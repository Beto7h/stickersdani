FROM python:3.10-slim

# Instalamos ffmpeg para procesar los videos y convertirlos a .webm
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Comando para arrancar tu bot
CMD ["python", "bot.py"]
