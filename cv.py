# bot.py
import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
import pdfplumber
from collections import Counter
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    DictPersistence,
)

from openai import OpenAI

# ──── إعدادات ────
GROK_API_KEY = "xai-YourApiKeyHere...................."  # ← غير هذا
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"              # ← غير هذا

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")

CHOICE, CV, EMAIL, PASSWORD = range(4)

async def grok_generate(prompt: str) -> str:
    try:
        resp = client.chat.completions.create(
            model="grok-4.1-fast",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()
    except:
        return "السلام عليكم، أتقدم بطلب لهذه الفرصة. مرفق سيرتي الذاتية. شكراً."

def extract_keywords(cv_path: str) -> list:
    text = ""
    if cv_path.endswith('.pdf'):
        with pdfplumber.open(cv_path) as pdf:
            text = " ".join(page.extract_text() or "" for page in pdf.pages)
    else:
        with open(cv_path, 'r', encoding='utf-8') as f:
            text = f.read()

    words = re.findall(r'\w+', text.lower())
    stopwords = set(['a','an','the','and','or','but','if','for','of','to','in','on','at','by','with','about','as','into','like','through','after','over','between','out','this','that','these','those','is','are','was','were','be','have','has','had','do','does','did','will','would','can','could','may','might','must'])
    filtered = [w for w in words if w not in stopwords and len(w) > 3]
    return [w for w, _ in Counter(filtered).most_common(6)]

def find_emails(query: str, max_emails: int = 6) -> list:
    emails = set()
    try:
        q = f"{query} email OR recrutement OR hr OR contact OR carrière OR emploi OR stage"
        resp = requests.get(
            f"https://www.google.com/search?q={requests.utils.quote(q)}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12
        )
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator=" ")
        found = re.findall(r'[\w\.-]+@[\w\.-]+\.\w{2,}', text)
        emails.update(found)
    except:
        pass

    return list(emails)[:max_emails]

def send_one_email(to_email: str, subject: str, body: str, from_email: str, app_password: str, cv_path: str) -> bool:
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    if os.path.exists(cv_path):
        subtype = "pdf" if cv_path.endswith(".pdf") else "txt"
        with open(cv_path, "rb") as f:
            attach = MIMEApplication(f.read(), _subtype=subtype)
            attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(cv_path))
            msg.attach(attach)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, app_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"فشل إرسال إلى {to_email} → {e}")
        return False

# ──── Conversation Handlers ────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("Stage / تدريب", callback_data="stage")],
        [InlineKeyboardButton("Emploi / Job", callback_data="job")],
    ]
    await update.message.reply_text(
        "مرحبا! 👋\nاختر نوع الفرص التي تبحث عنها:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOICE

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = query.data
    await query.edit_message_text(
        f"تم اختيار: {query.data}\n\nالآن أرسل سيرتك الذاتية (PDF أفضل)."
    )
    return CV

async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc = update.message.document
    if not doc:
        await update.message.reply_text("أرسل ملفًا (PDF أو txt).")
        return CV

    file = await doc.get_file()
    ext = ".pdf" if "pdf" in doc.mime_type.lower() else ".txt"
    path = f"cv_{update.effective_chat.id}{ext}"
    await file.download_to_drive(path)

    context.user_data["cv_path"] = path
    kws = extract_keywords(path)
    context.user_data["keywords"] = kws

    await update.message.reply_text(
        f"تم التحميل والتحليل.\nكلمات مفتاحية: {', '.join(kws)}\n\nأرسل Gmail الخاص بك."
    )
    return EMAIL

async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@gmail.com" not in email.lower():
        await update.message.reply_text("أرسل Gmail صالح.")
        return EMAIL

    context.user_data["sender_email"] = email
    await update.message.reply_text("أرسل App Password الخاص بك (من https://myaccount.google.com/apppasswords)")
    return PASSWORD

async def handle_password_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    app_pw = update.message.text.strip()
    data = context.user_data

    if "cv_path" not in data or "keywords" not in data:
        await update.message.reply_text("خطأ، ابدأ من جديد → /start")
        return ConversationHandler.END

    await update.message.reply_text("جاري البحث والإرسال...")

    q = " ".join(data["keywords"]) + f" {data['type']} tanger OR maroc OR remote OR stage OR emploi"
    found_emails = find_emails(q, max_emails=5)

    sent = 0
    for dest in found_emails:
        prompt = f"اكتب رسالة تقديم قصيرة احترافية لطلب {data['type']}, كلمات مفتاحية: {', '.join(data['keywords'])}"
        body = await grok_generate(prompt)
        subject = f"طلب {data['type'].title()} – Candidature"

        if send_one_email(dest, subject, body, data["sender_email"], app_pw, data["cv_path"]):
            sent += 1
            await context.bot.send_message(chat_id, f"تم الإرسال إلى {dest}")

        time.sleep(random.uniform(40, 120))

    await context.bot.send_message(chat_id, f"تم إرسال {sent} طلبات.\nشكراً!")

    if os.path.exists(data.get("cv_path", "")):
        os.remove(data["cv_path"])
    data.clear()

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم الإلغاء.")
    if "cv_path" in context.user_data and os.path.exists(context.user_data["cv_path"]):
        os.remove(context.user_data["cv_path"])
    context.user_data.clear()
    return ConversationHandler.END

def main():
    persistence = DictPersistence()
    app = Application.builder().token(TELEGRAM_TOKEN).persistence(persistence).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOICE: [CallbackQueryHandler(handle_choice)],
            CV: [MessageHandler(filters.Document.ALL, handle_cv)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password_and_run)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    print("البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
