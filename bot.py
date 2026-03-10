import os
import logging
import subprocess
import threading
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputSticker
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURACIÓN DE BASE DE DATOS ---
MONGO_URL = os.getenv("MONGO_URL")
TOKEN = os.getenv("TELEGRAM_TOKEN")
client = MongoClient(MONGO_URL)
db = client[os.getenv("DATABASE_NAME", "sticker_bot_db")]
packs_col = db["packs"]

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TITULO, URL = range(2)

# --- SERVIDOR DE SALUD PARA KOYEB ---
def run_health_check():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), Handler).serve_forever()

# --- FUNCIONES DE INTERFAZ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"¡Hola, {user_name}! 👋 Soy tu **Gestor Personal de Stickers**.\n\n"
        "Conmigo puedes crear paquetes personalizados, convertir videos/GIFs y "
        "gestionar tus packs de forma sencilla.\n\n"
        "Comandos útiles:\n"
        "🗑 /purgar - Borra el último sticker añadido.\n\n"
        "🙏 _Agradecimiento especial a mi creador:_ @danielhs7"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Crear Nuevo Pack", callback_data='crear_pack')],
        [InlineKeyboardButton("📦 Mis Paquetes", callback_data='ver_packs')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📝 Dime el **Título** del paquete (ej: Mis Stickers):")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text("🔗 Dime el nombre único para el enlace (sin espacios):")
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_raw = update.message.text.strip().replace(" ", "_").lower()
    user_id = update.effective_user.id
    nombre_full = f"{nombre_raw}_by_{context.bot.username}"

    if packs_col.find_one({"nombre_url": nombre_full}):
        await update.message.reply_text("❌ Ese enlace ya existe. Prueba otro:")
        return URL

    packs_col.insert_one({"user_id": user_id, "nombre_url": nombre_full, "titulo": context.user_data['temp_title']})
    await update.message.reply_text(f"✅ Pack reservado!\n🔗 https://t.me/addstickers/{nombre_full}")
    return ConversationHandler.END

# --- LÓGICA DE STICKERS ---
async def gestionar_contenido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pack_data = packs_col.find_one({"user_id": user_id}, sort=[('_id', -1)])
    if not pack_data: return

    status = await update.message.reply_text("⏳ Procesando...")
    nombre_pack = pack_data['nombre_url']

    try:
        if update.message.sticker:
            file = await update.message.sticker.get_file()
            format_type = "video" if update.message.sticker.is_video else "static"
            emoji = update.message.sticker.emoji or "✨"
        elif update.message.photo:
            file = await update.message.photo[-1].get_file()
            format_type = "static"
            emoji = "📸"
        else:
            file = await (update.message.video or update.message.animation).get_file()
            format_
