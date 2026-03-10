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
            format_type = "video"
            emoji = "🎬"

        path = f"file_{user_id}"
        await file.download_to_drive(path)

        with open(path, 'rb') as s_file:
            new_s = InputSticker(sticker=s_file, emoji_list=[emoji])
            try:
                await context.bot.add_sticker_to_set(user_id=user_id, name=nombre_pack, sticker=new_s)
            except Exception:
                await context.bot.create_new_sticker_set(
                    user_id=user_id, name=nombre_pack, title=pack_data['titulo'], 
                    stickers=[new_s], sticker_format=format_type
                )

        await status.edit_text(f"✅ ¡Añadido! Mira tu pack aquí:\nhttps://t.me/addstickers/{nombre_pack}")
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        logging.error(e)
        await status.edit_text("❌ Error: Asegúrate de que el video sea corto o envía un sticker.")

async def purgar_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pack_data = packs_col.find_one({"user_id": user_id}, sort=[('_id', -1)])
    if not pack_data: return

    try:
        sticker_set = await context.bot.get_sticker_set(pack_data['nombre_url'])
        if sticker_set.stickers:
            await context.bot.delete_sticker_from_set(sticker_set.stickers[-1].file_id)
            await update.message.reply_text("🗑 Último sticker borrado.")
    except Exception:
        await update.message.reply_text("❌ No se pudo borrar nada.")

async def ver_mis_packs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mis_packs = packs_col.find({"user_id": update.effective_user.id})
    lista = [f"• {p['titulo']}: https://t.me/addstickers/{p['nombre_url']}" for p in mis_packs]
    texto = "📦 **Tus Paquetes:**\n\n" + "\n".join(lista) if lista else "No tienes packs."
    await query.edit_message_text(texto, parse_mode='Markdown')

def main():
    threading.Thread(target=run_health_check, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_creacion, pattern='crear_pack')],
        states={TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)], 
                URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, crear_pack_url)]},
        fallbacks=[]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("purgar", purgar_sticker))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(ver_mis_packs, pattern='ver_packs'))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Sticker.ALL, gestionar_contenido))
    app.run_polling()

if __name__ == '__main__': main()
