import random
from datetime import datetime, timezone, timedelta
from database import SessionLocal, User

def generate_otp(identifier: str) -> str:
    # generate 6 digit OTP
    otp = str(random.randint(100000, 999999))

    db = SessionLocal()
    try:
        if "@" in identifier:
            user = db.query(User).filter(User.email == identifier).first()
            if not user:
                user = User(email=identifier, is_verified=False)
                db.add(user)
        else:
            user = db.query(User).filter(User.phone == identifier).first()
            if not user:
                user = User(phone=identifier, is_verified=False)
                db.add(user)

        user.otp_code = otp
        # OTP valid for 5 minutes
        user.otp_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
        db.commit()
    finally:
        db.close()
    return otp

def verify_otp(identifier: str, user_otp: str) -> bool:
    db = SessionLocal()
    try:
        if "@" in identifier:
            user = db.query(User).filter(User.email == identifier).first()
        else:
            user = db.query(User).filter(User.phone == identifier).first()

        if not user or not user.otp_expires or not user.otp_code:
            return False

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        # check expiry
        if now_naive > user.otp_expires:
            user.otp_code = None
            user.otp_expires = None
            db.commit()
            return False

        # check match
        if user.otp_code == user_otp:
            user.otp_code = None
            user.otp_expires = None
            db.commit()
            return True
    finally:
        db.close()
    return False
