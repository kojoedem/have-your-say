import smtplib
from email.message import EmailMessage
from config import SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_SENDER

def send_email_otp(recipient_email: str, otp_code: str) -> bool:
    """
    Sends a real SMTP email containing the 6-digit OTP code.
    """
    message = EmailMessage()
    message["Subject"] = "🔐 Your Have Your Say OTP Code"
    message["From"] = SMTP_SENDER
    message["To"] = recipient_email

    body = f"Hello,\n\n🔐 Your OTP code is: {otp_code}\n\nDo not share this code with anyone.\n\nBest regards,\nHave Your Say Team"
    message.set_content(body)

    try:
        # Use SMTP_SSL for standard SSL port 465, or standard SMTP with starttls for 587/others
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                if SMTP_PORT == 587:
                    server.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)

        print(f"[Email Sender] Real email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"[Email Sender Error] Failed to send email to {recipient_email}: {e}")
        return False
