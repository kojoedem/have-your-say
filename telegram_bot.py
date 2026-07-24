import requests
from config import BOT_TOKEN

# telegram api endpoint
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

def send_otp(chat_id: str, otp: str):
    # message sent to user
    message = f"🔐 Your OTP code is: {otp}\n\nDo not share this code."

    payload = {
        "chat_id": chat_id,
        "text": message
    }

    # send request to telegram
    response = requests.post(TELEGRAM_API, json=payload, timeout=5)

    return response.json()
