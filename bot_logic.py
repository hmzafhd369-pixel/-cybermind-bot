import logging
import os
import asyncio
import aiosqlite
import re
import json
import google.generativeai as genai
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

model = None

async def init_db(db_file, default_channels):
    async with aiosqlite.connect(db_file) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS posts (post_id TEXT PRIMARY KEY, clean_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS content_history (id INTEGER PRIMARY KEY AUTOINCREMENT, normalized_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS channels (username TEXT PRIMARY KEY)""")
        async with db.execute("SELECT COUNT(*) FROM channels") as cursor:
            if (await cursor.fetchone())[0] == 0:
                for ch in default_channels:
                    await db.execute("INSERT INTO channels (username) VALUES (?)", (ch,))
        await db.commit()

def configure_gemini(api_key):
    global model
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("Gemini model configured successfully.")
        except Exception as e:
            logger.error(f"Gemini Config Error: {e}")
            model = None
    else:
        logger.warning("GEMINI_API_KEY not found. AI processing will be disabled.")
        model = None

async def get_all_channels(db_file):
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT username FROM channels") as cursor:
            return [row[0] async for row in cursor]

async def add_channel_to_db(db_file, channel_username):
    async with aiosqlite.connect(db_file) as db:
        await db.execute("INSERT OR IGNORE INTO channels (username) VALUES (?)", (channel_username,))
        await db.commit()
        logger.info(f"Channel @{channel_username} added to DB.")

async def remove_channel_from_db(db_file, channel_username):
    async with aiosqlite.connect(db_file) as db:
        await db.execute("DELETE FROM channels WHERE username = ?", (channel_username,))
        await db.commit()
        logger.info(f"Channel @{channel_username} removed from DB.")

async def is_content_duplicate(db_file, new_text, similarity_threshold):
    if not new_text or len(new_text) < 20: return False
    norm_new = re.sub(r"[^\w\u0600-\u06FF]", "", new_text)
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT normalized_text FROM content_history ORDER BY timestamp DESC LIMIT 500") as cursor:
            recent_contents = [row[0] async for row in cursor]
    for old_norm in recent_contents:
        if old_norm and SequenceMatcher(None, norm_new, old_norm).ratio() > similarity_threshold:
            logger.info(f"Duplicate content detected: {new_text[:50]}...")
            return True
    return False

async def save_content_history(db_file, text):
    norm_text = re.sub(r"[^\w\u0600-\u06FF]", "", text)
    async with aiosqlite.connect(db_file) as db:
        await db.execute("INSERT INTO content_history (normalized_text) VALUES (?)", (norm_text,))
        await db.commit()

async def get_posted_ids(db_file):
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT post_id FROM posts") as cursor:
            return {row[0] async for row in cursor}

async def save_posted_id(db_file, post_id, clean_text):
    async with aiosqlite.connect(db_file) as db:
        await db.execute("INSERT INTO posts (post_id, clean_text) VALUES (?, ?)", (post_id, clean_text))
        await db.commit()

def super_clean(text):
    if not text: return ""
    
    # 1. حذف كلمة "قناة ." وأي توقيعات مصادر في نهاية النص
    text = re.sub(r"قناة\s*\.?\s*$", "", text.strip())
    text = re.sub(r"\bقناة\s*\.\s*", "", text)
    
    # 2. حذف جمل الاشتراك والروابط
    text = re.sub(r"للاشتراك في ال\s*\.?\s*", "", text)
    text = re.sub(r"للاشتراك\s*(في|عبر)?\s*(القناة|تيليجرام)?.*", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"t\.me/\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#[\w_\u0600-\u06FF]+", "", text)
    
    # 3. قائمة الكلمات المرفوضة (فقط ما يتعلق بالاشتراك والروابط)
    bad_phrases = [
        "قناة احتياطية", "Channel created", "نرجو الاشتراك", "نشر رابطها",
        "انضموا إلينا", "رابط القناة", "رابط المجموعة", "تابعونا على"
    ]
    # بدلاً من تجاهل الخبر بالكامل، سنقوم بحذف هذه الجمل فقط
    for phrase in bad_phrases:
        text = text.replace(phrase, "")

    # تصفية الضجيج (الرموز التعبيرية المفرطة والجمل الإنشائية المكررة والأسئلة الشخصية)
    # إزالة الإيموجي المفرط (أكثر من 3 إيموجي في سطر واحد يعتبر مفرطاً)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        emoji_count = len(re.findall(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]", line))
        if emoji_count > 3: # إذا كان هناك أكثر من 3 إيموجي في سطر واحد، اعتبره ضجيجاً واحذفه
            continue
        # سنبقي على معظم المحتوى الآن بناءً على طلب المستخدم
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # إزالة الحشو (إزاحة الستار، كشف المستور، شاهد الآن) - تم إضافتها بالفعل في bad_phrases

    # منع الاختراق الدعائي (روابط قنوات، حسابات "إكس"، مجموعات "واتساب"، أو جمل مثل "انضموا إلينا")
    # روابط القنوات وحسابات X والواتساب تم التعامل معها في re.sub(r'https?://\S+', '', text) و re.sub(r't\.me/\S+', '', text, flags=re.IGNORECASE)
    # جمل مثل "انضموا إلينا" تم التعامل معها في bad_phrases

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines).strip()

async def ai_process_news(text, my_channel_link):
    if not model or not text: return "IGNORE"
    
    prompt = f"""أنت الآن المنسق العام لغرفة أخبار المحور. مهمتك هي إدارة التدفق الإخباري بدقة استخباراتية، مع دمج الخبر الميداني بالتحليل السياسي وفق البروتوكول التالي:

#### 🛑 أولاً: جدار الحماية (قواعد الحذف القطعي)
 * **منع الاختراق الدعائي:** يُحذف أي نص يتضمن روابط قنوات، حسابات "إكس"، مجموعات "واتساب"، أو جمل مثل "انضموا إلينا".
 * **تصفية الضجيج:** تُحذف الرموز التعبيرية المفرطة، الجمل الإنشائية المكررة، والأسئلة الشخصية التي لا تحمل معلومة.
 * **إزالة الحشو:** امسح كلمات مثل (إزاحة الستار، كشف المستور، شاهد الآن) واعتمد لغة الخبر المباشر.

#### 📊 ثانياً: تصنيف المحتوى المقبول (مصفوفة النشر)
يُسمح بنشر خمسة مسارات فقط، ولكل مسار "وسم" بصري محدد:
 1. **الميدان والبلاغات:** (أخبار الاشتباكات، القصف، البيانات العسكرية).
 2. **المجازر والانتهاكات:** (التغطية الإنسانية لجرائم العدوان).
 3. **المواقف السياسية:** (التصريحات الرسمية وردود الفعل الدولية والمحلية).
 4. **التحليل والمتابعة:** (قراءة في أبعاد الحدث، رصد تحركات العدو، التطورات اللاحقة).
 5. **قوافل المجد:** (نعي الشهداء والتشييع).

#### ⚔️ ثالثاً: الترميز السيادي (الهوية)
(يُوضع الرمز في بداية الخبر لبيان الجغرافيا السياسية):
🇵🇸 فلسطين | 🇱🇧 لبنان | 🇮🇷 إيران | 🇾🇪 اليمن | 🇮🇶 العراق | 🇸🇾 سوريا

#### 🛡️ رابعاً: الدليل البصري للوظائف (إيموجي واحد فقط)
 * 🚨 **عاجل / تصريح رسمي.**
 * 💥 **قصف / غارات / مجازر.**
 * 🔥 **عمليات ميدانية / اشتباكات.**
 * 🎯 **تحليل / متابعة خلفيات الحدث.**
 * ⚖️ **ردود فعل / مواقف سياسية.**
 * 🕊️ **شهداء.**

#### 📐 خامساً: القواعد التقنية (التنسيق الاحترافي)
 * **نظام "النص المكثف":** لا أسطر فارغة بين الفقرات، الخبر متماسك جداً.
 * **صيغة الصياغة:** [رمز الهوية] [جهة الخبر]: [مضمون الخبر/التحليل/الرد].
 * **اللغة:** لغة رصينة، تبدأ من اليمين، وتستخدم الفعل المضارع للمتابعة (مثال: "يتابع المحور رصد...") والماضي للحدث (مثال: "استهدفت المقاومة...").

#### 🔚 سادساً: التذييل الموحد
ـــــــــــــــــــــــــــــــــــــــــــــــــ
🚩 **شبكة المحور الإخبارية**
🔗 {my_channel_link}
#شبكة_المحور_الإخبارية

الخبر المراد معالجته:
{text}

ملاحظة هامة جداً: اقبل أي محتوى إخباري أو تحليل أو بيان، ولا تستخدم "IGNORE" إلا إذا كان النص فارغاً تماماً أو لا يحتوي على أي معلومة مفيدة إطلاقاً. مهمتك الأساسية هي تنظيف النص من أي روابط (Links) أو أسماء قنوات (Channel Names) أو دعوات للاشتراك، وإعادة صياغته وفق القواعد المذكورة أعلاه. يجب أن يكون الإخراج باللغة العربية فقط.
"""
    
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        if response and response.text:
            result = response.text.strip()
            if "IGNORE" in result: return "IGNORE"
            return result
        return "IGNORE"
    except Exception as e:
        logger.error(f"AI Error: {e}")
        if "429" in str(e):
            await asyncio.sleep(60)
        return "IGNORE"

# هذه الدالة لم تعد ضرورية إذا كان Gemini يعيد النص المنسق بالكامل
# ولكن يمكن استخدامها لتنظيف إضافي أو استخراج عناصر إذا لزم الأمر
