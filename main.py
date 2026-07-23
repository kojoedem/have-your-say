from __future__ import annotations

import os
import random
import uuid
import shutil
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI, Depends, HTTPException, status, Response, Cookie, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session


from database import init_db, get_db, User, Topic, Comment

app = FastAPI(title="Have Your Say - One Page App")

# Create static directories for uploads and frontend assets
os.makedirs("static", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database
init_db()

# --- Telegram Bot Background Polling and Mapping ---
import threading
import time
import urllib.request
import urllib.parse
import json

# Global mapping for phone -> chat_id
user_telegram_mapping = {}

def telegram_bot_poll():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[Telegram Bot] TELEGRAM_BOT_TOKEN not set. Polling inactive.")
        return

    print(f"[Telegram Bot] Starting background polling thread...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=10"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("ok"):
                    for update in data.get("result", []):
                        update_id = update.get("update_id")
                        if update_id >= offset:
                            offset = update_id + 1

                        message = update.get("message")
                        if not message:
                            continue

                        chat_id = message.get("chat", {}).get("id")
                        text = message.get("text", "")

                        if text.startswith("/start "):
                            payload = text.split("/start ")[1]
                            if payload.startswith("login_"):
                                phone = payload.split("login_")[1]
                                user_telegram_mapping[phone] = chat_id

                                # Generate OTP code and save to DB
                                otp_code = f"{random.randint(100000, 999999)}"
                                otp_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)

                                # Access database
                                from database import SessionLocal, User
                                db = SessionLocal()
                                try:
                                    user = db.query(User).filter(User.phone == phone).first()
                                    if not user:
                                        user = User(
                                            phone=phone,
                                            otp_code=otp_code,
                                            otp_expires=otp_expires,
                                            is_verified=False
                                        )
                                        db.add(user)
                                    else:
                                        user.otp_code = otp_code
                                        user.otp_expires = otp_expires
                                        user.is_verified = False
                                    db.commit()

                                    # Send success OTP reply via Telegram
                                    reply_msg = f"✅ Account linked successfully!\n\n🔐 Your Have Your Say OTP code is: {otp_code}\n\nDo not share this code."
                                    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                                    send_data = urllib.parse.urlencode({
                                        "chat_id": chat_id,
                                        "text": reply_msg
                                    }).encode("utf-8")
                                    send_req = urllib.request.Request(send_url, data=send_data, method="POST")
                                    with urllib.request.urlopen(send_req, timeout=5) as send_resp:
                                        pass
                                    print(f"[Telegram Bot] Link & OTP sent to {phone} (Chat ID {chat_id})")
                                except Exception as dberr:
                                    print(f"[Telegram Bot DB Error] {dberr}")
                                finally:
                                    db.close()
        except Exception as e:
            # Avoid logging excessive errors if offline/invalid token
            time.sleep(5)
        time.sleep(2)

# Start background thread
polling_thread = threading.Thread(target=telegram_bot_poll, daemon=True)
polling_thread.start()

# --- Helper to get authenticated user ---
def get_current_user(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> Optional[User]:
    if not session_token:
        return None
    user = db.query(User).filter(User.session_token == session_token).first()
    if user and user.is_verified:
        return user
    return None

def require_current_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please verify your phone number."
        )
    return user

# --- Frontpage route ---
@app.get("/", response_class=HTMLResponse)
def read_index():
    with open("templates/index.html", "r") as f:
        return f.read()

# --- Authentication Endpoints ---

@app.post("/api/auth/otp-request")
def request_otp(phone: str = Form(...), db: Session = Depends(get_db)):
    phone = phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number, Telegram ID, or Email is required.")

    # Check if the input is an email address
    is_email = "@" in phone

    otp_code = f"{random.randint(100000, 999999)}"
    otp_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_username = os.getenv("TELEGRAM_BOT_USERNAME", "HaveYourSayBot")

    # If it is not an email and Telegram Bot is fully configured, check for deep link association
    if not is_email and telegram_token:
        chat_id = user_telegram_mapping.get(phone)
        if not chat_id:
            # Not linked yet! Return a redirect response with the Telegram deep link
            telegram_link = f"https://t.me/{telegram_username}?start=login_{phone}"
            return {
                "success": True,
                "status": "redirect",
                "telegram_link": telegram_link,
                "message": "Open Telegram to link your account and receive your OTP."
            }
        else:
            # Already linked! Send direct Telegram message
            user = db.query(User).filter(User.phone == phone).first()
            if not user:
                user = User(
                    phone=phone,
                    otp_code=otp_code,
                    otp_expires=otp_expires,
                    is_verified=False
                )
                db.add(user)
            else:
                user.otp_code = otp_code
                user.otp_expires = otp_expires
                user.is_verified = False
            db.commit()

            try:
                message = f"🔐 Your Have Your Say OTP code is: {otp_code}\n\nDo not share this code."
                url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                data = urllib.parse.urlencode({
                    "chat_id": chat_id,
                    "text": message
                }).encode("utf-8")
                req = urllib.request.Request(url, data=data, method="POST")
                with urllib.request.urlopen(req, timeout=5) as response:
                    pass
                print(f"[Telegram Bot] Sent direct OTP to Chat ID {chat_id}.")
            except Exception as e:
                print(f"[Telegram Bot Error] Failed to send direct message: {e}")

            return {
                "success": True,
                "message": "OTP sent via Telegram.",
                "phone": phone,
                "otp_code": otp_code
            }

    # Standard email or mock fallback login
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            phone=phone,
            otp_code=otp_code,
            otp_expires=otp_expires,
            is_verified=False
        )
        db.add(user)
    else:
        user.otp_code = otp_code
        user.otp_expires = otp_expires
        user.is_verified = False

    db.commit()

    if is_email:
        print(f"\n[MOCK EMAIL] To: {phone} | Code: {otp_code}\n")
    else:
        print(f"\n[MOCK SMS] To: {phone} | Code: {otp_code}\n")

    return {
        "success": True,
        "message": f"OTP sent successfully ({'mocked email' if is_email else 'mocked SMS'}).",
        "phone": phone,
        "otp_code": otp_code
    }

@app.post("/api/auth/otp-verify")
def verify_otp(
    response: Response,
    phone: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    phone = phone.strip()
    code = code.strip()

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Request OTP first.")

    if not user.otp_expires:
        raise HTTPException(status_code=400, detail="No OTP requested.")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if now_naive > user.otp_expires:
        raise HTTPException(status_code=400, detail="OTP has expired.")

    if user.otp_code != code:
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # Generate a random alias and username on every login
    adjectives = ["Silent", "Quiet", "Hidden", "Shadow", "Deep", "Bold", "Free", "Wild", "Bright", "Epic", "Magic", "Crypto", "Nova", "Cosmic", "Mystic"]
    nouns = ["Thinker", "Voice", "Echo", "Philosopher", "Dreamer", "Seeker", "Rebel", "Mind", "Nomad", "Wanderer", "Stargazer", "Oracle", "Scribe"]
    random_alias = f"{random.choice(adjectives)}_{random.choice(nouns)}"
    random_suffix = secrets.token_hex(2)

    user.alias = random_alias
    user.username = f"{random_alias}_{random_suffix}"

    user.is_verified = True
    user.otp_code = None
    user.otp_expires = None
    user.session_token = secrets.token_hex(32)
    db.commit()

    response.set_cookie(
        key="session_token",
        value=user.session_token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        samesite="lax"
    )

    return {
        "success": True,
        "message": "Authentication successful.",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "username": user.username,
            "alias": user.alias,
            "belief": user.belief,
            "has_profile": bool(user.username)
        }
    }

@app.post("/api/auth/profile")
def update_profile(
    username: str = Form(...),
    belief: Optional[str] = Form(None),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    alias = username.strip()
    belief = belief.strip() if belief else ""

    if not alias:
        raise HTTPException(status_code=400, detail="Username is required.")

    random_suffix = secrets.token_hex(2)
    public_username = f"{alias}_{random_suffix}"

    user.alias = alias
    user.username = public_username
    user.belief = belief
    db.commit()

    return {
        "success": True,
        "message": "Profile updated successfully.",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "username": user.username,
            "alias": user.alias,
            "belief": user.belief,
            "has_profile": True
        }
    }

@app.get("/api/auth/me")
def get_me(user: Optional[User] = Depends(get_current_user)):
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "phone": user.phone,
            "username": user.username,
            "alias": user.alias,
            "belief": user.belief,
            "has_profile": bool(user.username)
        }
    }

@app.post("/api/auth/logout")
def logout(
    response: Response,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user:
        user.session_token = None
        db.commit()
    response.delete_cookie(key="session_token")
    return {"success": True, "message": "Logged out successfully."}


# --- Topic and Comment Endpoints ---

@app.post("/api/topics")
def create_topic(
    text: str = Form(...),
    image: Optional[UploadFile] = File(None),
    location: Optional[str] = Form(None),
    allow_download: bool = Form(True),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Topic text cannot be empty.")

    image_url = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1]
        unique_filename = f"{uuid.uuid4()}{ext}"
        filepath = f"static/uploads/{unique_filename}"
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/uploads/{unique_filename}"

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now_naive + timedelta(hours=12)

    topic = Topic(
        user_id=user.id,
        text=text,
        image_url=image_url,
        location=location.strip() if location else None,
        allow_download=allow_download,
        created_at=now_naive,
        expires_at=expires_at
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    return {
        "success": True,
        "topic": {
            "id": topic.id,
            "text": topic.text,
            "image_url": topic.image_url,
            "location": topic.location,
            "allow_download": topic.allow_download,
            "created_at": topic.created_at.isoformat(),
            "expires_at": topic.expires_at.isoformat(),
            "author": {
                "id": user.id,
                "username": user.username or "Anonymous",
                "belief": user.belief or ""
            }
        }
    }

@app.get("/api/topics")
def get_topics(db: Session = Depends(get_db)):
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active_topics = db.query(Topic).filter(Topic.expires_at > now_naive).all()

    active_topics = sorted(active_topics, key=lambda t: t.created_at, reverse=True)

    topics_with_counts = []
    max_comments = 0

    for t in active_topics:
        comm_count = len(t.comments)
        if comm_count > max_comments:
            max_comments = comm_count

        time_left_sec = max(0, int((t.expires_at - now_naive).total_seconds()))

        # Build structured comments with nested replies
        all_comments = sorted(t.comments, key=lambda x: x.created_at)
        top_level_comments = [c for c in all_comments if c.parent_id is None]

        replies_map = {}
        for c in all_comments:
            if c.parent_id is not None:
                replies_map.setdefault(c.parent_id, []).append(c)

        structured_comments = []
        for c in top_level_comments:
            c_replies = replies_map.get(c.id, [])
            replies_list = []
            for r in c_replies:
                replies_list.append({
                    "id": r.id,
                    "parent_id": r.parent_id,
                    "text": r.text,
                    "location": r.location,
                    "created_at": r.created_at.isoformat(),
                    "author": {
                    "id": r.author.id,
                        "username": r.author.username or "Anonymous",
                        "belief": r.author.belief or ""
                    }
                })

            structured_comments.append({
                "id": c.id,
                "parent_id": None,
                "text": c.text,
                "location": c.location,
                "created_at": c.created_at.isoformat(),
                "author": {
                    "id": c.author.id,
                    "username": c.author.username or "Anonymous",
                    "belief": c.author.belief or ""
                },
                "replies": replies_list,
                "replies_count": len(replies_list),
                "is_pinned": False
            })

        # Pin the top-level comment with the most replies (if there are any replies at all)
        if structured_comments:
            max_replies = max(item["replies_count"] for item in structured_comments)
            if max_replies > 0:
                pinned_idx = next(i for i, item in enumerate(structured_comments) if item["replies_count"] == max_replies)
                structured_comments[pinned_idx]["is_pinned"] = True
                pinned_comment = structured_comments.pop(pinned_idx)
                structured_comments.insert(0, pinned_comment)

        topics_with_counts.append({
            "id": t.id,
            "text": t.text,
            "image_url": t.image_url,
            "location": t.location,
            "allow_download": t.allow_download,
            "created_at": t.created_at.isoformat(),
            "expires_at": t.expires_at.isoformat(),
            "time_left_seconds": time_left_sec,
            "comments_count": comm_count,
            "comments": structured_comments,
            "author": {
                "id": t.author.id,
                "username": t.author.username or "Anonymous",
                "belief": t.author.belief or ""
            }
        })

    for item in topics_with_counts:
        if max_comments > 0:
            item["progress_percent"] = int((item["comments_count"] / max_comments) * 100)
        else:
            item["progress_percent"] = 0

    return {
        "success": True,
        "topics": topics_with_counts
    }

@app.post("/api/topics/{topic_id}/comments")
def create_comment(
    topic_id: int,
    text: str = Form(...),
    parent_id: Optional[int] = Form(None),
    location: Optional[str] = Form(None),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text cannot be empty.")

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if now_naive > topic.expires_at:
        raise HTTPException(status_code=400, detail="This topic has expired and cannot be commented on.")

    if parent_id:
        parent_comment = db.query(Comment).filter(Comment.id == parent_id, Comment.topic_id == topic_id).first()
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Parent comment not found.")

    comment = Comment(
        topic_id=topic_id,
        user_id=user.id,
        parent_id=parent_id,
        text=text,
        location=location.strip() if location else None,
        created_at=now_naive
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "success": True,
        "comment": {
            "id": comment.id,
            "parent_id": comment.parent_id,
            "text": comment.text,
            "location": comment.location,
            "created_at": comment.created_at.isoformat(),
            "author": {
                "id": user.id,
                "username": user.username or "Anonymous",
                "belief": user.belief or ""
            }
        }
    }

@app.get("/api/trending")
def get_trending_topics(db: Session = Depends(get_db)):
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active_topics = db.query(Topic).filter(Topic.expires_at > now_naive).all()

    sorted_topics = sorted(active_topics, key=lambda t: (len(t.comments), t.created_at), reverse=True)

    trending = []
    for t in sorted_topics[:5]:
        trending.append({
            "id": t.id,
            "text": t.text,
            "comments_count": len(t.comments),
            "image_url": t.image_url,
            "location": t.location,
            "author": {
                "id": t.author.id,
                "username": t.author.username or "Anonymous"
            }
        })

    return {
        "success": True,
        "trending": trending
    }

@app.put("/api/topics/{topic_id}")
def update_topic(
    topic_id: int,
    text: Optional[str] = Form(None),
    allow_download: Optional[bool] = Form(None),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")
    if topic.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to edit this conversation.")

    if text is not None:
        text = text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Topic text cannot be empty.")
        topic.text = text

    if allow_download is not None:
        topic.allow_download = allow_download

    db.commit()
    return {"success": True, "message": "Topic updated successfully."}

@app.delete("/api/topics/{topic_id}")
def delete_topic(
    topic_id: int,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")
    if topic.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this conversation.")

    db.delete(topic)
    db.commit()
    return {"success": True, "message": "Topic deleted successfully."}

@app.put("/api/comments/{comment_id}")
def update_comment(
    comment_id: int,
    text: str = Form(...),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to edit this comment.")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text cannot be empty.")

    comment.text = text
    db.commit()
    return {"success": True, "message": "Comment updated successfully."}

@app.delete("/api/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this comment.")

    db.delete(comment)
    db.commit()
    return {"success": True, "message": "Comment deleted successfully."}
