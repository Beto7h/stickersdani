import os
import logging
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- BASE DE DATOS SIMPLE (Archivo JSON) ---
DB_FILE = "packs_db.json"

def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

# --- TRUCO KOYEB ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Vivo")

def run_health_check():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- CONFIGURACIÓN ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
TITULO, URL = range(2)

# --- FUNCIONES DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = f"¡Hola, {user_name}! 👋\n\n¿Qué quieres hacer hoy?\n\n🙏 @danielhs7"
    keyboard = [
        [InlineKeyboardButton("➕ Crear Nuevo Pack", callback_data='crear_pack')],
        [InlineKeyboardButton("📦 Mis Paquetes", callback_data='ver_packs')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📝 Dime el **Título** del pack:")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text("🔗 Dime el nombre para el enlace:")
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_propuesto = update.message.text.strip().replace(" ", "_")
    user_id = str(update.effective_user.id)
    db = cargar_db()

    # VERIFICACIÓN DE DUPLICADOS
    if nombre_propuesto in db:
        propietario = db[nombre_propuesto]["user_id"]
        if propietario == user_id:
            await update.message.reply_text(f"⚠️ Este pack ya es tuyo. Enlace: https://t.me/addstickers/{nombre_propuesto}")
        else:
            await update.message.reply_text("❌ Este nombre ya está en uso por otro usuario. Por favor, intenta con otro nombre.")
        return URL # Lo mantenemos en el estado URL para que mande otro

    # REGISTRO EN "BASE DE DATOS"
    db[nombre_propuesto] = {
        "user_id": user_id,
        "titulo": context.user_data['temp_title']
    }
    guardar_db(db)

    await update.message.reply_text(
        f"✅ ¡Pack registrado con éxito!\n\n🔗 Enlace: https://t.me/addstickers/{nombre_propuesto}\n\n"
        "Ya puedes enviarme videos."
    )
    return ConversationHandler.END

async def ver_mis_packs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    db = cargar_db()
    
    mis_packs = [f"• {info['titulo']}: https://t.me/addstickers/{name}" for name, info in db.items() if info['user_id'] == user_id]
    
    if mis_packs:
        texto = "📦 **Tus Paquetes:**\n\n" + "\n".join(mis_packs)
    else:
        texto = "Aún no has creado ningún paquete. 😅"
    
    await query.edit_message_text(texto, parse_mode='Markdown')

async def procesar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Mantenemos la misma lógica de procesamiento de video anterior...)
    await update.message.reply_text("⏳ Procesando video...")
    # ... (FFmpeg command)

def main():
    if not TOKEN: return
    threading.Thread(target=run_health_check, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_creacion, pattern='crear_pack')],
        states={
            TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, crear_pack_url)],
        },
        fallbacks=[]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(ver_mis_packs, pattern='ver_packs'))
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION, procesar_video))
    
    app.run_polling()

if __name__ == '__main__':
    main()
