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
from config import BOT_USERNAME, BOT_TOKEN
from otp import generate_otp, verify_otp
from email_sender import send_email_otp

app = FastAPI(title="Have Your Say - One Page App")

# Create static directories for uploads and frontend assets
os.makedirs("static", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database
init_db()

# Startup event to run the Telegram Bot polling in a background thread if token is set
@app.on_event("startup")
def start_telegram_bot():
    if BOT_TOKEN:
        import threading
        from bot_handler import run_bot
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        print("[main] Started Telegram bot polling in a background thread.")

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
            detail="Authentication required. Please verify your identity."
        )
    return user

# --- Frontpage route ---
@app.get("/", response_class=HTMLResponse)
def read_index():
    with open("templates/index.html", "r") as f:
        return f.read()

# --- Authentication Endpoints ---

@app.post("/api/auth/otp-request")
def request_otp(
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    if phone:
        phone = phone.strip()
    if email:
        email = email.strip()

    if not phone and not email:
        raise HTTPException(status_code=400, detail="Either phone number or email address is required.")

    # Use otp.py functions for OTP generation
    identifier = phone if phone else email
    otp_code = generate_otp(identifier)

    if phone:
        user = db.query(User).filter(User.phone == phone).first()
        # If user has not linked their Telegram Chat ID yet, return deep-link redirect
        if not user or not user.telegram_chat_id:
            telegram_link = f"https://t.me/{BOT_USERNAME}?start=login_{phone}"
            return {
                "success": True,
                "status": "redirect",
                "message": "Open Telegram to link your account and get OTP code.",
                "telegram_link": telegram_link,
                "phone": phone,
                "otp_code": otp_code
            }

        # If already linked, send the OTP code via Telegram Bot
        print(f"\n[MOCK SMS] To: {phone} | Code: {otp_code}\n")

        if BOT_TOKEN and user.telegram_chat_id:
            try:
                from telegram_bot import send_otp
                send_otp(user.telegram_chat_id, otp_code)
                print(f"[Telegram Bot] Sent directly to Chat ID {user.telegram_chat_id}.")
            except Exception as e:
                print(f"[Telegram Bot Error] Failed to send message: {e}")

        return {
            "success": True,
            "message": "OTP sent successfully via Telegram bot.",
            "phone": phone,
            "otp_code": otp_code
        }

    else:
        # Email flow
        print(f"\n[MOCK EMAIL] To: {email} | Code: {otp_code}\n")

        # Trigger real email sending via SMTP and raise error with SMTP details if it fails
        success, err_msg = send_email_otp(email, otp_code)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Email delivery failed: {err_msg}"
            )

        return {
            "success": True,
            "message": "OTP sent successfully to your email address.",
            "email": email
        }

@app.post("/api/auth/otp-verify")
def verify_otp_endpoint(
    response: Response,
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    if phone:
        phone = phone.strip()
    if email:
        email = email.strip()

    if not phone and not email:
        raise HTTPException(status_code=400, detail="Either phone number or email address is required for verification.")

    code = code.strip()

    # Use otp.py functions for OTP validation
    identifier = phone if phone else email
    if not verify_otp(identifier, code):
        raise HTTPException(status_code=400, detail="Invalid OTP code or it has expired.")

    if phone:
        user = db.query(User).filter(User.phone == phone).first()
    else:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found. Request OTP first.")

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
            "email": user.email,
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
            "email": user.email,
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
            "email": user.email,
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
