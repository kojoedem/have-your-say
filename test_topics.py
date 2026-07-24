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

def test_update_topic():
    # Setup owner and non-owner
    create_and_verify_user("+15551112222", "owner_user", "Believer")
    resp = client.post("/api/topics", data={"text": "Original Topic Text", "location": "NYC"})
    topic_id = resp.json()["topic"]["id"]

    # Verify original values
    topics = client.get("/api/topics").json()["topics"]
    assert topics[0]["text"] == "Original Topic Text"
    assert topics[0]["allow_download"] is True

    # 1. Update topic as owner
    update_resp = client.put(f"/api/topics/{topic_id}", data={"text": "Updated Topic Text", "allow_download": "false"})
    assert update_resp.status_code == 200
    assert update_resp.json()["success"] is True

    # Check updated values
    topics = client.get("/api/topics").json()["topics"]
    assert topics[0]["text"] == "Updated Topic Text"
    assert topics[0]["allow_download"] is False

    # 2. Update as non-owner (different user)
    create_and_verify_user("+15553334444", "stranger_user", "Skeptic")
    bad_update_resp = client.put(f"/api/topics/{topic_id}", data={"text": "Hacked!", "allow_download": "true"})
    assert bad_update_resp.status_code == 403


def test_delete_topic():
    create_and_verify_user("+15555556666", "owner_two", "Code")
    resp = client.post("/api/topics", data={"text": "Topic to delete"})
    topic_id = resp.json()["topic"]["id"]

    # Add a comment to it
    client.post(f"/api/topics/{topic_id}/comments", data={"text": "A comment"})

    # Try deleting as stranger
    create_and_verify_user("+15557778888", "stranger_two", "No Code")
    bad_delete = client.delete(f"/api/topics/{topic_id}")
    assert bad_delete.status_code == 403

    # Authenticate back as owner
    create_and_verify_user("+15555556666", "owner_two", "Code")
    ok_delete = client.delete(f"/api/topics/{topic_id}")
    assert ok_delete.status_code == 200

    # Verify topic and its comments are deleted
    topics = client.get("/api/topics").json()["topics"]
    assert len(topics) == 0


def test_update_comment():
    create_and_verify_user("+15551113333", "topic_author", "Idea")
    topic_resp = client.post("/api/topics", data={"text": "A Topic"})
    topic_id = topic_resp.json()["topic"]["id"]

    # Create comment as comment_author
    create_and_verify_user("+15552224444", "comment_author", "Idea 2")
    comment_resp = client.post(f"/api/topics/{topic_id}/comments", data={"text": "Original Comment"})
    comment_id = comment_resp.json()["comment"]["id"]

    # 1. Update comment as author
    update_resp = client.put(f"/api/comments/{comment_id}", data={"text": "Updated Comment Text"})
    assert update_resp.status_code == 200

    # Verify updated text
    topics = client.get("/api/topics").json()["topics"]
    assert topics[0]["comments"][0]["text"] == "Updated Comment Text"

    # 2. Update as non-author
    create_and_verify_user("+15553335555", "stranger_three", "No Idea")
    bad_update = client.put(f"/api/comments/{comment_id}", data={"text": "Hijacked Comment!"})
    assert bad_update.status_code == 403


def test_delete_comment():
    create_and_verify_user("+15551114444", "author_topic", "Idea")
    topic_resp = client.post("/api/topics", data={"text": "A Topic"})
    topic_id = topic_resp.json()["topic"]["id"]

    # Create comment
    create_and_verify_user("+15552225555", "author_comment", "Idea 2")
    comment_resp = client.post(f"/api/topics/{topic_id}/comments", data={"text": "Comment to delete"})
    comment_id = comment_resp.json()["comment"]["id"]

    # 1. Try deleting comment as non-author
    create_and_verify_user("+15553336666", "stranger_four", "No Idea")
    bad_delete = client.delete(f"/api/comments/{comment_id}")
    assert bad_delete.status_code == 403

    # 2. Delete as author
    create_and_verify_user("+15552225555", "author_comment", "Idea 2")
    ok_delete = client.delete(f"/api/comments/{comment_id}")
    assert ok_delete.status_code == 200

    # Verify deleted
    topics = client.get("/api/topics").json()["topics"]
    assert len(topics[0]["comments"]) == 0

def test_create_topic_with_video_processing():
    create_and_verify_user("+15551119999", "videomaker", "Direct video streaming")

    # Mock video file upload
    file_content = b"fake-mp4-video-header-and-body-content"
    video_file = io.BytesIO(file_content)

    resp = client.post(
        "/api/topics",
        data={"text": "Check out this beautiful status clip!", "location": "Sweden"},
        files={"image": ("my_holiday.mp4", video_file, "video/mp4")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["topic"]["text"] == "Check out this beautiful status clip!"
    assert data["topic"]["video"] is not None
    assert data["topic"]["video"]["title"] == "my_holiday.mp4"
    assert data["topic"]["video"]["filename"] == "my_holiday.mp4"

    video_id = data["topic"]["video"]["id"]

    # Try retrieving video metadata
    meta_resp = client.get(f"/api/videos/{video_id}/metadata")
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert meta_data["success"] is True
    assert meta_data["video"]["id"] == video_id
    assert meta_data["video"]["title"] == "my_holiday.mp4"

def test_trim_selected_video_frame_processing():
    from video_processor import trim_selected_video_frame, VIDEO_ORIGINAL_DIR, VIDEO_SEGMENT_DIR, VIDEO_THUMBNAIL_DIR
    import shutil

    video_id = 9999
    filename = "holiday_test.mp4"
    orig_file = VIDEO_ORIGINAL_DIR / f"{video_id}_{filename}"

    # Generate a real short test video to trim
    import subprocess
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(orig_file)
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    assert orig_file.exists()

    # Call trim frame 0
    res = trim_selected_video_frame(video_id, filename, 0)
    assert res is not False
    assert res["segments_count"] == 1
    assert res["duration"] > 0.0

    # Original file must be immediately deleted!
    assert not orig_file.exists()

    # The trimmed segment must exist as 9999_000.mp4
    trimmed_segment = VIDEO_SEGMENT_DIR / f"{video_id}_000.mp4"
    assert trimmed_segment.exists()

    # Clean up generated files
    if trimmed_segment.exists():
        trimmed_segment.unlink()
    for thumb in VIDEO_THUMBNAIL_DIR.glob(f"{video_id}_*.jpg"):
        thumb.unlink()


def test_user_credibility_and_verification_votes():
    # 1. Setup User A (Author) and User B & C (voters)
    create_and_verify_user("+15550000001", "author_user", "Absolute Honesty")

    # User A creates a topic/say
    resp = client.post("/api/topics", data={"text": "This is a claim to verify!"})
    assert resp.status_code == 200
    topic_id = resp.json()["topic"]["id"]

    # Retrieve feed - topic should be "Disputed (uncertain)" by default
    feed_resp = client.get("/api/topics")
    assert feed_resp.json()["topics"][0]["verification_status"] == "Disputed (uncertain)"
    assert feed_resp.json()["topics"][0]["author"]["credibility"] == 50

    # 2. Login as User B and verify topic
    create_and_verify_user("+15550000002", "voter_b", "Verification is good")
    vote_resp = client.post(f"/api/topics/{topic_id}/vote", data={"vote_type": "verify"})
    assert vote_resp.status_code == 200
    assert vote_resp.json()["verification_status"] == "Disputed (uncertain)" # W_v - W_d = 1.0 (requires >= 1.5)

    # 3. Login as User C and verify topic
    create_and_verify_user("+15550000003", "voter_c", "Truth is good")
    vote_resp2 = client.post(f"/api/topics/{topic_id}/vote", data={"vote_type": "verify"})
    assert vote_resp2.status_code == 200
    assert vote_resp2.json()["verification_status"] == "Verified (trusted)" # W_v - W_d = 2.0 >= 1.5

    # Check updated feed
    feed_resp2 = client.get("/api/topics")
    assert feed_resp2.json()["topics"][0]["verification_status"] == "Verified (trusted)"
    # User A (Author) has their say verified, so their credibility should increase!
    assert feed_resp2.json()["topics"][0]["author"]["credibility"] > 50


def test_periodic_pseudonym_rotation():
    phone = "+15558881234"
    create_and_verify_user(phone, "initial_alias", "My belief statement")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        assert user is not None
        assert user.alias == "initial_alias"

        # Simulate that 12 hours have passed since the last pseudonym update
        user.pseudonym_updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=13)
        db.commit()

        # Call get /api/auth/me to trigger automatic rotation in get_current_user
        me_resp = client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["authenticated"] is True

        rotated_username = me_resp.json()["user"]["username"]
        assert rotated_username != "initial_alias"
        assert rotated_username is not None
    finally:
        db.close()


def test_weighted_vote_influence():
    # User A is the author
    create_and_verify_user("+15559990001", "author_weight", "Claim Creator")
    topic_id = client.post("/api/topics", data={"text": "Weight test claim"}).json()["topic"]["id"]

    # Voter B has low credibility (e.g. they have disverified topics/says, or just base 50)
    create_and_verify_user("+15559990002", "voter_b", "Normal voter")
    # Voter C has high credibility (by having 2 verified topics/says under their belt)
    create_and_verify_user("+15559990003", "voter_c", "Trusted sentinel")

    # Let's verify voter_c's posts using Voter B
    topic_c1 = client.post("/api/topics", data={"text": "Sentinel claim 1"}).json()["topic"]["id"]
    topic_c2 = client.post("/api/topics", data={"text": "Sentinel claim 2"}).json()["topic"]["id"]

    # B verifies C1 & C2
    create_and_verify_user("+15559990002", "voter_b", "Normal voter")
    client.post(f"/api/topics/{topic_c1}/vote", data={"vote_type": "verify"})
    client.post(f"/api/topics/{topic_c2}/vote", data={"vote_type": "verify"})

    # Let's add some more verifications from other users to ensure C's claims are Verified
    for i in range(2):
        create_and_verify_user(f"+1555999200{i}", f"helper_{i}", "Help")
        client.post(f"/api/topics/{topic_c1}/vote", data={"vote_type": "verify"})
        client.post(f"/api/topics/{topic_c2}/vote", data={"vote_type": "verify"})

    # Voter C's credibility score should now be high! Let's check it:
    db = SessionLocal()
    try:
        user_c = db.query(User).filter(User.phone == "+15559990003").first()
        from main import calculate_user_credibility
        cred_c = calculate_user_credibility(user_c.id, db)
        assert cred_c > 50  # Sentiment/Laplace smoothing makes it higher than 50
    finally:
        db.close()

    # Voter C disverifies the target claim
    create_and_verify_user("+15559990003", "voter_c", "Trusted sentinel")
    vote_resp = client.post(f"/api/topics/{topic_id}/vote", data={"vote_type": "disverify"})
    # Since C has high credibility (weight > 1.0), their single vote is worth more and can classify the post!
    assert vote_resp.status_code == 200
    assert vote_resp.json()["verification_status"] == "Disverified (rejected)"
