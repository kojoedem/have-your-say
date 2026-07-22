from fastapi.testclient import TestClient
import pytest
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
    assert json_data["phone"] == "+15551234567"
    assert "otp_code" in json_data
    assert len(json_data["otp_code"]) == 6

def test_verify_otp_success_and_fail():
    # 1. Request OTP
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
    assert data["user"]["has_profile"] is False

    # Check cookies
    cookies = verify_ok.cookies
    assert "session_phone" in cookies
    assert cookies["session_phone"] == "+15559876543"

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
    assert me_resp.json()["user"]["has_profile"] is False

    # 3. Set Profile
    prof_resp = client.post("/api/auth/profile", data={"username": "jules", "belief": "Honesty & Code Quality"})
    assert prof_resp.status_code == 200
    assert prof_resp.json()["user"]["username"] == "jules"
    assert prof_resp.json()["user"]["belief"] == "Honesty & Code Quality"
    assert prof_resp.json()["user"]["has_profile"] is True

    # 4. Check /me again
    me_resp = client.get("/api/auth/me")
    assert me_resp.json()["user"]["username"] == "jules"
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
