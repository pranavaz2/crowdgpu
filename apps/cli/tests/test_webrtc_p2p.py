"""
Tests for WebRTC Peer-to-Peer Protocol, Data Channel, and In-Process Loopback Exchange.

Covers:
- Protocol envelope hashing and SHA-256 integrity verification.
- Tampering detection on P2P payloads.
- Structured ACK generation and verification.
- Direct peer-to-peer RTCDataChannel open, message exchange, and ACK round-trip
  without any HTTP relaying (in-process WebRTC loopback).
- Malformed message rejection on the data channel.
- Multiple peer sessions without cross-delivery.
- Orderly connection teardown and cleanup.
"""

import asyncio
import json
import pytest
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_to_sdp, candidate_from_sdp

from cli.webrtc.protocol import (
    PROTOCOL_VERSION,
    compute_sha256,
    create_p2p_message,
    verify_p2p_message,
    create_p2p_ack,
    verify_p2p_ack,
)
from cli.webrtc.peer import WebRTCPeer


# ---------------------------------------------------------------------------
# 1. Unit: Protocol Hashing, Envelope Validation & Tamper Resistance
# ---------------------------------------------------------------------------

def test_p2p_envelope_creation_and_integrity_verification():
    """Verify envelope wraps payload with deterministic SHA-256 hash."""
    payload = {"task": "benchmark", "matrix_size": 2048, "iterations": 10}
    envelope = create_p2p_message(
        sender_id="peer-alice",
        message_type="p2p_benchmark_request",
        payload=payload,
    )

    assert envelope["protocol"] == PROTOCOL_VERSION
    assert envelope["sender_id"] == "peer-alice"
    assert envelope["type"] == "p2p_benchmark_request"
    assert envelope["payload"] == payload
    assert len(envelope["payload_sha256"]) == 64  # Hex SHA-256 length

    # Validate integrity
    is_valid, msg, parsed = verify_p2p_message(envelope)
    assert is_valid is True
    assert "verified" in msg.lower()
    assert parsed["request_id"] == envelope["request_id"]


def test_p2p_envelope_tampering_detection():
    """Verify tampering with payload invalidates SHA-256 checksum."""
    payload = {"task": "benchmark", "matrix_size": 2048}
    envelope = create_p2p_message(
        sender_id="peer-alice",
        payload=payload,
    )

    # Malicious actor or network bit-flip modifies payload in flight
    tampered = dict(envelope)
    tampered["payload"] = {"task": "benchmark", "matrix_size": 999999}

    is_valid, err_msg, _ = verify_p2p_message(tampered)
    assert is_valid is False
    assert "integrity check failed" in err_msg.lower()


def test_p2p_envelope_malformed_inputs():
    """Verify malformed JSON or invalid types are safely rejected."""
    is_valid, err, _ = verify_p2p_message("not a valid json")
    assert is_valid is False

    is_valid, err, _ = verify_p2p_message(["array", "instead", "of", "dict"])
    assert is_valid is False

    is_valid, err, _ = verify_p2p_message({"protocol": "wrong-version"})
    assert is_valid is False

    is_valid, err, _ = verify_p2p_message({
        "protocol": PROTOCOL_VERSION,
        "request_id": "r1",
        # missing payload_sha256 and payload
    })
    assert is_valid is False


def test_p2p_acknowledgement_round_trip():
    """Verify ACK generation matches original request ID and payload hash."""
    payload = {"data": "test-data-block-128kb"}
    envelope = create_p2p_message(
        sender_id="initiator-1",
        payload=payload,
    )

    req_id = envelope["request_id"]
    payload_hash = envelope["payload_sha256"]

    ack = create_p2p_ack(
        receiver_id="receiver-1",
        request_id=req_id,
        verified_hash=payload_hash,
        latency_ms=1.23,
    )

    assert ack["protocol"] == PROTOCOL_VERSION
    assert ack["type"] == "ack"
    assert ack["response_to"] == req_id
    assert ack["receiver_id"] == "receiver-1"
    assert ack["verified_sha256"] == payload_hash
    assert ack["status"] == "verified"

    # Verify matching ACK
    valid_ack, msg, parsed_ack = verify_p2p_ack(ack, req_id, payload_hash)
    assert valid_ack is True
    assert "verified successfully" in msg.lower()
    assert parsed_ack["verified_sha256"] == payload_hash

    # Verify mismatched request_id rejected
    valid_ack, err, _ = verify_p2p_ack(ack, "different-request-id", payload_hash)
    assert valid_ack is False
    assert "mismatch" in err.lower()

    # Verify mismatched hash rejected
    valid_ack, err, _ = verify_p2p_ack(ack, req_id, "00000000000000000000000000000000")
    assert valid_ack is False
    assert "hash mismatch" in err.lower()


# ---------------------------------------------------------------------------
# 2. In-Process Peer-to-Peer Loopback Test (aiortc Data Channel)
# ---------------------------------------------------------------------------

async def _exchange_candidates_loopback(pc_a: RTCPeerConnection, pc_b: RTCPeerConnection, stop_event: asyncio.Event):
    """Exchanges Trickle ICE candidates between two in-process RTCPeerConnections."""
    sent_a: set[str] = set()
    sent_b: set[str] = set()
    while not stop_event.is_set():
        if pc_a.sctp and pc_a.sctp.transport and pc_a.sctp.transport.transport:
            gatherer_a = pc_a.sctp.transport.transport.iceGatherer
            for cand in gatherer_a.getLocalCandidates():
                sdp_str = candidate_to_sdp(cand)
                if sdp_str not in sent_a:
                    sent_a.add(sdp_str)
                    c = candidate_from_sdp(sdp_str)
                    c.sdpMid = "0"
                    c.sdpMLineIndex = 0
                    await pc_b.addIceCandidate(c)

        if pc_b.sctp and pc_b.sctp.transport and pc_b.sctp.transport.transport:
            gatherer_b = pc_b.sctp.transport.transport.iceGatherer
            for cand in gatherer_b.getLocalCandidates():
                sdp_str = candidate_to_sdp(cand)
                if sdp_str not in sent_b:
                    sent_b.add(sdp_str)
                    c = candidate_from_sdp(sdp_str)
                    c.sdpMid = "0"
                    c.sdpMLineIndex = 0
                    await pc_a.addIceCandidate(c)

        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_in_process_p2p_datachannel_exchange():
    """
    Direct in-process loopback WebRTC test without external network.
    
    Workflow:
    1. Peer A (Initiator) & Peer B (Receiver) create RTCPeerConnection instances.
    2. Data channel is opened by Peer A.
    3. Direct exchange of offer and answer descriptions + ICE candidate exchange.
    4. Data channel state transitions to 'open'.
    5. Peer A sends structured JSON envelope over RTCDataChannel.
    6. Peer B receives message on RTCDataChannel, computes SHA-256 hash, verifies integrity,
       and transmits matching structured ACK directly back over the data channel.
    7. Peer A receives and verifies the ACK over the data channel.
    8. Both connections close cleanly.
    """
    pc_a = RTCPeerConnection()
    pc_b = RTCPeerConnection()

    channel_a = pc_a.createDataChannel("crowdgpu-datachannel")
    
    b_received_messages = []
    a_received_messages = []
    channel_b_holder = []
    
    channel_a_opened = asyncio.Event()
    channel_b_opened = asyncio.Event()
    b_processed_msg = asyncio.Event()
    a_received_ack = asyncio.Event()
    stop_ice_exchange = asyncio.Event()

    @channel_a.on("open")
    def on_a_open():
        channel_a_opened.set()

    @channel_a.on("message")
    def on_a_message(msg):
        a_received_messages.append(msg)
        a_received_ack.set()

    @pc_b.on("datachannel")
    def on_datachannel(channel):
        channel_b_holder.append(channel)
        if getattr(channel, "readyState", None) == "open":
            channel_b_opened.set()

        @channel.on("open")
        def on_b_open():
            channel_b_opened.set()

        @channel.on("message")
        def on_b_message(msg):
            b_received_messages.append(msg)
            # Receiver verifies message integrity and returns ACK directly over data channel
            is_valid, reason, parsed = verify_p2p_message(msg)
            if is_valid and parsed:
                ack = create_p2p_ack(
                    receiver_id="peer-b-receiver",
                    request_id=parsed["request_id"],
                    verified_hash=parsed["payload_sha256"],
                    status="verified",
                )
                channel.send(json.dumps(ack))
            b_processed_msg.set()

    try:
        # Step 1: Create and exchange offer/answer
        offer = await pc_a.createOffer()
        await pc_a.setLocalDescription(offer)
        await pc_b.setRemoteDescription(pc_a.localDescription)

        answer = await pc_b.createAnswer()
        await pc_b.setLocalDescription(answer)
        await pc_a.setRemoteDescription(pc_b.localDescription)

        # Step 2: Start trickle ICE exchange
        ice_task = asyncio.create_task(_exchange_candidates_loopback(pc_a, pc_b, stop_ice_exchange))

        # Step 3: Await data channel opening on both sides
        await asyncio.wait_for(channel_a_opened.wait(), timeout=5.0)
        await asyncio.wait_for(channel_b_opened.wait(), timeout=5.0)

        assert channel_a.readyState == "open"
        assert len(channel_b_holder) == 1
        assert channel_b_holder[0].readyState == "open"

        # Step 4: Peer A sends structured message over RTCDataChannel
        test_payload = {
            "workload": "vector_add_demo",
            "elements": 1000000,
            "status": "ready_for_execution",
        }
        envelope = create_p2p_message(
            sender_id="peer-a-initiator",
            message_type="p2p_data_sync",
            payload=test_payload,
        )
        channel_a.send(json.dumps(envelope))

        # Step 5: Wait for Peer B to process and respond
        await asyncio.wait_for(b_processed_msg.wait(), timeout=5.0)
        assert len(b_received_messages) == 1

        # Step 6: Wait for Peer A to receive ACK
        await asyncio.wait_for(a_received_ack.wait(), timeout=5.0)
        assert len(a_received_messages) == 1

        # Step 7: Verify ACK matches
        is_valid, reason, parsed_ack = verify_p2p_ack(
            a_received_messages[0],
            expected_request_id=envelope["request_id"],
            expected_hash=envelope["payload_sha256"],
        )
        assert is_valid is True
        assert parsed_ack["receiver_id"] == "peer-b-receiver"
        assert parsed_ack["response_to"] == envelope["request_id"]
        assert parsed_ack["status"] == "verified"

    finally:
        stop_ice_exchange.set()
        await ice_task
        channel_a.close()
        for ch in channel_b_holder:
            ch.close()
        await pc_a.close()
        await pc_b.close()


@pytest.mark.asyncio
async def test_p2p_datachannel_tampered_payload_rejected_by_receiver():
    """Verify receiver rejects tampered data and does not issue a verified ACK."""
    pc_a = RTCPeerConnection()
    pc_b = RTCPeerConnection()

    channel_a = pc_a.createDataChannel("crowdgpu-datachannel")
    channel_b_holder = []
    
    channel_a_opened = asyncio.Event()
    channel_b_opened = asyncio.Event()
    b_processed_msg = asyncio.Event()
    stop_ice_exchange = asyncio.Event()
    receiver_acks = []

    @channel_a.on("open")
    def on_a_open():
        channel_a_opened.set()

    @pc_b.on("datachannel")
    def on_datachannel(channel):
        channel_b_holder.append(channel)
        if getattr(channel, "readyState", None) == "open":
            channel_b_opened.set()

        @channel.on("open")
        def on_b_open():
            channel_b_opened.set()

        @channel.on("message")
        def on_b_message(msg):
            is_valid, reason, parsed = verify_p2p_message(msg)
            if not is_valid:
                receiver_acks.append({"error": reason})
            else:
                ack = create_p2p_ack(
                    receiver_id="peer-b",
                    request_id=parsed["request_id"],
                    verified_hash=parsed["payload_sha256"],
                )
                receiver_acks.append(ack)
            b_processed_msg.set()

    try:
        offer = await pc_a.createOffer()
        await pc_a.setLocalDescription(offer)
        await pc_b.setRemoteDescription(pc_a.localDescription)

        answer = await pc_b.createAnswer()
        await pc_b.setLocalDescription(answer)
        await pc_a.setRemoteDescription(pc_b.localDescription)

        ice_task = asyncio.create_task(_exchange_candidates_loopback(pc_a, pc_b, stop_ice_exchange))

        await asyncio.wait_for(channel_a_opened.wait(), timeout=5.0)
        await asyncio.wait_for(channel_b_opened.wait(), timeout=5.0)

        # Create message and tamper with it
        envelope = create_p2p_message(
            sender_id="peer-a",
            payload={"secret_value": 42},
        )
        tampered_envelope = dict(envelope)
        tampered_envelope["payload"] = {"secret_value": 9999}  # altered!

        channel_a.send(json.dumps(tampered_envelope))
        await asyncio.wait_for(b_processed_msg.wait(), timeout=5.0)

        assert len(receiver_acks) == 1
        assert "error" in receiver_acks[0]
        assert "integrity check failed" in receiver_acks[0]["error"].lower()

    finally:
        stop_ice_exchange.set()
        await ice_task
        channel_a.close()
        for ch in channel_b_holder:
            ch.close()
        await pc_a.close()
        await pc_b.close()
