from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch
from main import app
from database import Base, engine, SessionLocal, User

# Use TestClient for fastapi testing
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    # Clear and recreate database tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_request_otp():
    response = client.post("/api/auth/otp-request", data={"phone": "+15551234567"})
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    # If the user is not linked yet, it will return a redirect with telegram link
    assert "status" in json_data
    assert json_data["status"] == "redirect"
    assert "telegram_link" in json_data
    assert "otp_code" in json_data
    assert len(json_data["otp_code"]) == 6

def test_verify_otp_success_and_fail():
    # 1. Request OTP (returns redirect for unlinked, but generates OTP code)
    req_resp = client.post("/api/auth/otp-request", data={"phone": "+15559876543"})
    assert req_resp.status_code == 200
    otp_code = req_resp.json()["otp_code"]

    # 2. Try verifying with wrong OTP
    verify_wrong = client.post("/api/auth/otp-verify", data={"phone": "+15559876543", "code": "000000"})
    assert verify_wrong.status_code == 400
    assert "Invalid OTP code" in verify_wrong.json()["detail"]

    # 3. Verify with correct OTP
    verify_ok = client.post("/api/auth/otp-verify", data={"phone": "+15559876543", "code": otp_code})
    assert verify_ok.status_code == 200
    data = verify_ok.json()
    assert data["success"] is True
    assert data["user"]["phone"] == "+15559876543"
    assert data["user"]["has_profile"] is True

    # Check cookies
    cookies = verify_ok.cookies
    assert "session_token" in cookies
    assert len(cookies["session_token"]) == 64

def test_update_profile_and_get_me():
    # 1. Request & Verify OTP
    req_resp = client.post("/api/auth/otp-request", data={"phone": "+15550001111"})
    otp_code = req_resp.json()["otp_code"]

    # We must maintain the cookie session so we can request other endpoints
    client.post("/api/auth/otp-verify", data={"phone": "+15550001111", "code": otp_code})

    # 2. Check current user /me
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["authenticated"] is True
    assert me_resp.json()["user"]["has_profile"] is True

    # 3. Set Profile
    prof_resp = client.post("/api/auth/profile", data={"username": "jules", "belief": "Honesty & Code Quality"})
    assert prof_resp.status_code == 200
    assert prof_resp.json()["user"]["username"].startswith("jules_")
    assert prof_resp.json()["user"]["alias"] == "jules"
    assert prof_resp.json()["user"]["belief"] == "Honesty & Code Quality"
    assert prof_resp.json()["user"]["has_profile"] is True

    # 4. Check /me again
    me_resp = client.get("/api/auth/me")
    assert me_resp.json()["user"]["username"].startswith("jules_")
    assert me_resp.json()["user"]["alias"] == "jules"
    assert me_resp.json()["user"]["belief"] == "Honesty & Code Quality"

def test_logout():
    # 1. Login
    req_resp = client.post("/api/auth/otp-request", data={"phone": "+15552223333"})
    otp_code = req_resp.json()["otp_code"]
    client.post("/api/auth/otp-verify", data={"phone": "+15552223333", "code": otp_code})

    # Verify we are logged in
    assert client.get("/api/auth/me").json()["authenticated"] is True

    # 2. Logout
    client.post("/api/auth/logout")

    # Verify we are logged out
    assert client.get("/api/auth/me").json()["authenticated"] is False


# --- New Tests for Telegram/Email Auth Features ---

def test_email_request_and_verify_success():
    with patch("main.send_email_otp", return_value=(True, "")) as mock_send_email:
        # 1. Request OTP via email
        response = client.post("/api/auth/otp-request", data={"email": "alice@example.com"})
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["email"] == "alice@example.com"
        assert "otp_code" not in json_data  # Ensure mocked otp_code retrieval is removed for Email

        # Fetch otp_code directly from database for testing
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == "alice@example.com").first()
            assert user is not None
            otp_code = user.otp_code
            assert otp_code is not None
        finally:
            db.close()

        # Verify SMTP sender function is executed with proper arguments
        mock_send_email.assert_called_once_with("alice@example.com", otp_code)

        # 2. Verify OTP with email
        verify_resp = client.post("/api/auth/otp-verify", data={"email": "alice@example.com", "code": otp_code})
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["success"] is True
        assert data["user"]["email"] == "alice@example.com"
        assert data["user"]["phone"] is None

        # Check session cookie is set
        assert "session_token" in verify_resp.cookies

        # 3. Access current user /me and verify email is in response
        me_resp = client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["authenticated"] is True
        assert me_resp.json()["user"]["email"] == "alice@example.com"


def test_request_validation_errors():
    # 1. Request with neither phone nor email (missing fields)
    response = client.post("/api/auth/otp-request", data={})
    assert response.status_code == 400
    assert "required" in response.json()["detail"]

    # 2. Request with empty strings
    response_400 = client.post("/api/auth/otp-request", data={"phone": "", "email": ""})
    assert response_400.status_code == 400
    assert "required" in response_400.json()["detail"]


def test_telegram_deep_link_redirect_flow():
    phone_number = "+15556667777"

    # 1. Request OTP for unlinked user -> expect "redirect"
    req_resp = client.post("/api/auth/otp-request", data={"phone": phone_number})
    assert req_resp.status_code == 200
    data = req_resp.json()
    assert data["status"] == "redirect"
    assert "telegram_link" in data
    assert f"login_{phone_number}" in data["telegram_link"]

    # 2. Simulate Telegram bot linking by directly setting telegram_chat_id in database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone_number).first()
        assert user is not None
        assert user.telegram_chat_id is None

        # Link the account with mock chat_id
        user.telegram_chat_id = "123456789"
        db.commit()
    finally:
        db.close()

    # 3. Request OTP again -> expect standard success (no redirect) since account is now linked
    req_resp2 = client.post("/api/auth/otp-request", data={"phone": phone_number})
    assert req_resp2.status_code == 200
    data2 = req_resp2.json()
    assert "status" not in data2
    assert "message" in data2
    assert "OTP sent successfully" in data2["message"]


@pytest.mark.anyio
async def test_bot_start_handler_linking():
    from bot_handler import start

    phone_number = "+15558889999"
    chat_id = 987654321

    # 1. Mock Update and Context
    class MockMessage:
        def __init__(self):
            self.text = None
        async def reply_text(self, text: str):
            self.text = text

    class MockChat:
        def __init__(self, cid):
            self.id = cid

    class MockUpdate:
        def __init__(self, cid):
            self.effective_chat = MockChat(cid)
            self.message = MockMessage()

    class MockContext:
        def __init__(self, args):
            self.args = args

    update = MockUpdate(chat_id)
    context = MockContext([f"login_{phone_number}"])

    # 2. Call the bot handler
    await start(update, context)

    # 3. Verify reply
    assert update.message.text is not None
    assert "linked successfully" in update.message.text
    assert "Your OTP code is" in update.message.text

    # 4. Verify user was created and linked in the database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone_number).first()
        assert user is not None
        assert user.telegram_chat_id == str(chat_id)
        assert user.otp_code is not None
        assert len(user.otp_code) == 6
    finally:
        db.close()
