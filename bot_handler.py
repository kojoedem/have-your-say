from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

from database import SessionLocal, User
from otp import generate_otp
from config import BOT_TOKEN

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    # Check if deep link payload exists
    if context.args:
        payload = context.args[0]  # login_233xxxx

        if payload.startswith("login_"):
            phone = payload.split("login_")[1]

            # Save mapping automatically (NO manual work)
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.phone == phone).first()
                if not user:
                    user = User(
                        phone=phone,
                        is_verified=False
                    )
                    db.add(user)

                user.telegram_chat_id = chat_id
                user.is_verified = False
                db.commit()

                # generate OTP
                otp = generate_otp(phone)

                # send OTP directly in Telegram
                await update.message.reply_text(
                    f"✅ Account linked successfully!\n\n🔐 Your OTP code is: {otp}\n\nDo not share this code."
                )
            except Exception as e:
                print(f"[Telegram Bot Error] Failed to link and generate OTP: {e}")
                await update.message.reply_text("An error occurred. Please try again.")
            finally:
                db.close()
        else:
            await update.message.reply_text("Invalid request")
    else:
        await update.message.reply_text("Welcome to Have Your Say! Use the app to login.")

def run_bot():
    if not BOT_TOKEN or BOT_TOKEN.lower() in ["your_bot_token", "your_token", "yourbottoken", "fake", ""]:
        print("[Telegram Bot] TELEGRAM_BOT_TOKEN not configured or is a placeholder. Bot polling not started.")
        return

    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        from telegram.error import InvalidToken
    except ImportError:
        InvalidToken = Exception

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))

        print("Starting Telegram Bot polling...")
        # close_loop=False and stop_signals=False prevent signal handler errors on background threads
        app.run_polling(close_loop=False, stop_signals=False)
    except InvalidToken as e:
        print(f"[Telegram Bot Error] Failed to initialize bot with token `{BOT_TOKEN}`: {e}")
    except Exception as e:
        print(f"[Telegram Bot Error] Unexpected error starting bot: {e}")

if __name__ == "__main__":
    run_bot()
