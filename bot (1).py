import logging
import os
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import feedparser
import requests
from bs4 import BeautifulSoup
import re
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, JobQueue, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

# --- Configuration & Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Essential Constants (Preserved as requested)
BOT_TOKEN = "8594908071:AAEKIjXRBvYyAS3fBiU0UFj-zqXdC2KemJ0"
CHANNEL_USERNAME = "@CyberMindAr"
ADMIN_ID = 7531900641
TIMEZONE = pytz.timezone("Asia/Riyadh")

# File paths
POSTS_FILE = "posted_content.json"
CONFIG_FILE = "bot_config.json"

# --- State Management ---
def load_json(file_path, default):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
    return default

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")

bot_config = load_json(CONFIG_FILE, {"posting_enabled": True, "post_stats": {}, "last_run_hour": -1})
posted_content = load_json(POSTS_FILE, [])

# --- Enhanced RSS Sources & Categories ---
RSS_FEEDS = {
    "أخبار تقنية عامة": [
        "https://aitnews.com/feed/",
        "https://www.tech-wd.com/wd/feed/",
        "https://ar.ign.com/news.xml",
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://www.wired.com/feed/rss",
        "https://gadgets360.com/rss/feeds"
    ],
    "ذكاء اصطناعي وأدوات": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "https://openai.com/news/rss.xml",
        "https://ai.googleblog.com/feeds/posts/default",
        "https://vistanews.ru/science/ai/rss.xml",
        "https://www.unite.ai/feed/",
        "https://news.ycombinator.com/rss"
    ],
    "أمن سيبراني وحماية": [
        "https://www.bleepingcomputer.com/feed/",
        "https://thehackernews.com/feeds/posts/default",
        "https://www.darkreading.com/rss.xml",
        "https://krebsonsecurity.com/feed/",
        "https://threatpost.com/feed/",
        "https://www.securityweek.com/rss"
    ],
    "برمجة وتطوير": [
        "https://dev.to/feed",
        "https://www.infoq.com/feed",
        "https://www.smashingmagazine.com/feed/",
        "https://hackernoon.com/feed",
        "https://www.freecodecamp.org/news/rss/"
    ],
    "هواتف وأجهزة ذكية": [
        "https://www.gsmarena.com/rss-news-reviews.php3",
        "https://www.androidauthority.com/feed/",
        "https://www.macrumors.com/macrumors.xml",
        "https://9to5mac.com/feed/"
    ],
    "عملات رقمية وبلوكشين": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://bitcoinmagazine.com/.rss/full/"
    ]
}

# --- 24-Hour Schedule with New Categories ---
CONTENT_SCHEDULE = {
    0: ("ملخص تقني ليلي 🌙", "أخبار تقنية عامة"),
    1: ("تلميحة برمجية 💻", "برمجة وتطوير"),
    2: ("أداة ذكاء اصطناعي 🤖", "ذكاء اصطناعي وأدوات"),
    3: ("نصيحة أمنية 🛡️", "أمن سيبراني وحماية"),
    4: ("عالم العملات الرقمية ₿", "عملات رقمية وبلوكشين"),
    5: ("مصدر تعلم 📚", "برمجة وتطوير"),
    6: ("أخبار الصباح التقنية ☀️", "أخبار تقنية عامة"),
    7: ("أداة إنتاجية 🚀", "ذكاء اصطناعي وأدوات"),
    8: ("جديد الهواتف 📱", "هواتف وأجهزة ذكية"),
    9: ("ثورة الـ AI 🤖", "ذكاء اصطناعي وأدوات"),
    10: ("تحذير أمني ⚠️", "أمن سيبراني وحماية"),
    11: ("تلميحة تقنية سريعة 💡", "أخبار تقنية عامة"),
    12: ("مقالات برمجية 📚", "برمجة وتطوير"),
    13: ("تكنولوجيا المستقبل 🚀", "أخبار تقنية عامة"),
    14: ("أسرار الاختراق والحماية 🔐", "أمن سيبراني وحماية"),
    15: ("تطبيقات ذكية 📲", "هواتف وأجهزة ذكية"),
    16: ("حقيقة تقنية ⚡", "أخبار تقنية عامة"),
    17: ("أدوات المطورين 🛠️", "برمجة وتطوير"),
    18: ("أخبار المساء التقنية 📰", "أخبار تقنية عامة"),
    19: ("شرح مصطلح تقني 🎯", "أخبار تقنية عامة"),
    20: ("أداة مجانية مميزة 🎁", "ذكاء اصطناعي وأدوات"),
    21: ("أخبار العملات المشفرة 🪙", "عملات رقمية وبلوكشين"),
    22: ("ملخص اليوم التقني 📊", "أخبار تقنية عامة"),
    23: ("أخبار عاجلة 🔔", "أخبار تقنية عامة")
}

# --- Core Functions ---

def translate_text(text, target_lang='ar'):
    if not text: return ""
    # Check if text is already mostly Arabic
    arabic_chars = re.findall(r'[\u0600-\u06FF]', text)
    if len(arabic_chars) > len(text) * 0.3: return text
        
    try:
        # Using MyMemory API for translation
        url = f"https://api.mymemory.translated.net/get?q={text[:500]}&langpair=en|{target_lang}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            translated = data.get('responseData', {}).get('translatedText', text)
            # Basic cleanup of HTML entities sometimes returned
            translated = BeautifulSoup(translated, "html.parser").get_text()
            return translated
    except Exception as e:
        logger.error(f"Translation error: {e}")
    return text

def fetch_rss_content(url):
    """Fixed: Added missing fetch_rss_content function"""
    try:
        feed = feedparser.parse(url)
        return feed.entries
    except Exception as e:
        logger.error(f"Error fetching RSS from {url}: {e}")
        return []

def extract_image_url(entry):
    """Enhanced image extraction"""
    # 1. Try media_content
    if 'media_content' in entry and entry.media_content:
        return entry.media_content[0]['url']
    # 2. Try enclosure
    if 'enclosures' in entry and entry.enclosures:
        for enc in entry.enclosures:
            if 'image' in enc.get('type', ''): return enc.get('href')
    # 3. Try links
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''): return link.get('href')
    # 4. Scrape from content/summary
    content = entry.get('content', [{}])[0].get('value', '') or entry.get('summary', '') or entry.get('description', '')
    if content:
        soup = BeautifulSoup(content, 'html.parser')
        img = soup.find('img')
        if img:
            src = img.get('src')
            if src and src.startswith('http'): return src
    return None

def generate_smart_hashtags(title, summary):
    combined = (title + " " + summary).lower()
    hashtags = {"#CyberMind", "#تقنية"}
    mapping = {
        r"ذكاء|ai|artificial|gpt|bot": "#ذكاء_اصطناعي",
        r"أمن|حماية|security|cyber|hack|اختراق": "#أمن_سيبراني",
        r"تطبيق|app|برنامج|ios|android": "#تطبيقات",
        r"أداة|tool": "#أدوات_تقنية",
        r"برمجة|code|dev|python|js": "#برمجة",
        r"هاتف|phone|iphone|samsung": "#هواتف",
        r"شركة|google|apple|meta|microsoft": "#شركات_تقنية",
        r"عملات|crypto|bitcoin|btc|eth": "#عملات_رقمية"
    }
    for pattern, tag in mapping.items():
        if re.search(pattern, combined): hashtags.add(tag)
    
    general = ["#تكنولوجيا", "#جديد_التقنية", "#عالم_التقنية", "#CyberSecurity"]
    while len(hashtags) < 6 and general:
        hashtags.add(general.pop(0))
    return list(hashtags)[:7]

def clean_and_format_text(title, summary, topic_name):
    ar_title = translate_text(title)
    
    # Clean summary from HTML
    soup = BeautifulSoup(summary, 'html.parser')
    clean_summary = soup.get_text().strip()
    # Limit summary length for translation and readability
    if len(clean_summary) > 400: clean_summary = clean_summary[:397] + "..."
    
    ar_summary = translate_text(clean_summary)
    
    # Formatting
    styled_text = f"🌟 <b>{topic_name}</b>\n\n"
    styled_text += f"🔥 <b>{ar_title}</b>\n\n"
    
    # Split by sentence and clean
    sentences = [s.strip() for s in ar_summary.split('.') if len(s.strip()) > 15]
    
    emojis = ["🔹", "⚡", "💎", "🛡️", "🚀", "💡", "✨", "📡"]
    random.shuffle(emojis)
    
    content_body = ""
    for i, s in enumerate(sentences[:3]):
        content_body += f"{emojis[i % len(emojis)]} {s}\n\n"
    
    if not content_body:
        content_body = f"🔹 {ar_summary[:300]}...\n\n"
        
    styled_text += content_body
    styled_text += "━━━━━━━━━━━━━━\n"
    styled_text += "🧠 <b>CyberMind | @CyberMindAr</b>\n\n"
    return styled_text

async def post_now(context: ContextTypes.DEFAULT_TYPE, force_hour=None) -> bool:
    """Enhanced posting logic with retry and better error handling"""
    now = datetime.now(TIMEZONE)
    hour = force_hour if force_hour is not None else now.hour
    topic_name, category = CONTENT_SCHEDULE.get(hour, ("أخبار تقنية", "أخبار تقنية عامة"))
    
    urls = RSS_FEEDS.get(category, RSS_FEEDS["أخبار تقنية عامة"])
    shuffled_urls = list(urls)
    random.shuffle(shuffled_urls)
    
    for url in shuffled_urls:
        entries = fetch_rss_content(url)
        if not entries: continue
        
        # Try top 5 entries from each feed
        for entry in entries[:5]:
            title = entry.get('title', '')
            link = entry.get('link', '')
            summary = entry.get('summary', '') or entry.get('description', '')
            
            # Uniqueness check
            if any(link == p.get("link") for p in posted_content) or not title:
                continue
                
            try:
                text = clean_and_format_text(title, summary, topic_name)
                tags = generate_smart_hashtags(title, summary)
                image_url = extract_image_url(entry)
                
                full_caption = f"{text}{' '.join(tags)}"
                keyboard = [[InlineKeyboardButton("🔗 اقرأ المزيد من المصدر", url=link)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Retry logic for Telegram API
                for attempt in range(3):
                    try:
                        if image_url:
                            try:
                                await context.bot.send_photo(
                                    chat_id=CHANNEL_USERNAME, 
                                    photo=image_url, 
                                    caption=full_caption, 
                                    reply_markup=reply_markup, 
                                    parse_mode=ParseMode.HTML
                                )
                            except Exception as img_err:
                                logger.warning(f"Failed to send photo: {img_err}, sending as text instead.")
                                await context.bot.send_message(
                                    chat_id=CHANNEL_USERNAME, 
                                    text=full_caption, 
                                    reply_markup=reply_markup, 
                                    parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=False
                                )
                        else:
                            await context.bot.send_message(
                                chat_id=CHANNEL_USERNAME, 
                                text=full_caption, 
                                reply_markup=reply_markup, 
                                parse_mode=ParseMode.HTML
                            )
                        
                        # Success! Record and return
                        posted_content.append({"timestamp": now.isoformat(), "link": link, "title": title})
                        save_json(POSTS_FILE, posted_content[-1000:]) # Keep last 1000
                        
                        day = now.strftime("%Y-%m-%d")
                        bot_config["post_stats"][day] = bot_config["post_stats"].get(day, 0) + 1
                        bot_config["last_run_hour"] = hour
                        save_json(CONFIG_FILE, bot_config)
                        return True
                        
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                    except (TimedOut, NetworkError):
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Telegram send attempt {attempt} failed: {e}")
                        break
                        
            except Exception as e:
                logger.error(f"Formatting/Processing error for {link}: {e}")
                continue
                
    return False

# --- Admin UI ---

def get_admin_keyboard():
    status = "🟢 نشط" if bot_config.get("posting_enabled", True) else "🔴 متوقف"
    keyboard = [
        [InlineKeyboardButton(f"الحالة: {status}", callback_data="toggle_posting")],
        [InlineKeyboardButton("🚀 انشر الآن", callback_data="post_now"), 
         InlineKeyboardButton("📊 الإحصائيات", callback_data="view_stats")],
        [InlineKeyboardButton("📅 جدول النشر", callback_data="view_schedule")],
        [InlineKeyboardButton("🔄 تحديث الإعدادات", callback_data="refresh_admin")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "🧠 <b>لوحة تحكم CyberMind V8 Pro</b>\n\n"
        "مرحباً بك في نظام إدارة المحتوى التقني المتكامل.\n\n"
        "• <b>القناة:</b> @CyberMindAr\n"
        "• <b>النظام:</b> آلي بالكامل (24 منشور يومياً)\n"
        "• <b>المصادر:</b> +30 مصدر عالمي وعربي\n"
        "• <b>الذكاء:</b> ترجمة آلية وتنسيق ذكي", 
        reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID: return
    await query.answer()
    
    if query.data == "toggle_posting":
        bot_config["posting_enabled"] = not bot_config.get("posting_enabled", True)
        save_json(CONFIG_FILE, bot_config)
        await query.edit_message_reply_markup(reply_markup=get_admin_keyboard())
    
    elif query.data == "post_now":
        await query.message.reply_text("⏳ جاري جلب محتوى جديد وترجمته...")
        success = await post_now(context)
        if success: await query.message.reply_text("✅ تم النشر بنجاح!")
        else: await query.message.reply_text("❌ فشل النشر أو لا يوجد محتوى جديد.")
        
    elif query.data == "view_schedule":
        text = "📅 <b>جدول النشر التلقائي:</b>\n\n"
        for h in range(24):
            t_name, cat = CONTENT_SCHEDULE[h]
            mark = "📍" if h == datetime.now(TIMEZONE).hour else "•"
            text += f"{mark} {h:02d}:00 | {t_name} ({cat})\n"
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)
        
    elif query.data == "view_stats":
        day = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        today_count = bot_config["post_stats"].get(day, 0)
        total_posted = len(posted_content)
        text = f"📊 <b>إحصائيات CyberMind:</b>\n\n"
        text += f"• منشورات اليوم: {today_count}\n"
        text += f"• إجمالي المنشورات: {total_posted}\n"
        text += f"• حالة النظام: {'متصل ✅' if bot_config['posting_enabled'] else 'متوقف ❌'}"
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)

    elif query.data == "refresh_admin":
        await query.edit_message_text(
            "🔄 تم تحديث لوحة التحكم.",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.HTML
        )

async def hourly_job(context: ContextTypes.DEFAULT_TYPE):
    if bot_config.get("posting_enabled", True):
        now = datetime.now(TIMEZONE)
        # Prevent double posting in the same hour if job runs multiple times
        if bot_config.get("last_run_hour") != now.hour:
            await post_now(context)

def main():
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Job Queue for automated posting
    if application.job_queue:
        # Run exactly at the start of every hour
        application.job_queue.run_repeating(
            hourly_job, 
            interval=3600, 
            first=datetime.now(TIMEZONE).replace(minute=0, second=5, microsecond=0) + timedelta(hours=1)
        )
        # Initial check in case it's a fresh start
        application.job_queue.run_once(hourly_job, 10)
    
    logger.info("CyberMind Bot V8 Pro Started Successfully.")
    application.run_polling()

if __name__ == "__main__":
    main()
