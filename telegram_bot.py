try:
    import requests
except Exception:
    # Fallback small shim if 'requests' isn't available in the environment.
    import urllib.request as _urllib_request
    import json as _json

    class _Response:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class requests:  # minimal compatible subset used by this module
        @staticmethod
        def post(url, json=None, **kwargs):
            body = _json.dumps(json).encode('utf-8') if json is not None else None
            req = _urllib_request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            with _urllib_request.urlopen(req) as resp:
                resp_data = resp.read().decode('utf-8')
            try:
                parsed = _json.loads(resp_data)
            except Exception:
                parsed = {'raw': resp_data}
            return _Response(parsed)
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
    response = requests.post(TELEGRAM_API, json=payload)

    return response.json()
