"""
Tests for CLI WebRTC commands.
"""

from click.testing import CliRunner

from cli.main import cli
from cli.webrtc.peer import WebRTCPeer


def test_webrtc_help() -> None:
    """webrtc --help should exit zero and show commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["webrtc", "--help"])
    assert result.exit_code == 0
    assert "listen" in result.output
    assert "connect" in result.output
    assert "status" in result.output


def test_webrtc_status(monkeypatch) -> None:
    """webrtc status should query and format signaling peers and ICE servers."""
    class MockClient:
        def __init__(self):
            self.base_url = "http://localhost:8000"

        def list_signaling_peers(self):
            return {"connected_peers": ["peer-1", "peer-2"], "count": 2}

        def get_ice_servers(self):
            return {"ice_servers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["webrtc", "status"])
    assert result.exit_code == 0
    assert "Connected Peers Count: 2" in result.output
    assert "peer-1, peer-2" in result.output
    assert "stun:stun.l.google.com:19302" in result.output


def test_webrtc_peer_url_derivation() -> None:
    """WebRTCPeer should correctly format WebSocket URLs for signaling."""
    p1 = WebRTCPeer(peer_id="node-1", coordinator_url="http://127.0.0.1:8000")
    assert p1._get_ws_url() == "ws://127.0.0.1:8000/api/v1/signaling/ws?peer_id=node-1"

    p2 = WebRTCPeer(peer_id="node-2", coordinator_url="https://coord.example.com")
    assert p2._get_ws_url() == "wss://coord.example.com/api/v1/signaling/ws?peer_id=node-2"
