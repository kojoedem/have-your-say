from __future__ import annotations

import os
import random
import uuid
import shutil
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

# --- Helper to get authenticated user ---
def get_current_user(session_phone: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> Optional[User]:
    if not session_phone:
        return None
    user = db.query(User).filter(User.phone == session_phone).first()
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
        raise HTTPException(status_code=400, detail="Phone number is required.")

    otp_code = f"{random.randint(100000, 999999)}"
    otp_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)

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

    print(f"\n[MOCK SMS] To: {phone} | Code: {otp_code}\n")

    return {
        "success": True,
        "message": "OTP sent successfully (mocked).",
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

    user.is_verified = True
    user.otp_code = None
    user.otp_expires = None
    db.commit()

    response.set_cookie(
        key="session_phone",
        value=user.phone,
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
            "belief": user.belief,
            "has_profile": bool(user.username)
        }
    }

@app.post("/api/auth/profile")
def update_profile(
    username: str = Form(...),
    belief: str = Form(...),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    username = username.strip()
    belief = belief.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    existing = db.query(User).filter(User.username == username, User.id != user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username is already taken.")

    user.username = username
    user.belief = belief
    db.commit()

    return {
        "success": True,
        "message": "Profile updated successfully.",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "username": user.username,
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
            "belief": user.belief,
            "has_profile": bool(user.username)
        }
    }

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(key="session_phone")
    return {"success": True, "message": "Logged out successfully."}


# --- Topic and Comment Endpoints ---

@app.post("/api/topics")
def create_topic(
    text: str = Form(...),
    image: Optional[UploadFile] = File(None),
    location: Optional[str] = Form(None),
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
            "created_at": topic.created_at.isoformat(),
            "expires_at": topic.expires_at.isoformat()
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

        comments_list = []
        for c in sorted(t.comments, key=lambda x: x.created_at):
            comments_list.append({
                "id": c.id,
                "text": c.text,
                "location": c.location,
                "created_at": c.created_at.isoformat(),
                "author": {
                    "username": c.author.username or "Anonymous",
                    "belief": c.author.belief or ""
                }
            })

        topics_with_counts.append({
            "id": t.id,
            "text": t.text,
            "image_url": t.image_url,
            "location": t.location,
            "created_at": t.created_at.isoformat(),
            "expires_at": t.expires_at.isoformat(),
            "time_left_seconds": time_left_sec,
            "comments_count": comm_count,
            "comments": comments_list,
            "author": {
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

    comment = Comment(
        topic_id=topic_id,
        user_id=user.id,
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
            "text": comment.text,
            "location": comment.location,
            "created_at": comment.created_at.isoformat(),
            "author": {
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
                "username": t.author.username or "Anonymous"
            }
        })

    return {
        "success": True,
        "trending": trending
    }
