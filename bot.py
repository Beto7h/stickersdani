import os
import logging
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# 1. TRUCO PARA KOYEB: Servidor para responder al puerto
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot dmxsticker_bot activo")

def run_health_check():
    # Koyeb asigna el puerto automáticamente, generalmente el 8080
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# 2. CONFIGURACIÓN DEL BOT
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
SUFIJO_ENLACE = "by_dmxsticker_bot"
TITULO, URL, ESPERAR_ID = range(3)

# --- COMANDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"¡Hola, {user_name}! 👋 Soy tu **Gestor Personal de Stickers**.\n\n"
        "Conmigo puedes crear paquetes personalizados, convertir videos/GIFs y "
        "gestionar quién es el dueño de cada pack.\n\n"
        "¿Qué deseas hacer hoy?\n\n"
        "🙏 _Agradecimiento especial a mi creador:_ @danielhs7"
    )
    keyboard = [
        [InlineKeyboardButton("📦 Mis Paquetes", callback_query_data='ver_packs')],
        [InlineKeyboardButton("➕ Crear Nuevo Pack", callback_query_data='crear_pack')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Dime el **Título** visible de tu paquete (ej: Mis Stickers Cool):")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text(f"🔗 Ahora dime el nombre para el enlace.\nSe añadirá automáticamente: `_{SUFIJO_ENLACE}`")
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_usuario = update.message.text.strip().replace(" ", "_")
    enlace_final = f"{nombre_usuario}_{SUFIJO_ENLACE}"
    titulo = context.user_data['temp_title']
    
    await update.message.reply_text(
        f"✅ ¡Pack configurado!\n\n🌈 Título: {titulo}\n🔗 Enlace: https://t.me/add_stickers/{enlace_final}\n\n"
        "Ahora ya puedes enviarme videos o GIFs para convertirlos."
    )
    return ConversationHandler.END

async def procesar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Procesando video a formato Sticker Animado...")
    video_file = await update.message.video.get_file()
    input_p, output_p = "temp_in.mp4", "temp_out.webm"
    await video_file.download_to_drive(input_p)
    
    cmd = ['ffmpeg', '-y', '-i', input_p, '-vcodec', 'libvpx-vp9', '-an',
           '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
           '-t', '2.9', output_p]
    subprocess.run(cmd)
    
    await update.message.reply_document(document=open(output_p, 'rb'), filename="sticker.webm", caption="¡Listo!")
    if os.path.exists(input_p): os.remove(input_p)
    if os.path.exists(output_p): os.remove(output_p)

def main():
    if not TOKEN:
        print("ERROR: No se encontró la variable TELEGRAM_TOKEN")
        return

    # Iniciar el servidor de salud en un hilo aparte para no bloquear el bot
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
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION, procesar_video))

    print("Bot @dmxsticker_bot iniciado con Health Check...")
    app.run_polling()

if __name__ == '__main__':
    main()
    
