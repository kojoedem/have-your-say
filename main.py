from __future__ import annotations

import os
import random
import uuid
import shutil
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI, Depends, HTTPException, status, Response, Cookie, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import init_db, get_db, SessionLocal, User, Topic, Comment, Video
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

# Background task for video processing
def background_video_processing(video_id: int, filename: str, db_session_maker, frame_index: int = 0):
    from video_processor import trim_selected_video_frame
    result = trim_selected_video_frame(video_id, filename, frame_index)
    if result:
        db = db_session_maker()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.duration = result["duration"]
                video.segments_count = result["segments_count"]
                db.commit()
                print(f"[background_video_processing] Updated video {video_id}: duration={video.duration}, segments={video.segments_count}")
        except Exception as e:
            print(f"[background_video_processing] Error updating video database: {e}")
        finally:
            db.close()

# Startup event to run the Telegram Bot polling in a background thread if token is set
@app.on_event("startup")
def start_telegram_bot():
    if BOT_TOKEN:
        import threading
        from bot_handler import run_bot
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        print("[main] Started Telegram bot polling in a background thread.")

def calculate_user_credibility(user_id: int, db: Session, depth: int = 0) -> int:
    """
    Each user builds a hidden credibility score based on:
    - Ratio of verified vs disverified posts (smoothed with Laplace)
    - Quality and consistency of contributions (+1 per comment on other users' topics, max +10)
    Capped between 10 and 100.
    """
    if depth >= 2:
        return 50

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return 50

    topics = db.query(Topic).filter(Topic.user_id == user_id).all()
    n_verified = 0
    n_disverified = 0

    for t in topics:
        status, _, _ = classify_topic(t.id, db, depth=depth)
        if status == "Verified (trusted)":
            n_verified += 1
        elif status == "Disverified (rejected)":
            n_disverified += 1

    if n_verified + n_disverified > 0:
        ratio_term = (n_verified - n_disverified) / (n_verified + n_disverified + 2)
        score = 50.0 + 50.0 * ratio_term
    else:
        score = 50.0

    # Quality and consistency bonus: count comments on other users' topics
    comment_count = (
        db.query(Comment)
        .join(Topic, Comment.topic_id == Topic.id)
        .filter(Comment.user_id == user_id, Topic.user_id != user_id)
        .count()
    )
    score += min(comment_count, 10)

    return max(10, min(100, int(round(score))))


def classify_topic(topic_id: int, db: Session, depth: int = 0):
    """
    Classifies a topic dynamically:
    - Sum of weighted verify votes (W_v) and disverify votes (W_d), where weights
      are proportional to voters' credibility: Weight = voter_credibility / 50.0.
    - Classification: Verified (trusted) if W_v - W_d >= 1.5,
                      Disverified (rejected) if W_d - W_v >= 1.5,
                      otherwise Disputed (uncertain).
    """
    from database import VerificationVote
    votes = db.query(VerificationVote).filter(VerificationVote.topic_id == topic_id).all()

    if depth >= 1:
        # Simple unweighted calculation to break cycle/recursion
        v_count = sum(1 for v in votes if v.vote_type == "verify")
        d_count = sum(1 for v in votes if v.vote_type == "disverify")
        if v_count - d_count >= 2:
            return "Verified (trusted)", float(v_count), float(d_count)
        elif d_count - v_count >= 2:
            return "Disverified (rejected)", float(v_count), float(d_count)
        else:
            return "Disputed (uncertain)", float(v_count), float(d_count)

    w_v = 0.0
    w_d = 0.0
    for v in votes:
        cred = calculate_user_credibility(v.user_id, db, depth=depth + 1)
        weight = cred / 50.0
        if v.vote_type == "verify":
            w_v += weight
        else:
            w_d += weight

    if w_v - w_d >= 1.5:
        return "Verified (trusted)", w_v, w_d
    elif w_d - w_v >= 1.5:
        return "Disverified (rejected)", w_v, w_d
    else:
        return "Disputed (uncertain)", w_v, w_d


def check_and_update_pseudonym(user: User, db: Session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Check if 12 hours have passed since pseudonym_updated_at
    if not user.pseudonym_updated_at or (now - user.pseudonym_updated_at) >= timedelta(hours=12):
        adjectives = ["Silent", "Quiet", "Hidden", "Shadow", "Deep", "Bold", "Free", "Wild", "Bright", "Epic", "Magic", "Crypto", "Nova", "Cosmic", "Mystic"]
        nouns = ["Thinker", "Voice", "Echo", "Philosopher", "Dreamer", "Seeker", "Rebel", "Mind", "Nomad", "Wanderer", "Stargazer", "Oracle", "Scribe"]
        random_alias = f"{random.choice(adjectives)}_{random.choice(nouns)}"
        random_suffix = secrets.token_hex(2)

        user.alias = random_alias
        user.username = f"{random_alias}_{random_suffix}"
        user.pseudonym_updated_at = now
        db.commit()


# --- Helper to get authenticated user ---
def get_current_user(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> Optional[User]:
    if not session_token:
        return None
    user = db.query(User).filter(User.session_token == session_token).first()
    if user and user.is_verified:
        check_and_update_pseudonym(user, db)
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

def send_telegram_otp_background(chat_id: str, otp_code: str):
    if BOT_TOKEN:
        try:
            from telegram_bot import send_otp
            send_otp(chat_id, otp_code)
            print(f"[Telegram Bot Background] Sent directly to Chat ID {chat_id}.")
        except Exception as e:
            print(f"[Telegram Bot Error Background] Failed to send message: {e}")

@app.post("/api/auth/otp-request")
def request_otp(
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
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
            if background_tasks:
                background_tasks.add_task(send_telegram_otp_background, user.telegram_chat_id, otp_code)
                print(f"[Telegram Bot] Enqueued direct message to Chat ID {user.telegram_chat_id}.")
            else:
                try:
                    from telegram_bot import send_otp
                    send_otp(user.telegram_chat_id, otp_code)
                    print(f"[Telegram Bot Direct] Sent directly to Chat ID {user.telegram_chat_id}.")
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
    user.pseudonym_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

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

    cred = calculate_user_credibility(user.id, db)

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
            "has_profile": bool(user.username),
            "credibility": cred
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
    user.pseudonym_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    cred = calculate_user_credibility(user.id, db)

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
            "has_profile": True,
            "credibility": cred
        }
    }

@app.get("/api/auth/me")
def get_me(user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"authenticated": False}
    cred = calculate_user_credibility(user.id, db)
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "phone": user.phone,
            "email": user.email,
            "username": user.username,
            "alias": user.alias,
            "belief": user.belief,
            "has_profile": bool(user.username),
            "credibility": cred
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
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    image: Optional[UploadFile] = File(None),
    location: Optional[str] = Form(None),
    allow_download: bool = Form(True),
    selected_frame_index: int = Form(0),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Topic text cannot be empty.")

    image_url = None
    is_video = False
    video_record = None

    if image and image.filename:
        lower_filename = image.filename.lower()
        if (image.content_type and image.content_type.startswith("video/")) or any(lower_filename.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"]):
            is_video = True

        if is_video:
            # Create video record
            video_record = Video(
                user_id=user.id,
                title=image.filename,
                filename=image.filename,
                duration=0.0,
                segments_count=0
            )
            db.add(video_record)
            db.commit()
            db.refresh(video_record)

            # Save raw original video file
            from video_processor import VIDEO_ORIGINAL_DIR, get_video_duration
            original_path = VIDEO_ORIGINAL_DIR / f"{video_record.id}_{image.filename}"
            with open(original_path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)

            # Validate video duration is not greater than 1 minute (60 seconds)
            duration = get_video_duration(str(original_path))
            if duration > 60.1:
                try:
                    original_path.unlink()
                except Exception as e:
                    print(f"Error unlinking video of too long duration: {e}")
                db.delete(video_record)
                db.commit()
                raise HTTPException(status_code=400, detail="Video exceeds the maximum duration limit of 1 minute (60 seconds).")

            # Trigger background segment processing and thumbnail extraction
            background_tasks.add_task(
                background_video_processing,
                video_record.id,
                image.filename,
                SessionLocal,
                selected_frame_index
            )
        else:
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

    # Link video to topic
    if video_record:
        video_record.topic_id = topic.id
        db.commit()
        db.refresh(video_record)

    video_response = None
    if video_record:
        video_response = {
            "id": video_record.id,
            "title": video_record.title,
            "filename": video_record.filename,
            "duration": video_record.duration,
            "segments_count": video_record.segments_count
        }

    cred = calculate_user_credibility(user.id, db)

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
            "video": video_response,
            "author": {
                "id": user.id,
                "username": user.username or "Anonymous",
                "belief": user.belief or "",
                "credibility": cred
            },
            "verification_status": "Disputed (uncertain)",
            "verify_count": 0,
            "disverify_count": 0,
            "user_vote": None
        }
    }

@app.get("/api/topics")
def get_topics(db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active_topics = db.query(Topic).filter(Topic.expires_at > now_naive).all()

    active_topics = sorted(active_topics, key=lambda t: t.created_at, reverse=True)

    topics_with_counts = []
    max_comments = 0

    from database import VerificationVote

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

        video_data = None
        if t.videos:
            v = t.videos[0]
            video_data = {
                "id": v.id,
                "title": v.title,
                "filename": v.filename,
                "duration": v.duration,
                "segments_count": v.segments_count
            }

        status, _, _ = classify_topic(t.id, db)
        actual_verify = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.vote_type == "verify").count()
        actual_disverify = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.vote_type == "disverify").count()

        user_vote = None
        if current_user:
            vote_obj = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.user_id == current_user.id).first()
            if vote_obj:
                user_vote = vote_obj.vote_type

        author_cred = calculate_user_credibility(t.user_id, db)

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
            "video": video_data,
            "author": {
                "id": t.author.id,
                "username": t.author.username or "Anonymous",
                "belief": t.author.belief or "",
                "credibility": author_cred
            },
            "verification_status": status,
            "verify_count": actual_verify,
            "disverify_count": actual_disverify,
            "user_vote": user_vote
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
def get_trending_topics(db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active_topics = db.query(Topic).filter(Topic.expires_at > now_naive).all()

    sorted_topics = sorted(active_topics, key=lambda t: (len(t.comments), t.created_at), reverse=True)

    trending = []
    for t in sorted_topics[:5]:
        from database import VerificationVote
        status, _, _ = classify_topic(t.id, db)
        actual_verify = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.vote_type == "verify").count()
        actual_disverify = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.vote_type == "disverify").count()
        user_vote = None
        if current_user:
            vote_obj = db.query(VerificationVote).filter(VerificationVote.topic_id == t.id, VerificationVote.user_id == current_user.id).first()
            if vote_obj:
                user_vote = vote_obj.vote_type

        trending.append({
            "id": t.id,
            "text": t.text,
            "comments_count": len(t.comments),
            "image_url": t.image_url,
            "location": t.location,
            "author": {
                "id": t.author.id,
                "username": t.author.username or "Anonymous",
                "credibility": calculate_user_credibility(t.user_id, db)
            },
            "verification_status": status,
            "verify_count": actual_verify,
            "disverify_count": actual_disverify,
            "user_vote": user_vote
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

@app.post("/api/topics/{topic_id}/vote")
def vote_topic(
    topic_id: int,
    vote_type: str = Form(...),
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    from database import VerificationVote
    vote_type = vote_type.strip().lower()
    if vote_type not in ["verify", "disverify"]:
        raise HTTPException(status_code=400, detail="Invalid vote type. Must be 'verify' or 'disverify'.")

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if now_naive > topic.expires_at:
        raise HTTPException(status_code=400, detail="This topic has expired and cannot be voted on.")

    # Check for existing vote
    existing_vote = db.query(VerificationVote).filter(
        VerificationVote.topic_id == topic_id,
        VerificationVote.user_id == user.id
    ).first()

    if existing_vote:
        if existing_vote.vote_type == vote_type:
            # Retract vote if they click their active vote type again
            db.delete(existing_vote)
            db.commit()
            action = "retracted"
        else:
            # Change vote type if they click the other option
            existing_vote.vote_type = vote_type
            db.commit()
            action = "changed"
    else:
        # Cast new vote
        new_vote = VerificationVote(
            user_id=user.id,
            topic_id=topic_id,
            vote_type=vote_type
        )
        db.add(new_vote)
        db.commit()
        action = "cast"

    # Re-classify topic and return updated counts and status
    status_str, w_v, w_d = classify_topic(topic_id, db)
    actual_verify = db.query(VerificationVote).filter(VerificationVote.topic_id == topic_id, VerificationVote.vote_type == "verify").count()
    actual_disverify = db.query(VerificationVote).filter(VerificationVote.topic_id == topic_id, VerificationVote.vote_type == "disverify").count()

    return {
        "success": True,
        "message": f"Vote {action} successfully.",
        "action": action,
        "verification_status": status_str,
        "verify_count": actual_verify,
        "disverify_count": actual_disverify,
        "user_vote": vote_type if action != "retracted" else None
    }


# --- Video Streaming and Thumbnail Endpoints ---

@app.get("/api/videos/{video_id}/segments/{segment_index}")
def get_video_segment(video_id: int, segment_index: int, db: Session = Depends(get_db)):
    """
    Returns the specific 60-second segment (.mp4 chunk) for a processed video.
    segment_index is 0-based.
    """
    # Verify video exists
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    from video_processor import VIDEO_SEGMENT_DIR
    filename = VIDEO_SEGMENT_DIR / f"{video_id}_{segment_index:03d}.mp4"
    if not filename.exists():
        raise HTTPException(status_code=404, detail=f"Segment {segment_index} not found for video {video_id}.")

    return FileResponse(filename, media_type="video/mp4")

@app.get("/api/videos/{video_id}/thumbnails/{time_index}")
def get_video_thumbnail(video_id: int, time_index: int, db: Session = Depends(get_db)):
    """
    Returns the preview frame thumbnail image at the designated time_index (1-based).
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    from video_processor import VIDEO_THUMBNAIL_DIR
    filename = VIDEO_THUMBNAIL_DIR / f"{video_id}_{time_index:03d}.jpg"
    if not filename.exists():
        # Fallback to the first thumbnail if available
        fallback = VIDEO_THUMBNAIL_DIR / f"{video_id}_001.jpg"
        if fallback.exists():
            return FileResponse(fallback, media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="Thumbnail not found.")

    return FileResponse(filename, media_type="image/jpeg")

@app.get("/api/videos/{video_id}/metadata")
def get_video_metadata(video_id: int, db: Session = Depends(get_db)):
    """
    Returns metadata (duration, segments count) for the specified video.
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    return {
        "success": True,
        "video": {
            "id": video.id,
            "title": video.title,
            "duration": video.duration,
            "segments_count": video.segments_count,
            "created_at": video.created_at.isoformat()
        }
    }
