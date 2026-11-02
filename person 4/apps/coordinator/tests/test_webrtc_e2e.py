"""
End-to-End Real WebRTC Peer-to-Peer Data Channel Test.

Spins up a live Coordinator FastAPI ASGI server over uvicorn,
connects two real aiortc WebRTC peers (initiator & receiver) via WebSocket signaling,
establishes an RTCPeerConnection with real ICE candidate exchange,
opens an RTCDataChannel, and verifies bi-directional message exchange.
"""

import asyncio
import socket
import sys
from pathlib import Path

import pytest
import uvicorn

# Ensure apps/cli is in sys.path
cli_path = str(Path(__file__).resolve().parent.parent.parent / "cli")
if cli_path not in sys.path:
    sys.path.insert(0, cli_path)

from cli.webrtc.peer import WebRTCPeer  # noqa: E402

from coordinator.main import app  # noqa: E402


def get_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_webrtc_p2p_data_channel_bidirectional_exchange():
    """
    Test real two-peer WebRTC connection and bi-directional RTCDataChannel messaging.
    """
    port = get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    # Launch coordinator server as background asyncio task
    server_task = asyncio.create_task(server.serve())

    # Wait until server is listening
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started, "Uvicorn server failed to start"

    coordinator_url = f"http://127.0.0.1:{port}"

    receiver_id = "test-rx-peer"
    initiator_id = "test-tx-peer"

    receiver = WebRTCPeer(
        peer_id=receiver_id,
        coordinator_url=coordinator_url,
        role="receiver",
        auto_echo=True,
    )

    initiator = WebRTCPeer(
        peer_id=initiator_id,
        coordinator_url=coordinator_url,
        role="initiator",
        target_id=receiver_id,
    )

    try:
        # Start receiver first so it registers with signaling
        await receiver.start()
        assert receiver.signaling_registered.is_set()

        # Start initiator
        await initiator.start()
        assert initiator.signaling_registered.is_set()

        # Wait for data channels to open on both ends
        await asyncio.wait_for(
            asyncio.gather(
                receiver.channel_open.wait(),
                initiator.channel_open.wait(),
            ),
            timeout=10.0,
        )

        assert receiver.data_channel is not None
        assert initiator.data_channel is not None
        assert receiver.data_channel.readyState == "open"
        assert initiator.data_channel.readyState == "open"

        # Verify ICE connection state
        assert initiator.pc.iceConnectionState in ("connected", "completed")
        assert receiver.pc.iceConnectionState in ("connected", "completed")

        # 1. Initiator sends message to Receiver
        msg_1 = "Hello Receiver from Initiator! Ping 1"
        await initiator.send_message(msg_1)

        rx_received = await receiver.wait_for_message(timeout=5.0)
        assert rx_received == msg_1, f"Expected '{msg_1}', got '{rx_received}'"

        # 2. Receiver auto-echos: "Echo: Hello Receiver from Initiator! Ping 1"
        tx_received_echo = await initiator.wait_for_message(timeout=5.0)
        expected_echo = f"Echo: {msg_1}"
        assert tx_received_echo == expected_echo, (
            f"Expected '{expected_echo}', got '{tx_received_echo}'"
        )

        # 3. Receiver sends independent message back to Initiator (reverse flow)
        msg_2 = "Reverse flow message: Provider GPU status READY"
        await receiver.send_message(msg_2)

        tx_received_reverse = await initiator.wait_for_message(timeout=5.0)
        assert tx_received_reverse == msg_2, (
            f"Expected '{msg_2}', got '{tx_received_reverse}'"
        )

        # Both directions confirmed!
        assert len(receiver.received_messages) >= 1
        assert len(initiator.received_messages) >= 2

    finally:
        # Graceful cleanup
        await initiator.close()
        await receiver.close()
        server.should_exit = True
        await server_task
