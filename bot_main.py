import logging
import os
import asyncio
import aiosqlite
import aiohttp
import re
import json
import time
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import RetryAfter, TelegramError
from dotenv import load_dotenv

# استيراد الوظائف من bot_logic.py
from bot_logic import (
    init_db, configure_gemini, super_clean, ai_process_news, 
    is_content_duplicate, save_content_history, get_all_channels, 
    add_channel_to_db, remove_channel_from_db, get_posted_ids, 
    save_posted_id
)

# تحميل الإعدادات
load_dotenv("/home/ubuntu/almihwar_bot/bot_config_2.env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")
MY_CHANNEL_LINK = os.getenv("MY_CHANNEL_LINK", "https://t.me/almihwar_news")
DB_FILE = os.getenv("DB_FILE", "almihwar.db")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.85))
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# إعداد Gemini
configure_gemini(GEMINI_API_KEY)

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

IS_RUNNING = True
TOTAL_POSTED_TODAY = 0

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("عذراً، أنت لست المسؤول عن هذا البوت.")
        return

    keyboard = [
        [InlineKeyboardButton("إضافة قناة", callback_data='add_channel')],
        [InlineKeyboardButton("حذف قناة", callback_data='remove_channel')],
        [InlineKeyboardButton("قائمة القنوات", callback_data='list_channels')],
        [InlineKeyboardButton("إيقاف/تشغيل البوت", callback_data='toggle_running')],
        [InlineKeyboardButton("حالة البوت", callback_data='bot_status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        f"مرحباً {user.mention_html()}!\nأنا بوت شبكة المحور الإخبارية. كيف يمكنني مساعدتك؟",
        reply_markup=reply_markup
    )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'add_channel':
        await query.edit_message_text("الرجاء إرسال اسم المستخدم للقناة (مثال: almasirah).")
        context.user_data['awaiting_channel_add'] = True
    elif query.data == 'remove_channel':
        await query.edit_message_text("الرجاء إرسال اسم المستخدم للقناة المراد حذفها.")
        context.user_data['awaiting_channel_remove'] = True
    elif query.data == 'list_channels':
        channels = await get_all_channels(DB_FILE)
        if channels:
            channel_list = "\n".join([f"- @{ch}" for ch in channels])
            await query.edit_message_text(f"القنوات المراقبة:\n{channel_list}")
        else:
            await query.edit_message_text("لا توجد قنوات مراقبة حالياً.")
    elif query.data == 'toggle_running':
        global IS_RUNNING
        IS_RUNNING = not IS_RUNNING
        status = "يعمل" if IS_RUNNING else "متوقف"
        await query.edit_message_text(f"تم تغيير حالة البوت إلى: {status}")
    elif query.data == 'bot_status':
        status = "يعمل" if IS_RUNNING else "متوقف"
        await query.edit_message_text(f"حالة البوت: {status}\nإجمالي المنشورات اليوم: {TOTAL_POSTED_TODAY}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    if context.user_data.get('awaiting_channel_add'):
        channel_username = update.message.text.strip().replace('@', '')
        await add_channel_to_db(DB_FILE, channel_username)
        await update.message.reply_text(f"تم إضافة القناة @{channel_username} بنجاح.")
        context.user_data['awaiting_channel_add'] = False
    elif context.user_data.get('awaiting_channel_remove'):
        channel_username = update.message.text.strip().replace('@', '')
        await remove_channel_from_db(DB_FILE, channel_username)
        await update.message.reply_text(f"تم حذف القناة @{channel_username} بنجاح.")
        context.user_data['awaiting_channel_remove'] = False
    else:
        await start_command(update, context) # Show menu again if no specific action is pending

async def fetch_channel_posts(session, channel):
    url = f"https://t.me/s/{channel}"
    try:
        async with session.get(url, timeout=20) as res:
            if res.status != 200: 
                logger.warning(f"Failed to fetch {channel}: Status {res.status}")
                return []
            soup = BeautifulSoup(await res.text(), 'html.parser')
            msgs = soup.find_all('div', class_='tgme_widget_message_wrap')
            results = []
            for m in msgs[-5:]:
                msg_div = m.find('div', class_='tgme_widget_message')
                if not msg_div: continue
                p_id = f"{channel}_{msg_div.get('data-post')}"
                txt_div = m.find('div', class_='tgme_widget_message_text')
                txt = txt_div.get_text(separator='\n') if txt_div else ""
                
                photos = []
                photo_elements = m.find_all('a', class_='tgme_widget_message_photo_wrap')
                for p in photo_elements:
                    style = p.get('style')
                    if style:
                        match = re.search(r"url\('([^']+)'\)", style)
                        if match:
                            img_url = match.group(1)
                            if img_url and "telegram.org" not in img_url: photos.append(img_url)
                
                video = None
                video_div = m.find('a', class_='tgme_widget_message_video_player')
                if video_div:
                    video_url = video_div.get('href')
                    if video_url: video = video_url
                
                results.append({"id": p_id, "text": txt, "photos": photos, "video": video, "channel": channel})
            return results
    except Exception as e:
        logger.error(f"Fetch Error for {channel}: {e}")
        return []

async def scraping_job(context: ContextTypes.DEFAULT_TYPE):
    global TOTAL_POSTED_TODAY
    if not IS_RUNNING: 
        logger.info("Scraping job skipped: Bot is not running.")
        return
    
    posted_ids = await get_posted_ids(DB_FILE)
    
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}) as session:
        channels = await get_all_channels(DB_FILE)
        if not channels:
            logger.warning("No channels configured for scraping.")
            return

        for channel in channels:
            posts = await fetch_channel_posts(session, channel)
            for post in posts:
                if post['id'] in posted_ids: continue
                
                cleaned_text = super_clean(post["text"])
                if cleaned_text == "IGNORE":
                    await save_posted_id(DB_FILE, post['id'], "SKIPPED_CLEAN")
                    continue

                if await is_content_duplicate(DB_FILE, cleaned_text, SIMILARITY_THRESHOLD):
                    await save_posted_id(DB_FILE, post['id'], "SKIPPED_DUPLICATE")
                    continue
                
                final_ai_output = await ai_process_news(cleaned_text, MY_CHANNEL_LINK)
                if final_ai_output == "IGNORE":
                    await save_posted_id(DB_FILE, post['id'], "SKIPPED_AI")
                    continue

                try:
                    target = TARGET_CHANNEL
                    full_message = final_ai_output

                    if post["photos"]:
                        if len(post["photos"]) == 1:
                            await context.bot.send_photo(target, photo=post["photos"][0], caption=full_message, parse_mode=ParseMode.HTML)
                        else:
                            media_group = [InputMediaPhoto(post["photos"][0], caption=full_message, parse_mode=ParseMode.HTML)]
                            for p in post["photos"][1:5]: media_group.append(InputMediaPhoto(p))
                            await context.bot.send_media_group(target, media=media_group)
                    elif post["video"]:
                        await context.bot.send_video(target, video=post["video"], caption=full_message, parse_mode=ParseMode.HTML)
                    else:
                        await context.bot.send_message(target, full_message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                    
                    await save_posted_id(DB_FILE, post["id"], cleaned_text)
                    await save_content_history(DB_FILE, cleaned_text)
                    TOTAL_POSTED_TODAY += 1
                    logger.info(f"Successfully posted news from {channel}. Total posted today: {TOTAL_POSTED_TODAY}")
                    await asyncio.sleep(5) # Delay to avoid rate limits
                except RetryAfter as e:
                    logger.warning(f"Rate limit exceeded. Retrying after {e.retry_after} seconds.")
                    await asyncio.sleep(e.retry_after)
                except TelegramError as e:
                    logger.error(f"Telegram Error posting news from {channel}: {e}")
                except Exception as e:
                    logger.error(f"General Error posting news from {channel}: {e}")

def main():
    if not BOT_TOKEN: 
        logger.error("BOT_TOKEN not found. Exiting.")
        return
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    default_channels = [
        "almasirah", "mmy_news", "AnsarAllahMC", "ansarallah_news", 
        "Yemen_News_Agency", "muqawam313", "axisofresistance313",
        "Azaha_Setar", "sasat_almaserah", "alalam_arabia", "almanarnews",
        "C_Military1", "Palinfo", "Hezbollah", "sarayaps", "qassam_brigades",
        "UunionNews", "yemennow_news", "AlmayadeenLive", "a7l733i", "ALYEMENNET"
    ]
    loop.run_until_complete(init_db(DB_FILE, default_channels))
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_repeating(scraping_job, interval=300, first=10)
    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
