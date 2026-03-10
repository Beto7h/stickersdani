import os
import logging
import subprocess
import threading
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputSticker
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- 1. CONFIGURACIÓN ---
MONGO_URL = os.getenv("MONGO_URL")
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_NAME = os.getenv("DATABASE_NAME", "sticker_bot_db")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
packs_col = db["packs"]

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TITULO, URL = range(2)

def run_health_check():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self): 
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    port = int(os.getenv("PORT", 8080))
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()

# --- 2. FUNCIONES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"<b>¡Hola, {user_name}!</b> 👋 Soy tu Gestor de Stickers.\n\n"
        "Comandos:\n"
        "🗑 /purgar - Borra el último sticker añadido.\n\n"
        "🙏 Creador: @danielhs7"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Crear Nuevo Pack", callback_data='crear_pack')],
        [InlineKeyboardButton("📦 Mis Paquetes", callback_data='ver_packs')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def ver_mis_packs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    mis_packs = list(packs_col.find({"user_id": user_id}))
    
    if mis_packs:
        lista = [f"• <b>{p['titulo']}</b>\n  🔗 https://t.me/addstickers/{p['nombre_url']}" for p in mis_packs]
        texto = "📦 <b>Tus Paquetes Registrados:</b>\n\n" + "\n\n".join(lista)
    else:
        texto = "⚠️ No tienes packs registrados todavía."
    
    try:
        await query.edit_message_text(texto, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Error al editar mensaje: {e}")
        await query.message.reply_text("❌ Error al mostrar la lista.")

async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📝 Dime el <b>Título</b> visible del paquete:", parse_mode='HTML')
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text("🔗 Ahora dime el nombre para el enlace (letras y números):")
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_raw = update.message.text.strip().replace(" ", "_").lower()
    user_id = update.effective_user.id
    nombre_full = f"{nombre_raw}_by_{context.bot.username}"
    
    packs_col.update_one(
        {"nombre_url": nombre_full}, 
        {"$set": {"user_id": user_id, "titulo": context.user_data['temp_title']}}, 
        upsert=True
    )
    
    await update.message.reply_text(
        f"✅ ¡Pack reservado!\n🔗 https://t.me/addstickers/{nombre_full}", 
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def gestionar_contenido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pack_data = packs_col.find_one({"user_id": user_id}, sort=[('_id', -1)])
    
    if not pack_data:
        await update.message.reply_text("❌ Crea un pack primero con el botón de Nuevo Pack.")
        return
        
    status = await update.message.reply_text("⏳ Procesando...")
    try:
        if update.message.sticker:
            file = await update.message.sticker.get_file()
            fmt = "video" if update.message.sticker.is_video else "static"
            emoji = update.message.sticker.emoji or "✨"
        elif update.message.photo:
            file = await update.message.photo[-1].get_file()
            fmt = "static"
            emoji = "📸"
        else:
            file = await (update.message.video or update.message.animation).get_file()
            fmt = "video"
            emoji = "🎬"
            
        path = f"temp_{user_id}"
        await file.download_to_drive(path)
        
        with open(path, 'rb') as f:
            si = InputSticker(sticker=f, emoji_list=[emoji], format=fmt)
            try:
                await context.bot.add_sticker_to_set(user_id=user_id, name=pack_data['nombre_url'], sticker=si)
            except Exception:
                # CORRECCIÓN: Usamos 'format' en lugar de 'sticker_format'
                await context.bot.create_new_sticker_set(
                    user_id=user_id, 
                    name=pack_data['nombre_url'], 
                    title=pack_data['titulo'], 
                    stickers=[si], 
                    format=fmt 
                )
                
        await status.edit_text(f"✅ ¡Añadido!\nhttps://t.me/addstickers/{pack_data['nombre_url']}")
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        logging.error(f"Error: {e}")
        await status.edit_text(f"❌ Error técnico: {e}")

async def purgar_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pack_data = packs_col.find_one({"user_id": user_id}, sort=[('_id', -1)])
    if not pack_data: return
    try:
        s_set = await context.bot.get_sticker_set(pack_data['nombre_url'])
        if s_set.stickers:
            await context.bot.delete_sticker_from_set(s_set.stickers[-1].file_id)
            await update.message.reply_text("🗑 Último sticker borrado.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al borrar: {e}")

# --- 3. INICIO ---
def main():
    threading.Thread(target=run_health_check, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_creacion, pattern='^crear_pack$')],
        states={
            TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)], 
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, crear_pack_url)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("purgar", purgar_sticker))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(ver_mis_packs, pattern='^ver_packs$'))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Sticker.ALL, gestionar_contenido))
    
    print("Bot dmxsticker_bot en línea...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
