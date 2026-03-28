import logging
import os
import json
import asyncio
import re
import time
import shutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
import yt_dlp

# --- Advanced Configuration ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Essential Constants (Preserved)
BOT_TOKEN = "8727707206:AAFE04HcDxRyYuS3iNVGGbi4eALqNqwzmY0"
ADMIN_ID = 7531900641
CHANNEL_USERNAME = "@CyberMindAr"

USER_DATA_FILE = "user_data.json"
STATS_FILE = "bot_stats.json"
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Ultra-Premium UI Strings ---
STRINGS = {
    "ar": {
        "welcome": (
            "💎 <b>مرحباً بك في النسخة الخارقة من بوت التحميل</b>\n\n"
            "أنا أقوى بوت تحميل في تيليجرام، مصمم لخدمتك بسرعة فائقة وأداء لا يضاهى.\n\n"
            "✨ <b>ما الذي يميزني؟</b>\n"
            "• ⚡ <b>سرعة توربو:</b> معالجة وتحميل في ثوانٍ.\n"
            "• 🌐 <b>دعم شامل:</b> +1000 منصة (YT, TikTok, IG, FB, X...).\n"
            "• 🎬 <b>جودة فائقة:</b> دعم دقات تصل إلى 4K و 8K.\n"
            "• 🎵 <b>نقاء الصوت:</b> تحويل MP3 بأعلى جودة 320kbps.\n"
            "• 🚫 <b>بدون علامة مائية:</b> تحميل فيديوهات تيك توك صافية.\n\n"
            "🌍 <b>اختر لغة الواجهة للبدء:</b>"
        ),
        "lang_set": "✅ <b>تم تفعيل الواجهة العربية!</b>\n\nأرسل الآن رابط الفيديو أو الصوت الذي تود تحميله.",
        "send_link": "📥 <b>من فضلك، أرسل الرابط الآن...</b>",
        "processing": "⚙️ <b>جاري تحليل الرابط بأقصى سرعة...</b>",
        "choose_quality": "🎬 <b>تم العثور على الفيديو! اختر الجودة:</b>\n\n📌 <i>ملاحظة: الجودات العالية قد تتجاوز 50MB.</i>",
        "downloading": "🚀 <b>جاري التحميل (Turbo Mode)...</b>\n\n{bar}\n\n📊 <b>التقدم:</b> <code>{progress}%</code>\n⚡ <b>السرعة:</b> <code>{speed}</code>\n📦 <b>الحجم:</b> <code>{size}</code>",
        "uploading": "📤 <b>اكتمل التحميل! جاري الرفع السريع...</b>",
        "error_link": "❌ <b>عذراً، الرابط غير مدعوم أو محمي. تأكد من صحة الرابط.</b>",
        "error_download": "❌ <b>فشل التحميل! قد يكون الفيديو طويلاً جداً أو محمياً.</b>",
        "file_too_large": "⚠️ <b>تنبيه: حجم الملف ({size}MB) كبير جداً!</b>\n\nتيليجرام يحد البوتات بـ 50MB.\n💡 <i>جرب اختيار جودة 480p أو 360p.</i>",
        "done": "✨ <b>تم التحميل بنجاح!</b>\n\n💎 بواسطة: @CyberMindAr",
        "audio": "🎵 تحميل كصوت MP3 (High Quality)",
        "cancel": "❌ إلغاء",
        "cancelled": "🚫 <b>تم الإلغاء. أنا جاهز لطلب جديد.</b>",
        "stats": "📊 <b>إحصائيات النظام:</b>\n\n👥 المستخدمين: <code>{users}</code>\n📥 التحميلات: <code>{downloads}</code>",
        "admin_only": "⚠️ للمسؤول فقط."
    },
    "en": {
        "welcome": (
            "💎 <b>Welcome to the Ultra-Premium Downloader Bot</b>\n\n"
            "I am the most powerful downloader on Telegram, built for speed and performance.\n\n"
            "✨ <b>Why Choose Me?</b>\n"
            "• ⚡ <b>Turbo Speed:</b> Processing and downloading in seconds.\n"
            "• 🌐 <b>Universal Support:</b> 1000+ sites (YT, TikTok, IG, FB, X...).\n"
            "• 🎬 <b>Ultra HD:</b> Support up to 4K and 8K resolutions.\n"
            "• 🎵 <b>Pure Audio:</b> MP3 conversion at 320kbps.\n"
            "• 🚫 <b>No Watermark:</b> Clean TikTok video downloads.\n\n"
            "🌍 <b>Choose your language to start:</b>"
        ),
        "lang_set": "✅ <b>English Interface Activated!</b>\n\nNow send the video or audio link you want to download.",
        "send_link": "📥 <b>Please, send the link now...</b>",
        "processing": "⚙️ <b>Analyzing link at maximum speed...</b>",
        "choose_quality": "🎬 <b>Video Found! Choose Quality:</b>\n\n📌 <i>Note: High qualities may exceed 50MB.</i>",
        "downloading": "🚀 <b>Downloading (Turbo Mode)...</b>\n\n{bar}\n\n📊 <b>Progress:</b> <code>{progress}%</code>\n⚡ <b>Speed:</b> <code>{speed}</code>\n📦 <b>Size:</b> <code>{size}</code>",
        "uploading": "📤 <b>Download complete! Fast uploading...</b>",
        "error_link": "❌ <b>Sorry, link not supported or protected. Check the URL.</b>",
        "error_download": "❌ <b>Download failed! Video might be too long or restricted.</b>",
        "file_too_large": "⚠️ <b>Warning: File size ({size}MB) is too large!</b>\n\nTelegram limits bots to 50MB.\n💡 <i>Try choosing 480p or 360p.</i>",
        "done": "✨ <b>Downloaded Successfully!</b>\n\n💎 By: @CyberMindAr",
        "audio": "🎵 Download as MP3 (High Quality)",
        "cancel": "❌ Cancel",
        "cancelled": "🚫 <b>Cancelled. Ready for a new request.</b>",
        "stats": "📊 <b>System Statistics:</b>\n\n👥 Users: <code>{users}</code>\n📥 Downloads: <code>{downloads}</code>",
        "admin_only": "⚠️ Admin only."
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
    return "⚡" * done + "◽" * (10 - done)

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
        'no_color': True,
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
            if current_time - last_update_time < 2.5: # Optimized update interval
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
                loop.create_task(message.edit_text(text, parse_mode=ParseMode.HTML))
            except: pass

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'logger': MyLogger(),
        'progress_hooks': [progress_hook],
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_color': True,
        'geo_bypass': True,
    }
    
    if "audio" in format_id:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            if not info: return None, None
            filename = ydl.prepare_filename(info)
            
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
        await update.message.reply_text(t(user_id, "send_link"), parse_mode=ParseMode.HTML)
        return

    url = url_match.group(0)
    msg = await update.message.reply_text(t(user_id, "processing"), parse_mode=ParseMode.HTML)
    
    info = await get_video_info(url)
    if not info:
        await msg.edit_text(t(user_id, "error_link"), parse_mode=ParseMode.HTML)
        return

    context.user_data['current_video'] = {'url': url, 'title': info.get('title', 'video')}

    keyboard = []
    formats = info.get('formats', [])
    
    # Advanced filtering for best qualities
    res_map = {}
    for f in formats:
        h = f.get('height')
        if h and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            if h not in res_map or f.get('tbr', 0) > res_map[h].get('tbr', 0):
                res_map[h] = f

    # Sort and add top resolutions
    for h in sorted(res_map.keys(), reverse=True):
        if h in [144, 240, 360, 480, 720, 1080, 1440, 2160]:
            ext = res_map[h].get('ext', 'mp4')
            keyboard.append([InlineKeyboardButton(f"🎬 {h}p HD ({ext})", callback_data=f"dl_{h}")])
    
    if not keyboard:
        keyboard.append([InlineKeyboardButton("🎬 Best Quality (Auto)", callback_data="dl_best")])
        
    keyboard.append([InlineKeyboardButton(t(user_id, "audio"), callback_data="dl_audio")])
    keyboard.append([InlineKeyboardButton(t(user_id, "cancel"), callback_data="dl_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    title = info.get('title', 'Video')
    if len(title) > 60: title = title[:57] + "..."
    
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
        await query.answer()
        await query.edit_message_text(t(user_id, "lang_set"), parse_mode=ParseMode.HTML)
        return

    if not data.startswith("dl_"): return

    action = data.split("_")[1]
    if action == "cancel":
        await query.edit_message_text(t(user_id, "cancelled"), parse_mode=ParseMode.HTML)
        return

    video_data = context.user_data.get('current_video')
    if not video_data:
        await query.answer("Session expired.")
        return

    await query.answer()
    msg = await query.edit_message_text(t(user_id, "downloading").format(bar=get_progress_bar(0), progress="0", speed="...", size="..."), parse_mode=ParseMode.HTML)
    
    url = video_data['url']
    if action == "audio": format_id = "bestaudio/best"
    elif action == "best": format_id = "bestvideo+bestaudio/best"
    else: format_id = f"bestvideo[height<={action}]+bestaudio/best[height<={action}]"

    file_path, info = await download_media(url, format_id, user_id, context, msg)
    
    if not file_path or not os.path.exists(file_path):
        await msg.edit_text(t(user_id, "error_download"), parse_mode=ParseMode.HTML)
        return

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > 50:
        await msg.edit_text(t(user_id, "file_too_large").format(size=round(size_mb, 1)), parse_mode=ParseMode.HTML)
        os.remove(file_path)
        return

    await msg.edit_text(t(user_id, "uploading"), parse_mode=ParseMode.HTML)
    
    try:
        if action == "audio":
            await context.bot.send_audio(
                chat_id=user_id,
                audio=open(file_path, 'rb'),
                title=video_data['title'],
                caption=t(user_id, "done"),
                parse_mode=ParseMode.HTML
            )
        else:
            await context.bot.send_video(
                chat_id=user_id,
                video=open(file_path, 'rb'),
                caption=t(user_id, "done"),
                supports_streaming=True,
                duration=info.get('duration'),
                width=info.get('width'),
                height=info.get('height'),
                parse_mode=ParseMode.HTML
            )
        update_stats(user_id, download=True)
        await msg.delete()
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await msg.edit_text(t(user_id, "error_download"), parse_mode=ParseMode.HTML)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    # Use concurrent workers for better performance
    application = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Ultra-Premium Downloader Bot Started.")
    application.run_polling()

if __name__ == "__main__":
    main()
