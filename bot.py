import os
import logging
import subprocess
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Configuración de Logs para ver errores en Koyeb
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Variables de configuración
TOKEN = os.getenv("TELEGRAM_TOKEN")
# Aquí definimos el sufijo que pediste para los enlaces
SUFIJO_ENLACE = "by_dmxsticker_bot"

# Estados para los pasos del bot
TITULO, URL, ESPERAR_ID = range(3)

# --- COMANDO INICIAL ---
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

# --- PROCESO DE CREAR PACK ---
async def iniciar_creacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Dime el **Título** visible de tu paquete (ej: Mis Stickers Cool):")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_title'] = update.message.text
    await update.message.reply_text(
        f"🔗 Ahora dime el nombre para el enlace.\n"
        f"Se añadirá automáticamente: `_{SUFIJO_ENLACE}`"
    )
    return URL

async def crear_pack_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_usuario = update.message.text.strip().replace(" ", "_")
    # Aplicamos tu regla específica de nombre
    enlace_final = f"{nombre_usuario}_{SUFIJO_ENLACE}"
    titulo = context.user_data['temp_title']
    
    await update.message.reply_text(
        f"✅ ¡Pack configurado!\n\n"
        f"🌈 Título: {titulo}\n"
        f"🔗 Enlace: https://t.me/add_stickers/{enlace_final}\n\n"
        "Ahora ya puedes enviarme videos o GIFs para convertirlos y añadirlos."
    )
    return ConversationHandler.END

# --- CONVERSIÓN DE VIDEO ---
async def procesar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Procesando video a formato Sticker Animado...")
    
    video_file = await update.message.video.get_file()
    input_p = "temp_in.mp4"
    output_p = "temp_out.webm"
    
    await video_file.download_to_drive(input_p)
    
    # Comando para cumplir con los requisitos de Telegram (512x512, VP9, sin audio)
    cmd = [
        'ffmpeg', '-y', '-i', input_p,
        '-vcodec', 'libvpx-vp9', '-an',
        '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
        '-t', '2.9', output_p
    ]
    subprocess.run(cmd)
    
    await update.message.reply_document(
        document=open(output_p, 'rb'),
        filename=f"sticker.webm",
        caption="¡Listo! Aquí tienes tu sticker animado."
    )
    
    if os.path.exists(input_p): os.remove(input_p)
    if os.path.exists(output_p): os.remove(output_p)

def main():
    if not TOKEN:
        print("ERROR: No se encontró la variable TELEGRAM_TOKEN")
        return

    app = Application.builder().token(TOKEN).build()

    # Manejo de la creación del pack
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

    print("Bot @dmxsticker_bot iniciado correctamente.")
    app.run_polling()

if __name__ == '__main__':
    main()
  
