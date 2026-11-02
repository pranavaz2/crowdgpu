"""
Security, Reliability, and Hardening Regression Tests for CrowdGPU Stage 6.

Validates:
- Production mode refuses demo_auth_enabled=True.
- Production mode refuses default secret_key.
- Production mode refuses default database_url credentials.
- Production mode rejects requests missing X-User-Id without falling back to demo user.
- WebRTC signaling requires HMAC token proof in production mode.
- Rate limiting protects signaling from abusive message floods.
- Signaling rejects self-directed messages.
- Worker peer identity cannot be spoofed across different peer IDs.
"""

import hashlib
import hmac
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from coordinator.config import Settings
from coordinator.main import app
from coordinator.signaling.router import generate_signaling_token


# ---------------------------------------------------------------------------
# 1. Configuration & Production Invariants
# ---------------------------------------------------------------------------

def test_production_mode_refuses_demo_auth():
    """Setting demo_auth_enabled=True in production environment raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment="production",
            demo_auth_enabled=True,
            secret_key="a-sufficiently-secure-custom-key-12345",
            database_url="postgresql+asyncpg://admin:StrongPassword123@db.prod.internal:5432/crowdgpu",
        )
    assert "demo_auth_enabled cannot be enabled in production" in str(exc_info.value)


def test_production_mode_refuses_default_secret_key():
    """Default 'changeme' secret key is strictly prohibited in production."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment="production",
            demo_auth_enabled=False,
            secret_key="changeme-replace-with-a-secure-random-key-in-production",
            database_url="postgresql+asyncpg://admin:StrongPassword123@db.prod.internal:5432/crowdgpu",
        )
    assert "default secret_key cannot be used in production" in str(exc_info.value)


def test_production_mode_refuses_default_database_credentials():
    """Default 'changeme' database credentials are strictly prohibited in production."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment="production",
            demo_auth_enabled=False,
            secret_key="a-sufficiently-secure-custom-key-12345",
            database_url="postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu",
        )
    assert "default database credentials cannot be used in production" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. Authentication: Production Mode Refuses Demo Identity Fallbacks
# ---------------------------------------------------------------------------

def test_production_mode_refuses_missing_x_user_id(monkeypatch):
    """When environment is production, missing X-User-Id yields 401 even if demo_auth was configured."""
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", True)

    client = TestClient(app)
    response = client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert "Missing required header: X-User-Id" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Worker Peer Authorization & Anti-Impersonation
# ---------------------------------------------------------------------------

def test_worker_polling_rejects_peer_id_mismatch():
    """A caller presenting X-Peer-Id of Peer B cannot query jobs/next for Peer A."""
    client = TestClient(app)
    target_peer_id = "11111111-1111-1111-1111-111111111111"
    imposter_peer_id = "22222222-2222-2222-2222-222222222222"

    response = client.get(
        f"/api/v1/workers/{target_peer_id}/jobs/next",
        headers={"X-Peer-Id": imposter_peer_id},
    )
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


def test_worker_heartbeat_rejects_peer_id_mismatch():
    """A caller presenting X-Peer-Id of Peer B cannot update heartbeat for Peer A."""
    client = TestClient(app)
    target_peer_id = "11111111-1111-1111-1111-111111111111"
    imposter_peer_id = "22222222-2222-2222-2222-222222222222"

    response = client.post(
        f"/api/v1/workers/{target_peer_id}/heartbeat",
        headers={"X-Peer-Id": imposter_peer_id},
    )
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. WebRTC Signaling Hardening: Tokens, Self-Relay & Rate Limiting
# ---------------------------------------------------------------------------

def test_signaling_token_validation_in_production(monkeypatch):
    """In production mode, unauthenticated signaling connections are closed with 1008."""
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")

    client = TestClient(app)

    # Attempt connection without token receives error and closes
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=unauthenticated-peer") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "UNAUTHORIZED"

    # Connection with valid HMAC token succeeds
    valid_token = generate_signaling_token("authenticated-peer")
    with client.websocket_connect(f"/api/v1/signaling/ws?peer_id=authenticated-peer&token={valid_token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "registered"
        assert msg["peer_id"] == "authenticated-peer"


def test_signaling_rejects_self_directed_messages():
    """A peer cannot relay signaling messages to its own ID."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=self-sender") as ws:
        ws.receive_json()

        ws.send_json({
            "type": "offer",
            "target_id": "self-sender",
            "payload": {"sdp": "v=0\r\no=test\r\ns=-\r\n"},
        })
        err_msg = ws.receive_json()
        assert err_msg["type"] == "error"
        assert "Cannot send signaling messages to self" in err_msg["message"]


def test_signaling_rate_limiting(monkeypatch):
    """Flooding signaling gateway with rapid messages triggers RATE_LIMITED error."""
    from coordinator.config import settings
    monkeypatch.setattr(settings, "signaling_rate_limit_per_minute", 5)

    client = TestClient(app)
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=rate-limit-peer") as ws:
        ws.receive_json()

        rate_limited_hit = False
        for _ in range(10):
            ws.send_json({"type": "ping"})
            res = ws.receive_json()
            if res.get("code") == "RATE_LIMITED":
                rate_limited_hit = True
                break

        assert rate_limited_hit is True


# ---------------------------------------------------------------------------
# 5. Stage 7 Identity Authentication & Impersonation Prevention
# ---------------------------------------------------------------------------

def test_production_mode_rejects_user_header_spoofing_without_token(monkeypatch):
    """In production mode, supplying X-User-Id without a valid token is rejected with 401."""
    import uuid
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    victim_user_id = str(uuid.uuid4())
    res = client.get("/api/v1/jobs", headers={"X-User-Id": victim_user_id})
    assert res.status_code == 401
    assert "User authentication token required in production" in res.json()["detail"]


def test_production_mode_rejects_forged_user_token(monkeypatch):
    """In production mode, supplying an invalid/forged token is rejected with 403."""
    import uuid
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    victim_user_id = str(uuid.uuid4())
    res = client.get(
        "/api/v1/jobs",
        headers={
            "X-User-Id": victim_user_id,
            "X-User-Token": "forged-token-999999999999999999999999",
        },
    )
    assert res.status_code == 403
    assert "Invalid user authentication credential" in res.json()["detail"]


def test_production_mode_accepts_valid_user_token(monkeypatch):
    """In production mode, a legitimate user presenting an HMAC token succeeds."""
    import uuid
    from coordinator.config import settings
    from coordinator.core.auth import generate_user_token
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    legit_user = uuid.UUID(settings.demo_user_id)
    token = generate_user_token(legit_user)

    res = client.get(
        "/api/v1/jobs",
        headers={
            "X-User-Id": str(legit_user),
            "X-User-Token": token,
        },
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_production_mode_rejects_worker_without_token(monkeypatch):
    """In production mode, worker job polling without token is rejected with 401."""
    import uuid
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    peer_id = str(uuid.uuid4())
    res = client.get(
        f"/api/v1/workers/{peer_id}/jobs/next",
        headers={"X-Peer-Id": peer_id},
    )
    assert res.status_code == 401
    assert "Worker authentication token required" in res.json()["detail"]


def test_production_mode_rejects_worker_with_forged_token(monkeypatch):
    """In production mode, worker polling with forged token is rejected with 403."""
    import uuid
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    peer_id = str(uuid.uuid4())
    res = client.get(
        f"/api/v1/workers/{peer_id}/jobs/next",
        headers={
            "X-Peer-Id": peer_id,
            "X-Peer-Token": "forged-worker-token-xyz",
        },
    )
    assert res.status_code == 403
    assert "Invalid worker authentication token" in res.json()["detail"]


def test_worker_cannot_impersonate_another_peer_with_own_token():
    """Worker A cannot use its valid token to poll jobs or update status for Worker B."""
    import uuid
    from coordinator.core.auth import generate_worker_token

    peer_a = uuid.uuid4()
    peer_b = uuid.uuid4()
    token_a = generate_worker_token(peer_a)

    client = TestClient(app)

    # 1. Worker A supplies Peer A token but claims Peer B in URL path
    res = client.get(
        f"/api/v1/workers/{peer_b}/jobs/next",
        headers={
            "X-Peer-Id": str(peer_b),
            "X-Peer-Token": token_a,  # Token for Peer A, not B
        },
    )
    assert res.status_code == 403
    assert "Invalid worker authentication token" in res.json()["detail"]

    # 2. Worker A supplies Peer A in header and token A, but targets Peer B in URL path
    res2 = client.get(
        f"/api/v1/workers/{peer_b}/jobs/next",
        headers={
            "X-Peer-Id": str(peer_a),
            "X-Peer-Token": token_a,
        },
    )
    assert res2.status_code == 403
    assert "Forbidden" in res2.json()["detail"]


def test_production_mode_rejects_result_submission_without_token(monkeypatch):
    """In production mode, submitting a job result without worker token is rejected with 401."""
    import uuid
    from coordinator.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "demo_auth_enabled", False)

    client = TestClient(app)
    job_id = str(uuid.uuid4())
    peer_id = str(uuid.uuid4())
    res = client.post(
        f"/api/v1/jobs/{job_id}/result",
        json={"status": "completed", "output": {"result": 42}},
        headers={"X-Peer-Id": peer_id},
    )
    assert res.status_code == 401
    assert "Worker authentication token required" in res.json()["detail"]

