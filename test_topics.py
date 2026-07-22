import io
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
import pytest
from main import app
from database import Base, engine, SessionLocal, User, Topic, Comment

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def create_and_verify_user(phone, username="tester", belief="Testing is cool"):
    req_resp = client.post("/api/auth/otp-request", data={"phone": phone})
    otp_code = req_resp.json()["otp_code"]
    client.post("/api/auth/otp-verify", data={"phone": phone, "code": otp_code})
    client.post("/api/auth/profile", data={"username": username, "belief": belief})

def test_create_topic_no_image():
    create_and_verify_user("+15551111111", "writer", "Freedom of speech")

    resp = client.post("/api/topics", data={"text": "This is a new say!", "location": "Canada"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["topic"]["text"] == "This is a new say!"
    assert data["topic"]["image_url"] is None
    assert data["topic"]["location"] == "Canada"

def test_create_topic_with_image():
    create_and_verify_user("+15552222222", "photographer", "Art & Design")

    # Mock an image file upload
    file_data = b"fake-image-bytes"
    image_file = io.BytesIO(file_data)

    resp = client.post(
        "/api/topics",
        data={"text": "A beautiful view", "location": "France"},
        files={"image": ("test.png", image_file, "image/png")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["topic"]["text"] == "A beautiful view"
    assert data["topic"]["image_url"].startswith("/static/uploads/")
    assert data["topic"]["location"] == "France"

def test_get_topics_and_progress_bars():
    create_and_verify_user("+15553333333", "user1", "I believe in cats")

    resp_a = client.post("/api/topics", data={"text": "Topic A", "location": "USA"})
    topic_a_id = resp_a.json()["topic"]["id"]

    resp_b = client.post("/api/topics", data={"text": "Topic B", "location": "Mexico"})
    topic_b_id = resp_b.json()["topic"]["id"]

    get_resp = client.get("/api/topics")
    topics = get_resp.json()["topics"]
    assert len(topics) == 2
    assert topics[0]["progress_percent"] == 0
    assert topics[1]["progress_percent"] == 0

    # Add comment with location
    client.post(f"/api/topics/{topic_b_id}/comments", data={"text": "Awesome Topic B!", "location": "United Kingdom"})

    get_resp = client.get("/api/topics")
    topics = get_resp.json()["topics"]
    topic_b_data = next(t for t in topics if t["id"] == topic_b_id)
    topic_a_data = next(t for t in topics if t["id"] == topic_a_id)

    assert topic_b_data["comments_count"] == 1
    assert topic_b_data["progress_percent"] == 100
    assert topic_b_data["comments"][0]["location"] == "United Kingdom"

    assert topic_a_data["comments_count"] == 0
    assert topic_a_data["progress_percent"] == 0

    # Add more comments to Topic A
    client.post(f"/api/topics/{topic_a_id}/comments", data={"text": "Comment A1", "location": "Germany"})
    client.post(f"/api/topics/{topic_a_id}/comments", data={"text": "Comment A2", "location": "Japan"})

    get_resp = client.get("/api/topics")
    topics = get_resp.json()["topics"]
    topic_b_data = next(t for t in topics if t["id"] == topic_b_id)
    topic_a_data = next(t for t in topics if t["id"] == topic_a_id)

    assert topic_a_data["comments_count"] == 2
    assert topic_a_data["progress_percent"] == 100
    assert topic_a_data["comments"][0]["location"] == "Germany"
    assert topic_a_data["comments"][1]["location"] == "Japan"

    assert topic_b_data["comments_count"] == 1
    assert topic_b_data["progress_percent"] == 50

def test_trending_topics():
    create_and_verify_user("+15554444444", "user2", "I believe in dogs")

    topic1 = client.post("/api/topics", data={"text": "Topic 1"}).json()["topic"]["id"]
    topic2 = client.post("/api/topics", data={"text": "Topic 2"}).json()["topic"]["id"]
    topic3 = client.post("/api/topics", data={"text": "Topic 3"}).json()["topic"]["id"]

    client.post(f"/api/topics/{topic3}/comments", data={"text": "a", "location": "Spain"})
    client.post(f"/api/topics/{topic3}/comments", data={"text": "b", "location": "Italy"})
    client.post(f"/api/topics/{topic3}/comments", data={"text": "c", "location": "Brazil"})
    client.post(f"/api/topics/{topic1}/comments", data={"text": "x", "location": "USA"})

    resp = client.get("/api/trending")
    assert resp.status_code == 200
    trending = resp.json()["trending"]
    assert len(trending) == 3
    assert trending[0]["id"] == topic3
    assert trending[0]["comments_count"] == 3
    assert trending[1]["id"] == topic1
    assert trending[1]["comments_count"] == 1
    assert trending[2]["id"] == topic2
    assert trending[2]["comments_count"] == 0

def test_expired_topic_filtering_and_comments():
    db = SessionLocal()
    try:
        user = User(phone="+15559999999", username="time_traveler", belief="History", is_verified=True)
        db.add(user)
        db.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_topic = Topic(
            user_id=user.id,
            text="Old topic from yesterday",
            created_at=now - timedelta(hours=15),
            expires_at=now - timedelta(hours=3),
            location="History Channel"
        )
        active_topic = Topic(
            user_id=user.id,
            text="Fresh active topic",
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=11),
            location="Present Day"
        )
        db.add(expired_topic)
        db.add(active_topic)
        db.commit()

        client.post("/api/auth/otp-request", data={"phone": "+15559999999"})
        db.refresh(user)
        client.post("/api/auth/otp-verify", data={"phone": "+15559999999", "code": user.otp_code})

        comment_resp = client.post(f"/api/topics/{expired_topic.id}/comments", data={"text": "Should fail", "location": "Nowhere"})
        assert comment_resp.status_code == 400
        assert "expired" in comment_resp.json()["detail"]

        get_resp = client.get("/api/topics")
        active_list = get_resp.json()["topics"]
        assert len(active_list) == 1
        assert active_list[0]["id"] == active_topic.id
        assert active_list[0]["location"] == "Present Day"

    finally:
        db.close()

def test_nested_comments_and_pinning():
    # 1. Register user
    create_and_verify_user("+15557777777", "nested_user", "Testing tree comments")

    # 2. Create Topic
    topic_resp = client.post("/api/topics", data={"text": "Parent Topic"})
    topic_id = topic_resp.json()["topic"]["id"]

    # 3. Create two top-level comments (Parent A, Parent B)
    comment_a = client.post(f"/api/topics/{topic_id}/comments", data={"text": "Parent A"}).json()["comment"]["id"]
    comment_b = client.post(f"/api/topics/{topic_id}/comments", data={"text": "Parent B"}).json()["comment"]["id"]

    # 4. Reply to Parent B (1 reply)
    client.post(f"/api/topics/{topic_id}/comments", data={"text": "Reply B1", "parent_id": comment_b})

    # 5. Reply to Parent A (2 replies) - making A the most commented (pinned) top-level comment
    client.post(f"/api/topics/{topic_id}/comments", data={"text": "Reply A1", "parent_id": comment_a})
    client.post(f"/api/topics/{topic_id}/comments", data={"text": "Reply A2", "parent_id": comment_a})

    # 6. Retrieve topic and verify nested structure and pinning
    get_resp = client.get("/api/topics")
    topics = get_resp.json()["topics"]
    topic_data = next(t for t in topics if t["id"] == topic_id)

    comments = topic_data["comments"]
    assert len(comments) == 2  # Only 2 top-level comments

    # Comment A should be pinned at index 0 because it has 2 replies
    assert comments[0]["id"] == comment_a
    assert comments[0]["is_pinned"] is True
    assert comments[0]["replies_count"] == 2
    assert len(comments[0]["replies"]) == 2
    assert comments[0]["replies"][0]["text"] == "Reply A1"
    assert comments[0]["replies"][1]["text"] == "Reply A2"

    # Comment B should be at index 1, unpinned
    assert comments[1]["id"] == comment_b
    assert comments[1]["is_pinned"] is False
    assert comments[1]["replies_count"] == 1
    assert len(comments[1]["replies"]) == 1
    assert comments[1]["replies"][0]["text"] == "Reply B1"
