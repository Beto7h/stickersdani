import os
import logging
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- TRUCO PARA KOYEB: Servidor de Salud ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot dmxsticker_bot activo")

def run_health_check():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- CONFIGURACIÓN DEL BOT ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Estados para la creación del pack
TITULO, URL = range(2)

# --- COMANDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"¡Hola, {user_name}! 👋 Soy tu **Gestor Personal de Stickers**.\n\n"
        "🙏 _Agradecimiento especial a mi creador:_ @danielhs7"
    )
    # Corregido: 'callback_data' en lugar de 'callback_query_data'
    keyboard = [[InlineKeyboardButton("➕ Crear Nuevo Pack", callback_data='crear_pack')]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📝 Dime el **Título** visible del paquete:")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text("🔗 Ahora dime el nombre para el enlace (se usará para la URL final):")
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Limpiamos el texto del usuario para la URL
    nombre_usuario = update.message.text.strip().replace(" ", "_")
    
    # NUEVA ESTRUCTURA DE ENLACE SOLICITADA
    enlace_final = f"https://t.me/addstickers/{nombre_usuario}"
    titulo = context.user_data['temp_title']
    
    await update.message.reply_text(
        f"✅ ¡Pack configurado!\n\n"
        f"🌈 Título: {titulo}\n"
        f"🔗 Enlace: {enlace_final}\n\n"
        "Ahora ya puedes enviarme videos o GIFs para convertirlos."
    )
    return ConversationHandler.END

async def procesar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Procesando video...")
    try:
        video = update.message.video or update.message.animation
        video_file = await video.get_file()
        
        input_p = f"in_{update.effective_user.id}.mp4"
        output_p = f"out_{update.effective_user.id}.webm"
        await video_file.download_to_drive(input_p)

        cmd = [
            'ffmpeg', '-y', '-i', input_p,
            '-vcodec', 'libvpx-vp9', '-an',
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
            '-pix_fmt', 'yuva420p', '-t', '2.9', '-crf', '30', '-b:v', '256k', output_p
        ]
        
        subprocess.run(cmd, timeout=30)

        if os.path.exists(output_p):
            await update.message.reply_document(
                document=open(output_p, 'rb'),
                filename="sticker.webm",
                caption="✅ ¡Aquí tienes tu sticker listo!"
            )
        else:
            await status_msg.edit_text("❌ Error al convertir el video.")
    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text("❌ Ocurrió un error al procesar el video.")
    finally:
        if 'input_p' in locals() and os.path.exists(input_p): os.remove(input_p)
        if 'output_p' in locals() and os.path.exists(output_p): os.remove(output_p)

def main():
    if not TOKEN: return

    # Iniciar Health Check para Koyeb
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
    
    print("Bot dmxsticker_bot en línea...")
    app.run_polling()

if __name__ == '__main__':
    main()
