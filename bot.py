import logging
import os
import json
import asyncio
import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
import yt_dlp

# --- Configuration ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Use the token and admin ID from the original code
BOT_TOKEN = "8594908071:AAEKIjXRBvYyAS3fBiU0UFj-zqXdC2KemJ0"
ADMIN_ID = 7531900641
USER_DATA_FILE = "user_data.json"
STATS_FILE = "bot_stats.json"
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Translations ---
STRINGS = {
    "ar": {
        "welcome": "👋 أهلاً بك في <b>بوت التحميل الخارق</b>!\n\nيمكنني التحميل من جميع المنصات:\n• YouTube & Shorts\n• TikTok (بدون علامة مائية)\n• Instagram (Reels & Stories)\n• Facebook & Twitter (X)\n• والمزيد من +1000 موقع!\n\nالرجاء اختيار اللغة:",
        "lang_set": "✅ تم ضبط اللغة إلى العربية.",
        "send_link": "📥 أرسل لي رابط الفيديو الآن.",
        "processing": "🔍 جاري فحص الرابط واستخراج الجودات المتاحة...",
        "choose_quality": "🎬 اختر الجودة المطلوبة للفيديو:\n\n📌 <i>ملاحظة: الجودات العالية قد تتجاوز حجم 50MB.</i>",
        "downloading": "📥 جاري التحميل...\n\n{bar}\n\nالتقدم: {progress}%\nالسرعة: {speed}\nالحجم: {size}",
        "uploading": "📤 اكتمل التحميل! جاري الرفع إلى تيليجرام...",
        "error_link": "❌ عذراً، الرابط غير مدعوم أو الفيديو خاص/محذوف.",
        "error_download": "❌ حدث خطأ غير متوقع أثناء التحميل. حاول مرة أخرى.",
        "file_too_large": "⚠️ حجم الملف ({size}MB) يتجاوز حد الـ 50MB المسموح به للبوتات في تيليجرام.\n\n💡 نصيحة: حاول اختيار جودة أقل (مثل 480p أو 360p).",
        "done": "✅ تم التحميل بنجاح بواسطة @CyberMindAr",
        "audio": "🎵 تحميل كصوت (MP3)",
        "cancel": "❌ إلغاء",
        "cancelled": "🚫 تم إلغاء العملية.",
        "stats": "📊 <b>إحصائيات البوت:</b>\n\n• عدد المستخدمين: {users}\n• إجمالي التحميلات: {downloads}",
        "admin_only": "⚠️ هذا الأمر للمسؤول فقط."
    },
    "en": {
        "welcome": "👋 Welcome to the <b>Ultimate Downloader Bot</b>!\n\nI can download from all platforms:\n• YouTube & Shorts\n• TikTok (No Watermark)\n• Instagram (Reels & Stories)\n• Facebook & Twitter (X)\n• And 1000+ more sites!\n\nPlease choose your language:",
        "lang_set": "✅ Language set to English.",
        "send_link": "📥 Send me the video link now.",
        "processing": "🔍 Processing link and fetching available qualities...",
        "choose_quality": "🎬 Choose the desired video quality:\n\n📌 <i>Note: High qualities may exceed 50MB.</i>",
        "downloading": "📥 Downloading...\n\n{bar}\n\nProgress: {progress}%\nSpeed: {speed}\nSize: {size}",
        "uploading": "📤 Download complete! Uploading to Telegram...",
        "error_link": "❌ Sorry, the link is not supported or the video is private/deleted.",
        "error_download": "❌ An unexpected error occurred during download. Try again.",
        "file_too_large": "⚠️ File size ({size}MB) exceeds the 50MB limit for Telegram bots.\n\n💡 Tip: Try choosing a lower quality (e.g., 480p or 360p).",
        "done": "✅ Downloaded successfully by @CyberMindAr",
        "audio": "🎵 Download as Audio (MP3)",
        "cancel": "❌ Cancel",
        "cancelled": "🚫 Operation cancelled.",
        "stats": "📊 <b>Bot Statistics:</b>\n\n• Total Users: {users}\n• Total Downloads: {downloads}",
        "admin_only": "⚠️ This command is for admin only."
    }
}

# --- State & Stats Management ---
def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return default

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

user_data = load_json(USER_DATA_FILE, {})
bot_stats = load_json(STATS_FILE, {"total_downloads": 0})

def get_lang(user_id):
    return user_data.get(str(user_id), {}).get("lang", "ar")

def t(user_id, key):
    lang = get_lang(user_id)
    return STRINGS[lang].get(key, STRINGS["en"][key])

def update_stats(user_id, download=False):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {"lang": "ar", "joined": datetime.now().isoformat()}
    if download:
        bot_stats["total_downloads"] += 1
        save_json(STATS_FILE, bot_stats)
    save_json(USER_DATA_FILE, user_data)

# --- Progress Bar Helper ---
def get_progress_bar(percent):
    done = int(percent / 10)
    return "🟢" * done + "⚪" * (10 - done)

# --- Downloader Logic ---
class MyLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): logger.error(msg)

async def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': MyLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return await asyncio.to_thread(ydl.extract_info, url, download=False)
    except Exception as e:
        logger.error(f"Info error: {e}")
        return None

async def download_media(url, format_id, user_id, context, message):
    timestamp = int(time.time())
    output_template = os.path.join(DOWNLOAD_DIR, f"{user_id}_{timestamp}.%(ext)s")
    
    last_update_time = 0
    
    def progress_hook(d):
        nonlocal last_update_time
        if d['status'] == 'downloading':
            current_time = time.time()
            if current_time - last_update_time < 2: # Update every 2 seconds
                return
            
            last_update_time = current_time
            p_raw = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                p = float(p_raw)
                bar = get_progress_bar(p)
                speed = d.get('_speed_str', 'N/A')
                size = d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', 'N/A'))
                
                text = t(user_id, "downloading").format(
                    bar=bar, progress=p_raw, speed=speed, size=size
                )
                
                loop = asyncio.get_event_loop()
                loop.create_task(message.edit_text(text))
            except: pass

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'logger': MyLogger(),
        'progress_hooks': [progress_hook],
    }
    
    if "audio" in format_id:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Handle extension changes (e.g. mp3)
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(os.path.basename(base)):
                        filename = os.path.join(DOWNLOAD_DIR, f)
                        break
            return filename, info
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None, None

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_stats(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("العربية 🇸🇦", callback_data="setlang_ar"),
            InlineKeyboardButton("English 🇺🇸", callback_data="setlang_en")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(STRINGS["ar"]["welcome"], reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text(t(user_id, "admin_only"))
        return
    
    text = t(user_id, "stats").format(
        users=len(user_data),
        downloads=bot_stats.get("total_downloads", 0)
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    update_stats(user_id)
    
    url_match = re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    if not url_match:
        await update.message.reply_text(t(user_id, "send_link"))
        return

    url = url_match.group(0)
    msg = await update.message.reply_text(t(user_id, "processing"))
    
    info = await get_video_info(url)
    if not info:
        await msg.edit_text(t(user_id, "error_link"))
        return

    context.user_data['current_video'] = {'url': url, 'title': info.get('title', 'video')}

    keyboard = []
    formats = info.get('formats', [])
    
    # Filter for unique resolutions
    res_map = {}
    for f in formats:
        h = f.get('height')
        if h and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            if h not in res_map or f.get('tbr', 0) > res_map[h].get('tbr', 0):
                res_map[h] = f

    # Sort resolutions descending
    for h in sorted(res_map.keys(), reverse=True):
        if h in [144, 240, 360, 480, 720, 1080, 1440, 2160]:
            ext = res_map[h].get('ext', 'mp4')
            keyboard.append([InlineKeyboardButton(f"🎬 {h}p ({ext})", callback_data=f"dl_{h}")])
    
    if not keyboard:
        keyboard.append([InlineKeyboardButton("🎬 Best Quality", callback_data="dl_best")])
        
    keyboard.append([InlineKeyboardButton(t(user_id, "audio"), callback_data="dl_audio")])
    keyboard.append([InlineKeyboardButton(t(user_id, "cancel"), callback_data="dl_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    title = info.get('title', 'Video')
    if len(title) > 50: title = title[:47] + "..."
    
    await msg.edit_text(
        f"<b>📦 {title}</b>\n\n{t(user_id, 'choose_quality')}", 
        reply_markup=reply_markup, 
        parse_mode=ParseMode.HTML
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("setlang_"):
        lang = data.split("_")[1]
        user_data[str(user_id)]["lang"] = lang
        save_json(USER_DATA_FILE, user_data)
        await query.answer(t(user_id, "lang_set"))
        await query.edit_message_text(t(user_id, "lang_set") + "\n\n" + t(user_id, "send_link"))
        return

    if not data.startswith("dl_"): return

    action = data.split("_")[1]
    if action == "cancel":
        await query.edit_message_text(t(user_id, "cancelled"))
        return

    video_data = context.user_data.get('current_video')
    if not video_data:
        await query.answer("Session expired.")
        return

    await query.answer()
    msg = await query.edit_message_text(t(user_id, "downloading").format(bar=get_progress_bar(0), progress="0", speed="...", size="..."))
    
    url = video_data['url']
    if action == "audio": format_id = "bestaudio/best"
    elif action == "best": format_id = "bestvideo+bestaudio/best"
    else: format_id = f"bestvideo[height<={action}]+bestaudio/best[height<={action}]"

    file_path, info = await download_media(url, format_id, user_id, context, msg)
    
    if not file_path or not os.path.exists(file_path):
        await msg.edit_text(t(user_id, "error_download"))
        return

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > 50:
        await msg.edit_text(t(user_id, "file_too_large").format(size=round(size_mb, 1)))
        os.remove(file_path)
        return

    await msg.edit_text(t(user_id, "uploading"))
    
    try:
        thumb = None
        if info.get('thumbnails'):
            thumb = info['thumbnails'][-1]['url']

        if action == "audio":
            await context.bot.send_audio(
                chat_id=user_id,
                audio=open(file_path, 'rb'),
                title=video_data['title'],
                caption=t(user_id, "done")
            )
        else:
            await context.bot.send_video(
                chat_id=user_id,
                video=open(file_path, 'rb'),
                caption=t(user_id, "done"),
                supports_streaming=True,
                duration=info.get('duration'),
                width=info.get('width'),
                height=info.get('height')
            )
        update_stats(user_id, download=True)
        await msg.delete()
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await msg.edit_text(t(user_id, "error_download"))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Ultimate Downloader Bot Started.")
    application.run_polling()

if __name__ == "__main__":
    main()
