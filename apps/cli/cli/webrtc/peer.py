"""
WebRTC Peer Client Implementation.

Provides initiator and receiver peer functionality using aiortc and FastAPI WebSocket signaling.
Features:
- SDP offer/answer exchange via coordinator signaling
- ICE candidate gathering and Trickle ICE candidate relay with pre-description queuing
- RTCPeerConnection lifecycle and connection state tracking
- Bi-directional RTCDataChannel direct messaging
- Cryptographic SHA-256 payload integrity verification and structured ACK handshake
- Configurable STUN/TURN servers
- Graceful shutdown and resource cleanup
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
import websockets
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

from cli.webrtc.protocol import (
    create_p2p_ack,
    create_p2p_message,
    verify_p2p_ack,
    verify_p2p_message,
)

logger = logging.getLogger(__name__)


class WebRTCPeerError(Exception):
    """Base exception for WebRTC Peer errors."""


class WebRTCPeer:
    """WebRTC Peer capable of acting as an initiator (offerer) or receiver (answerer)."""

    def __init__(
        self,
        peer_id: str,
        coordinator_url: str = "http://127.0.0.1:8000",
        role: str = "initiator",
        target_id: str | None = None,
        ice_servers: list[str] | None = None,
        channel_name: str = "crowdgpu-datachannel",
        auto_echo: bool = False,
    ) -> None:
        self.peer_id = peer_id
        self.coordinator_url = coordinator_url.rstrip("/")
        self.role = role.lower()  # "initiator" or "receiver"
        self.target_id = target_id
        self.channel_name = channel_name
        self.auto_echo = auto_echo

        self.custom_ice_servers = ice_servers
        self.ice_servers: list[RTCIceServer] = []

        self.ws: Any = None
        self.pc: RTCPeerConnection | None = None
        self.data_channel: Any = None

        # Synchronization events
        self.signaling_registered = asyncio.Event()
        self.ice_connected = asyncio.Event()
        self.channel_open = asyncio.Event()
        self.channel_closed = asyncio.Event()
        self.closed_event = asyncio.Event()

        # State and message history
        self.connection_states: list[str] = []
        self.ice_connection_states: list[str] = []
        self.received_messages: list[str] = []
        self.sent_messages: list[str] = []
        self.message_queue: asyncio.Queue[str] = asyncio.Queue()

        # Candidate queueing before remote description is set
        self._pending_ice_candidates: list[Any] = []

        # Background tasks
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._on_message_callback: Callable[[str], None] | None = None

    def on_message(self, callback: Callable[[str], None]) -> None:
        """Register a callback for data channel messages."""
        self._on_message_callback = callback

    def _get_ws_url(self) -> str:
        url = self.coordinator_url
        if url.startswith("https://"):
            ws_base = "wss://" + url[8:]
        elif url.startswith("http://"):
            ws_base = "ws://" + url[7:]
        elif url.startswith("ws://") or url.startswith("wss://"):
            ws_base = url
        else:
            ws_base = f"ws://{url}"
        return f"{ws_base}/api/v1/signaling/ws?peer_id={self.peer_id}"

    async def fetch_ice_servers(self) -> list[RTCIceServer]:
        """Fetch configured ICE servers from coordinator or fallback to defaults."""
        if self.custom_ice_servers:
            return [RTCIceServer(urls=self.custom_ice_servers)]

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.coordinator_url}/api/v1/signaling/ice-servers")
                if res.status_code == 200:
                    data = res.json()
                    servers = []
                    for entry in data.get("ice_servers", []):
                        servers.append(
                            RTCIceServer(
                                urls=entry["urls"],
                                username=entry.get("username"),
                                credential=entry.get("credential"),
                            )
                        )
                    if servers:
                        return servers
        except Exception as exc:
            logger.debug(
                "Failed to fetch ICE servers from coordinator (%s), using host candidates fallback",
                exc,
            )

        # Fallback to standard Google STUN; if offline, host candidates handle local loopback
        return [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]

    def _setup_peer_connection(self) -> None:
        """Initialize RTCPeerConnection and bind lifecycle event listeners."""
        config = RTCConfiguration(iceServers=self.ice_servers)
        self.pc = RTCPeerConnection(configuration=config)

        @self.pc.on("connectionstatechange")
        def on_connection_state_change() -> None:
            state = self.pc.connectionState if self.pc else "unknown"
            logger.info("[%s] RTCPeerConnection state: %s", self.peer_id, state)
            self.connection_states.append(state)
            if state == "failed":
                logger.error("[%s] RTCPeerConnection failed", self.peer_id)

        @self.pc.on("iceconnectionstatechange")
        def on_ice_connection_state_change() -> None:
            state = self.pc.iceConnectionState if self.pc else "unknown"
            logger.info("[%s] ICE Connection state: %s", self.peer_id, state)
            self.ice_connection_states.append(state)
            if state in ("connected", "completed"):
                self.ice_connected.set()

        @self.pc.on("icegatheringstatechange")
        def on_ice_gathering_state_change() -> None:
            state = self.pc.iceGatheringState if self.pc else "unknown"
            logger.debug("[%s] ICE Gathering state: %s", self.peer_id, state)

        if self.role == "receiver":
            @self.pc.on("datachannel")
            def on_datachannel(channel: Any) -> None:
                logger.info(
                    "[%s] Incoming RTCDataChannel received: '%s'",
                    self.peer_id,
                    channel.label,
                )
                self._bind_data_channel(channel)

    def _bind_data_channel(self, channel: Any) -> None:
        """Bind event listeners to the RTCDataChannel."""
        self.data_channel = channel

        if getattr(channel, "readyState", None) == "open":
            logger.info(
                "[%s] [data-channel:channel-open] RTCDataChannel '%s' is ALREADY OPEN",
                self.peer_id,
                channel.label,
            )
            self.channel_open.set()

        @channel.on("open")
        def on_open() -> None:
            logger.info(
                "[%s] [data-channel:channel-open] RTCDataChannel '%s' is OPEN",
                self.peer_id,
                channel.label,
            )
            self.channel_open.set()

        @channel.on("message")
        def on_message(message: Any) -> None:
            msg_str = (
                message if isinstance(message, str)
                else message.decode("utf-8", errors="replace")
            )
            logger.info(
                "[%s] [data-channel:message-received] Direct RTCDataChannel message: %s",
                self.peer_id,
                msg_str,
            )
            self.received_messages.append(msg_str)
            self.message_queue.put_nowait(msg_str)

            if self._on_message_callback:
                try:
                    self._on_message_callback(msg_str)
                except Exception as exc:
                    logger.exception("[%s] Callback error: %s", self.peer_id, exc)

            # Auto-respond if auto_echo is enabled
            if self.auto_echo and self.data_channel and self.data_channel.readyState == "open":
                is_valid, reason, parsed = verify_p2p_message(msg_str)
                if is_valid and parsed and parsed.get("type") != "ack":
                    req_id = parsed["request_id"]
                    verified_hash = parsed["payload_sha256"]
                    ack_payload = create_p2p_ack(
                        receiver_id=self.peer_id,
                        request_id=req_id,
                        verified_hash=verified_hash,
                    )
                    ack_str = json.dumps(ack_payload)
                    try:
                        self.data_channel.send(ack_str)
                        self.sent_messages.append(ack_str)
                        logger.info(
                            "[%s] [data-channel:acknowledgement-sent] Direct P2P ACK sent for request '%s'",
                            self.peer_id,
                            req_id,
                        )
                    except Exception as exc:
                        logger.warning("[%s] Failed to send ACK: %s", self.peer_id, exc)
                elif not is_valid:
                    reply = f"Echo: {msg_str}"
                    try:
                        self.data_channel.send(reply)
                        self.sent_messages.append(reply)
                    except Exception:
                        pass

        @channel.on("close")
        def on_close() -> None:
            logger.info("[%s] [data-channel:channel-closed] RTCDataChannel closed", self.peer_id)
            self.channel_closed.set()

    def _get_ice_gatherer(self) -> Any:
        """Retrieve the ICE gatherer from SCTP transport if available."""
        if self.pc and self.pc.sctp and self.pc.sctp.transport and self.pc.sctp.transport.transport:
            return self.pc.sctp.transport.transport.iceGatherer
        return None

    async def _send_signaling(self, message: dict[str, Any]) -> None:
        """Send a JSON payload over the signaling WebSocket."""
        if self.ws:
            payload = json.dumps(message)
            await self.ws.send(payload)

    async def _drain_pending_candidates(self) -> None:
        """Apply any ICE candidates received before the remote description was set."""
        while self._pending_ice_candidates:
            cand = self._pending_ice_candidates.pop(0)
            try:
                if self.pc and self.pc.remoteDescription:
                    await self.pc.addIceCandidate(cand)
                    logger.debug("[%s] Applied queued ICE candidate", self.peer_id)
            except Exception as exc:
                logger.debug("[%s] Error applying queued ICE candidate: %s", self.peer_id, exc)

    async def _signaling_loop(self) -> None:
        """Background loop to receive signaling messages from coordinator."""
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                msg_type = data.get("type")
                sender_id = data.get("sender_id")

                if msg_type == "registered":
                    logger.info("[%s] Registered with signaling server", self.peer_id)
                    self.signaling_registered.set()

                elif msg_type == "offer":
                    logger.info("[%s] Received SDP offer from '%s'", self.peer_id, sender_id)
                    payload = data.get("payload", {})
                    sdp = payload.get("sdp")
                    if sdp and self.pc:
                        self.target_id = sender_id
                        desc = RTCSessionDescription(sdp=sdp, type="offer")
                        await self.pc.setRemoteDescription(desc)
                        await self._drain_pending_candidates()

                        answer = await self.pc.createAnswer()
                        await self.pc.setLocalDescription(answer)
                        await self._send_signaling({
                            "type": "answer",
                            "target_id": sender_id,
                            "payload": {"type": answer.type, "sdp": answer.sdp},
                        })
                        logger.info("[%s] Sent SDP answer to '%s'", self.peer_id, sender_id)

                elif msg_type == "answer":
                    logger.info("[%s] Received SDP answer from '%s'", self.peer_id, sender_id)
                    payload = data.get("payload", {})
                    sdp = payload.get("sdp")
                    if sdp and self.pc:
                        desc = RTCSessionDescription(sdp=sdp, type="answer")
                        await self.pc.setRemoteDescription(desc)
                        await self._drain_pending_candidates()

                elif msg_type == "ice_candidate":
                    payload = data.get("payload", {})
                    cand_str = payload.get("candidate")
                    if cand_str and self.pc:
                        try:
                            candidate = candidate_from_sdp(cand_str)
                            candidate.sdpMid = payload.get("sdpMid", "0")
                            candidate.sdpMLineIndex = payload.get("sdpMLineIndex", 0)

                            if self.pc.remoteDescription:
                                await self.pc.addIceCandidate(candidate)
                                logger.debug(
                                    "[%s] Added remote ICE candidate from '%s'",
                                    self.peer_id,
                                    sender_id,
                                )
                            else:
                                self._pending_ice_candidates.append(candidate)
                                logger.debug(
                                    "[%s] Queued remote ICE candidate (remote description not ready)",
                                    self.peer_id,
                                )
                        except Exception as exc:
                            logger.debug(
                                "[%s] Error adding ICE candidate: %s",
                                self.peer_id,
                                exc,
                            )

                elif msg_type == "error":
                    logger.warning(
                        "[%s] Signaling error received: %s (code: %s)",
                        self.peer_id,
                        data.get("message"),
                        data.get("code"),
                    )

        except websockets.exceptions.ConnectionClosed:
            logger.info("[%s] Signaling WebSocket closed", self.peer_id)
        except Exception as exc:
            if self._running:
                logger.exception("[%s] Unexpected signaling error: %s", self.peer_id, exc)

    async def _candidate_gather_task(self) -> None:
        """Poll and transmit gathered local ICE candidates via Trickle ICE."""
        sent_candidates: set[str] = set()
        while self._running:
            gatherer = self._get_ice_gatherer()
            if gatherer and self.target_id:
                try:
                    candidates = gatherer.getLocalCandidates()
                    for cand in candidates:
                        sdp_line = candidate_to_sdp(cand)
                        if sdp_line not in sent_candidates:
                            sent_candidates.add(sdp_line)
                            await self._send_signaling({
                                "type": "ice_candidate",
                                "target_id": self.target_id,
                                "payload": {
                                    "candidate": sdp_line,
                                    "sdpMid": "0",
                                    "sdpMLineIndex": 0,
                                },
                            })
                            logger.debug(
                                "[%s] Sent ICE candidate to '%s'",
                                self.peer_id,
                                self.target_id,
                            )
                except Exception as exc:
                    logger.debug("[%s] Candidate polling notice: %s", self.peer_id, exc)

            if self.ice_connected.is_set():
                await asyncio.sleep(0.5)
                break

            await asyncio.sleep(0.05)

    async def start(self) -> None:
        """Connect to signaling gateway, initialize peer connection, and begin handshake."""
        self._running = True
        self.ice_servers = await self.fetch_ice_servers()
        self._setup_peer_connection()

        ws_url = self._get_ws_url()
        logger.info("[%s] Connecting to signaling gateway: %s", self.peer_id, ws_url)
        self.ws = await websockets.connect(ws_url)

        # Launch signaling reader task
        sig_task = asyncio.create_task(self._signaling_loop(), name=f"sig-{self.peer_id}")
        self._tasks.append(sig_task)

        # Wait for registration confirmation
        await asyncio.wait_for(self.signaling_registered.wait(), timeout=5.0)

        # Launch ICE candidate gatherer task
        cand_task = asyncio.create_task(self._candidate_gather_task(), name=f"cand-{self.peer_id}")
        self._tasks.append(cand_task)

        # If initiator, create data channel and send offer
        if self.role == "initiator":
            if not self.target_id:
                raise WebRTCPeerError("Initiator requires a target_id to connect to")

            logger.info(
                "[%s] Initiating WebRTC connection to target '%s'",
                self.peer_id,
                self.target_id,
            )
            dc = self.pc.createDataChannel(self.channel_name)
            self._bind_data_channel(dc)

            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)

            await self._send_signaling({
                "type": "offer",
                "target_id": self.target_id,
                "payload": {"type": offer.type, "sdp": offer.sdp},
            })
            logger.info("[%s] Created and transmitted SDP offer", self.peer_id)

    async def send_message(self, message: str) -> None:
        """Send a string message directly over the established RTCDataChannel."""
        if not self.data_channel or self.data_channel.readyState != "open":
            cur_state = getattr(self.data_channel, "readyState", "none")
            raise WebRTCPeerError(f"Data channel is not open (current state: {cur_state})")

        self.data_channel.send(message)
        self.sent_messages.append(message)
        logger.info(
            "[%s] [data-channel:message-sent] Sent message directly on data channel: %s",
            self.peer_id,
            message,
        )

    async def send_p2p_request(
        self,
        payload: dict[str, Any] | None = None,
        message_type: str = "p2p_data_sync",
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """
        Send a structured P2P message directly over the data channel and await matching direct ACK.
        """
        envelope = create_p2p_message(
            sender_id=self.peer_id,
            message_type=message_type,
            payload=payload,
        )
        req_id = envelope["request_id"]
        expected_hash = envelope["payload_sha256"]

        raw_json = json.dumps(envelope)
        t_start = time.perf_counter()
        await self.send_message(raw_json)

        # Wait for matching direct ACK
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            remaining = deadline - time.perf_counter()
            try:
                reply_raw = await asyncio.wait_for(self.message_queue.get(), timeout=min(remaining, 1.0))
            except TimeoutError:
                continue

            is_valid, reason, ack_dict = verify_p2p_ack(reply_raw, req_id, expected_hash)
            if is_valid and ack_dict:
                rtt_ms = (time.perf_counter() - t_start) * 1000.0
                logger.info(
                    "[%s] [data-channel:acknowledgement-received] Verified ACK for req_id=%s in %.2fms",
                    self.peer_id,
                    req_id,
                    rtt_ms,
                )
                return {
                    "success": True,
                    "request_id": req_id,
                    "payload_sha256": expected_hash,
                    "rtt_ms": rtt_ms,
                    "envelope": envelope,
                    "ack": ack_dict,
                }

        raise TimeoutError(f"Timed out waiting for matching direct P2P ACK for request '{req_id}'")

    async def wait_for_data_channel(self, timeout: float = 10.0) -> None:
        """Wait until the data channel reaches the 'open' state."""
        await asyncio.wait_for(self.channel_open.wait(), timeout=timeout)

    async def wait_for_connection(self, timeout: float = 10.0) -> None:
        """Wait until ICE connectivity is established."""
        await asyncio.wait_for(self.ice_connected.wait(), timeout=timeout)

    async def wait_for_message(self, timeout: float = 10.0) -> str:
        """Wait and retrieve the next message received over the data channel."""
        return await asyncio.wait_for(self.message_queue.get(), timeout=timeout)

    async def close(self) -> None:
        """Perform graceful cleanup of data channel, peer connection, and signaling."""
        self._running = False
        logger.info("[%s] Closing WebRTC Peer...", self.peer_id)

        if self.data_channel:
            with contextlib.suppress(Exception):
                self.data_channel.close()

        if self.pc:
            with contextlib.suppress(Exception):
                await self.pc.close()

        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close()

        for task in self._tasks:
            if not task.done():
                task.cancel()

        self.closed_event.set()
        logger.info("[%s] [data-channel:channel-closed] WebRTC Peer closed cleanly", self.peer_id)
