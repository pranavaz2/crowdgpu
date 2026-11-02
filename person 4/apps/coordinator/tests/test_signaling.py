"""
Tests for Coordinator WebRTC Signaling gateway.

Validates:
- WebSocket connection, handshake, and registration (via query param and initial payload)
- Duplicate peer rejection without silent replacement
- Message routing: offer, answer, ice_candidate
- Error handling: unknown recipient, missing target, malformed JSON
- Disconnect cleanup and successful reconnect
- REST endpoints for ICE servers and active peers
"""

import pytest
from starlette.testclient import TestClient

from coordinator.main import app
from coordinator.signaling.manager import signaling_manager


@pytest.fixture(autouse=True)
def cleanup_signaling_registry():
    """Ensure in-memory signaling manager is clean before and after each test."""
    signaling_manager._connections.clear()
    signaling_manager._metadata.clear()
    yield
    signaling_manager._connections.clear()
    signaling_manager._metadata.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_get_ice_servers(client: TestClient):
    """Test retrieving configured ICE servers."""
    response = client.get("/api/v1/signaling/ice-servers")
    assert response.status_code == 200
    data = response.json()
    assert "ice_servers" in data
    assert len(data["ice_servers"]) >= 1
    assert any("stun:" in url for entry in data["ice_servers"] for url in entry["urls"])


def test_get_signaling_peers_initially_empty(client: TestClient):
    """Test connected peers query when no peers are connected."""
    response = client.get("/api/v1/signaling/peers")
    assert response.status_code == 200
    data = response.json()
    assert data["connected_peers"] == []
    assert data["count"] == 0


def test_websocket_register_via_query_param(client: TestClient):
    """Test registering a peer using the ?peer_id= query parameter."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-alpha") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "registered"
        assert msg["peer_id"] == "peer-alpha"

        # Verify listed in REST endpoint
        res = client.get("/api/v1/signaling/peers")
        assert "peer-alpha" in res.json()["connected_peers"]

    # Verify unlisted after disconnect
    res2 = client.get("/api/v1/signaling/peers")
    assert "peer-alpha" not in res2.json()["connected_peers"]


def test_websocket_register_via_initial_message(client: TestClient):
    """Test registering a peer using the first 'register' JSON message."""
    with client.websocket_connect("/api/v1/signaling/ws") as ws:
        ws.send_json({"type": "register", "peer_id": "peer-beta"})
        msg = ws.receive_json()
        assert msg["type"] == "registered"
        assert msg["peer_id"] == "peer-beta"


def test_websocket_reject_duplicate_peer_id(client: TestClient):
    """Test that registering an already active peer ID is rejected without replacing."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-unique") as ws1:
        msg1 = ws1.receive_json()
        assert msg1["type"] == "registered"

        # Try connecting with the exact same peer_id
        with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-unique") as ws2:
            msg2 = ws2.receive_json()
            assert msg2["type"] == "error"
            assert msg2["code"] == "PEER_ALREADY_CONNECTED"

        # Ensure first connection is still active and registered
        assert signaling_manager.is_connected("peer-unique")


def test_websocket_ping_pong(client: TestClient):
    """Test ping/pong heartbeat over WebSocket."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-ping") as ws:
        ws.receive_json()  # discard registered message
        ws.send_json({"type": "ping"})
        msg = ws.receive_json()
        assert msg["type"] == "pong"
        assert msg["sender_id"] == "coordinator"


def test_websocket_offer_answer_and_candidate_relay(client: TestClient):
    """Test relaying offer, answer, and ICE candidates between two peers."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-initiator") as ws_init:
        init_reg = ws_init.receive_json()
        assert init_reg["type"] == "registered"

        with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-receiver") as ws_recv:
            recv_reg = ws_recv.receive_json()
            assert recv_reg["type"] == "registered"

            # Initiator might get peer_joined notification for receiver
            # Let's send an offer from initiator to receiver
            offer_payload = {"type": "offer", "sdp": "v=0\r\no=test\r\ns=-\r\n"}
            ws_init.send_json({
                "type": "offer",
                "target_id": "peer-receiver",
                "payload": offer_payload,
            })

            # Read on receiver: may receive peer_joined or offer
            received_offer = None
            for _ in range(3):
                msg = ws_recv.receive_json()
                if msg.get("type") == "offer":
                    received_offer = msg
                    break

            assert received_offer is not None
            assert received_offer["sender_id"] == "peer-initiator"
            assert received_offer["payload"]["sdp"] == offer_payload["sdp"]

            # Receiver replies with answer
            answer_payload = {"type": "answer", "sdp": "v=0\r\no=test-ans\r\ns=-\r\n"}
            ws_recv.send_json({
                "type": "answer",
                "target_id": "peer-initiator",
                "payload": answer_payload,
            })

            # Initiator receives answer
            received_answer = None
            for _ in range(3):
                msg = ws_init.receive_json()
                if msg.get("type") == "answer":
                    received_answer = msg
                    break

            assert received_answer is not None
            assert received_answer["sender_id"] == "peer-receiver"
            assert received_answer["payload"]["sdp"] == answer_payload["sdp"]

            # ICE candidate relay
            candidate_payload = {
                "candidate": "candidate:0 1 UDP 2122252543 127.0.0.1 50000 typ host",
                "sdpMid": "0",
            }
            ws_init.send_json({
                "type": "ice_candidate",
                "target_id": "peer-receiver",
                "payload": candidate_payload,
            })

            received_cand = ws_recv.receive_json()
            assert received_cand["type"] == "ice_candidate"
            assert received_cand["sender_id"] == "peer-initiator"
            assert received_cand["payload"]["candidate"] == candidate_payload["candidate"]


def test_websocket_unknown_target_error(client: TestClient):
    """Test routing message to non-existent peer returns TARGET_NOT_FOUND error."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-lonely") as ws:
        ws.receive_json()  # discard registered
        ws.send_json({
            "type": "offer",
            "target_id": "non-existent-peer",
            "payload": {"sdp": "..."},
        })
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "TARGET_NOT_FOUND"
        assert err["target_id"] == "non-existent-peer"


def test_websocket_missing_target_id_error(client: TestClient):
    """Test sending a relay message without target_id returns MISSING_TARGET_ID."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-test") as ws:
        ws.receive_json()  # discard registered
        ws.send_json({"type": "offer", "payload": {"sdp": "..."}})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "MISSING_TARGET_ID"


def test_websocket_malformed_json(client: TestClient):
    """Test sending invalid JSON returns MALFORMED_MESSAGE error."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-malformed") as ws:
        ws.receive_json()  # discard registered
        ws.send_text("this is not json {")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "MALFORMED_MESSAGE"


def test_websocket_reconnect_after_disconnect(client: TestClient):
    """Test that a peer can cleanly reconnect with the same peer_id after closing."""
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-reconnect") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "registered"

    # Connection is closed, now reconnect with same ID
    with client.websocket_connect("/api/v1/signaling/ws?peer_id=peer-reconnect") as ws2:
        msg2 = ws2.receive_json()
        assert msg2["type"] == "registered"
        assert msg2["peer_id"] == "peer-reconnect"
