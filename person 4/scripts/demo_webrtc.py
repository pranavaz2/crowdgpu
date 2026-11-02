"""
CrowdGPU WebRTC Peer-to-Peer Data Channel Demonstration.

Usage:
  # 1. Complete automated two-peer demo (starts coordinator or connects to existing):
  python scripts/demo_webrtc.py --role both

  # 2. Standalone receiver peer:
  python scripts/demo_webrtc.py --role receiver --peer-id provider-gpu-1

  # 3. Standalone initiator peer:
  python scripts/demo_webrtc.py --role initiator --peer-id client-node-1 --target-id provider-gpu-1
"""

import argparse
import asyncio
import logging
import socket
import sys
import time
from pathlib import Path

# Add project root to sys.path so apps/cli and apps/coordinator can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "apps" / "cli"))
sys.path.insert(0, str(ROOT_DIR / "apps" / "coordinator"))

from cli.webrtc.peer import WebRTCPeer


def get_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def run_receiver(
    peer_id: str,
    coordinator_url: str,
    timeout: float = 30.0,
    auto_echo: bool = True,
) -> None:
    """Run WebRTC receiver peer and echo back received messages."""
    peer = WebRTCPeer(
        peer_id=peer_id,
        coordinator_url=coordinator_url,
        role="receiver",
        auto_echo=auto_echo,
    )

    print("\n=======================================================")
    print(f"[RECEIVER] Starting Receiver Peer: '{peer_id}'")
    print(f"[RECEIVER] Coordinator: {coordinator_url}")
    print("=======================================================")

    await peer.start()
    print(f"[RECEIVER] Registered with signaling gateway as '{peer_id}'")
    print("[RECEIVER] Awaiting incoming connection and data channel...")

    try:
        await asyncio.wait_for(peer.channel_open.wait(), timeout=timeout)
        print(f"[RECEIVER] RTCDataChannel opened with '{peer.target_id}'!")
        print(f"[RECEIVER] RTCPeerConnection State: {peer.pc.connectionState if peer.pc else 'N/A'}")
        print(f"[RECEIVER] ICE Connection State:    {peer.pc.iceConnectionState if peer.pc else 'N/A'}")

        print("[RECEIVER] Listening for incoming messages...")
        msg = await asyncio.wait_for(peer.wait_for_message(), timeout=timeout)
        print(f"[RECEIVER] Received message: '{msg}'")

        if auto_echo:
            print("[RECEIVER] Echo reply sent automatically.")

        # Send an additional reverse-direction message
        reverse_msg = "[Provider Status] GPU GeForce RTX 4090 VRAM: 24576MiB AVAILABLE"
        await asyncio.sleep(0.1)
        await peer.send_message(reverse_msg)
        print(f"[RECEIVER] Sent reverse telemetry message: '{reverse_msg}'")

        # Give small buffer for delivery before closing
        await asyncio.sleep(1.0)

    finally:
        await peer.close()
        print("[RECEIVER] Closed cleanly.\n")


async def run_initiator(
    peer_id: str,
    target_id: str,
    coordinator_url: str,
    message: str = "CrowdGPU P2P Handshake: Ping #1",
    timeout: float = 30.0,
) -> None:
    """Run WebRTC initiator peer, connect to target, and exchange messages."""
    peer = WebRTCPeer(
        peer_id=peer_id,
        coordinator_url=coordinator_url,
        role="initiator",
        target_id=target_id,
    )

    print("\n=======================================================")
    print(f"[INITIATOR] Starting Initiator Peer: '{peer_id}' -> Target: '{target_id}'")
    print(f"[INITIATOR] Coordinator: {coordinator_url}")
    print("=======================================================")

    t0 = time.time()
    await peer.start()
    print(f"[INITIATOR] Registered with signaling gateway as '{peer_id}'")
    print(f"[INITIATOR] SDP offer transmitted to '{target_id}'. Waiting for handshake...")

    try:
        await asyncio.wait_for(peer.channel_open.wait(), timeout=timeout)
        t_open = time.time() - t0
        print(f"[INITIATOR] RTCDataChannel opened in {t_open:.2f}s!")
        print(f"[INITIATOR] RTCPeerConnection State: {peer.pc.connectionState if peer.pc else 'N/A'}")
        print(f"[INITIATOR] ICE Connection State:    {peer.pc.iceConnectionState if peer.pc else 'N/A'}")

        # Send test message
        print(f"[INITIATOR] Sending data channel message: '{message}'")
        t_send = time.time()
        await peer.send_message(message)

        # Wait for echo reply
        reply = await asyncio.wait_for(peer.wait_for_message(), timeout=timeout)
        rtt_ms = (time.time() - t_send) * 1000.0
        print(f"[INITIATOR] Echo reply received in {rtt_ms:.1f}ms: '{reply}'")

        # Wait for reverse telemetry message
        reverse_telemetry = await asyncio.wait_for(peer.wait_for_message(), timeout=timeout)
        print(f"[INITIATOR] Reverse message received: '{reverse_telemetry}'")

        print("\n[+] SUCCESS: Bi-directional WebRTC P2P communication fully verified!")

    finally:
        await peer.close()
        print("[INITIATOR] Closed cleanly.\n")


async def run_both(coordinator_url: str | None = None) -> None:
    """Run both peers in a self-contained demonstration."""
    import uvicorn
    from coordinator.main import app

    server_task = None
    server = None

    if not coordinator_url:
        port = get_free_port()
        coordinator_url = f"http://127.0.0.1:{port}"
        print(f"[*] Starting embedded Coordinator server on {coordinator_url}...")
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.05)
        print("[+] Coordinator server is ready.")

    rx_id = "provider-gpu-node-01"
    tx_id = "consumer-client-node-01"

    print("\n=======================================================")
    print("  CROWDGPU WEBRTC PEER-TO-PEER END-TO-END DEMONSTRATION")
    print("=======================================================")
    print(f"Coordinator URL:      {coordinator_url}")
    print(f"Receiver Peer ID:     {rx_id}")
    print(f"Initiator Peer ID:    {tx_id}")
    print("Transport:            RTCDataChannel over RTCPeerConnection")
    print("Signaling Protocol:   FastAPI WebSocket (/api/v1/signaling/ws)")
    print("-------------------------------------------------------")

    try:
        # Launch receiver task
        rx_task = asyncio.create_task(
            run_receiver(rx_id, coordinator_url, timeout=15.0, auto_echo=True)
        )
        await asyncio.sleep(0.5)

        # Launch initiator task
        tx_task = asyncio.create_task(
            run_initiator(tx_id, rx_id, coordinator_url, timeout=15.0)
        )

        await asyncio.gather(rx_task, tx_task)

        print("\n" + "=" * 55)
        print("  DEMO RESULT: 100% PASS - P2P DATA CHANNEL VERIFIED")
        print("=" * 55)

    finally:
        if server and server_task:
            server.should_exit = True
            await server_task


def main() -> None:
    parser = argparse.ArgumentParser(description="CrowdGPU WebRTC P2P Data Channel Demo")
    parser.add_argument("--role", choices=["initiator", "receiver", "both"], default="both", help="Peer role")
    parser.add_argument("--peer-id", default=None, help="Peer ID")
    parser.add_argument("--target-id", default=None, help="Target peer ID (for initiator)")
    parser.add_argument("--coordinator-url", default=None, help="Coordinator HTTP URL (e.g. http://localhost:8000)")
    parser.add_argument("--message", default="Hello CrowdGPU WebRTC Peer!", help="Message payload")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    coord_url = args.coordinator_url or "http://127.0.0.1:8000"

    if args.role == "both":
        asyncio.run(run_both(args.coordinator_url))
    elif args.role == "receiver":
        pid = args.peer_id or "provider-gpu-01"
        asyncio.run(run_receiver(pid, coord_url, timeout=args.timeout))
    elif args.role == "initiator":
        pid = args.peer_id or "client-node-01"
        tid = args.target_id or "provider-gpu-01"
        asyncio.run(run_initiator(pid, tid, coord_url, message=args.message, timeout=args.timeout))


if __name__ == "__main__":
    main()
