import os

# bot token from BotFather
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# bot username (without @)
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "HaveYourSayBot")

# SMTP Mail Server configurations
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "robinedemamedzo@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SENDER = "robinedemamedzo@gmail.com"
