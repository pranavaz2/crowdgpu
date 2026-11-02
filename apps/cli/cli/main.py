"""
CrowdGPU CLI — Canonical Command-Line Interface.

Provides complete platform interactions:
- Coordinator health check
- Peer discovery and GPU capabilities inspection
- Workload submission with canonical presets
- Job listing and status filtering
- Job execution tracking and result inspection
- Job cancellation
- WebRTC P2P diagnostics
"""

from __future__ import annotations

import json
from typing import Any

import click

from cli import __version__
from cli.client import (
    CoordinatorAuthError,
    CoordinatorClient,
    CoordinatorConnectionError,
    CoordinatorNotFoundError,
    CoordinatorValidationError,
    InvalidStateTransitionError,
)
from cli.config import get_settings
from cli.workloads import WORKLOAD_PRESETS, resolve_workload


def _format_dict(data: dict[str, Any], indent: int = 2) -> str:
    """Format dictionary for terminal display without exposing secrets."""
    lines = []
    space = " " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{space}{k}:")
            lines.append(_format_dict(v, indent + 2))
        elif isinstance(v, list):
            lines.append(f"{space}{k}: {json.dumps(v)}")
        else:
            lines.append(f"{space}{k}: {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Root Group
# ---------------------------------------------------------------------------
@click.group()
@click.version_option(version=__version__, prog_name="crowdgpu-cli")
@click.option(
    "--coordinator-url",
    envvar="COORDINATOR_URL",
    default=None,
    help="Coordinator API URL (default: http://127.0.0.1:8000)",
)
@click.option(
    "--user-id",
    envvar="CROWDGPU_USER_ID",
    default=None,
    help="Client User UUID (default: canonical demo user 00000000-0000-0000-0000-000000000001)",
)
@click.pass_context
def cli(ctx: click.Context, coordinator_url: str | None, user_id: str | None) -> None:
    """
    CrowdGPU — Intelligent Distributed GPU Resource Sharing Platform CLI.

    Manage compute jobs, discover GPU provider peers, check coordinator health,
    and monitor execution status directly from the command line.
    """
    ctx.ensure_object(dict)
    cli_settings = get_settings(coordinator_url=coordinator_url, user_id=user_id)
    ctx.obj["settings"] = cli_settings
    ctx.obj["client"] = CoordinatorClient(settings_override=cli_settings)


# ---------------------------------------------------------------------------
# Health Command
# ---------------------------------------------------------------------------
@cli.command("health")
@click.pass_context
def health_cmd(ctx: click.Context) -> None:
    """Check CrowdGPU Coordinator service health and liveness."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        data = client.health()
        click.echo("=== Coordinator Health ===")
        click.echo(f"Coordinator URL: {client.base_url}")
        click.echo(f"Status:          {data.get('status', 'unknown')}")
        click.echo(f"Version:         {data.get('version', 'unknown')}")
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Coordinator unreachable: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Health check failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Peers Command Group
# ---------------------------------------------------------------------------
@cli.group()
def peers() -> None:
    """Discover, inspect, and register GPU provider peer nodes."""


@peers.command("list")
@click.pass_context
def peers_list(ctx: click.Context) -> None:
    """List all registered GPU provider peers and their hardware resources."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        peers_data = client.list_peers()
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to list peers: {exc}") from exc

    if not peers_data:
        click.echo("No provider peers registered.")
        return

    click.echo(f"{'PEER ID':<38} {'HOSTNAME':<22} {'STATUS':<12} {'GPUS'}")
    click.echo("-" * 95)
    for peer in peers_data:
        caps = peer.get("gpu_capabilities", [])
        if caps:
            gpu_str = ", ".join(f"{g.get('gpu_name', 'GPU')} ({g.get('vram_mb', 0)} MiB)" for g in caps)
        else:
            gpu_str = "No GPU attached"
        click.echo(
            f"{str(peer.get('id', '')):<38} {str(peer.get('hostname', '')):<22} "
            f"{str(peer.get('status', '')).upper():<12} {gpu_str}"
        )


@peers.command("get")
@click.argument("peer_id")
@click.pass_context
def peers_get(ctx: click.Context, peer_id: str) -> None:
    """Show detailed hardware telemetry for a specific peer node."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        peer = client.get_peer(peer_id)
    except CoordinatorNotFoundError:
        raise click.ClickException(f"Peer '{peer_id}' not found.")
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to get peer: {exc}") from exc

    click.echo("=== Peer Details ===")
    click.echo(f"ID:            {peer.get('id')}")
    click.echo(f"Hostname:      {peer.get('hostname')}")
    click.echo(f"Status:        {str(peer.get('status')).upper()}")
    click.echo(f"Owner ID:      {peer.get('owner_id')}")
    click.echo(f"Last Seen:     {peer.get('last_seen_at') or 'Never'}")
    click.echo(f"Registered At: {peer.get('registered_at') or peer.get('created_at')}")

    caps = peer.get("gpu_capabilities", [])
    click.echo(f"\nGPU Capabilities ({len(caps)}):")
    if not caps:
        click.echo("  (None)")
    for i, g in enumerate(caps, 1):
        click.echo(f"  Device #{i}:")
        click.echo(f"    GPU Model:          {g.get('gpu_name')}")
        click.echo(f"    Total VRAM:         {g.get('vram_mb')} MiB")
        click.echo(f"    Driver Version:     {g.get('driver_version') or 'N/A'}")
        click.echo(f"    CUDA Version:       {g.get('cuda_version') or 'N/A'}")
        click.echo(f"    Compute Capability: {g.get('compute_capability') or 'N/A'}")


@peers.command("register")
@click.option("--owner-id", default=None, help="Owner user UUID (defaults to configured user ID)")
@click.option("--hostname", required=True, help="Peer hostname or alias")
@click.option("--gpu", "gpu_name", default="NVIDIA GeForce RTX 4090", help="GPU model name")
@click.option("--vram", "vram_mb", default=24576, type=int, help="Total GPU VRAM in MiB")
@click.option("--driver", "driver_version", default=None, help="Driver version string")
@click.option("--cuda", "cuda_version", default=None, help="CUDA version string")
@click.option("--compute", "compute_capability", default=None, help="Compute capability string")
@click.pass_context
def peers_register(
    ctx: click.Context,
    owner_id: str | None,
    hostname: str,
    gpu_name: str,
    vram_mb: int,
    driver_version: str | None,
    cuda_version: str | None,
    compute_capability: str | None,
) -> None:
    """Register a provider peer node with GPU hardware capabilities."""
    client: CoordinatorClient = ctx.obj["client"]
    target_owner = owner_id or client.user_id
    try:
        peer = client.register_peer(
            owner_id=target_owner,
            hostname=hostname,
            gpu_name=gpu_name,
            vram_mb=vram_mb,
            driver_version=driver_version,
            cuda_version=cuda_version,
            compute_capability=compute_capability,
        )
        click.echo("[+] Peer registered successfully!")
        click.echo(f"Peer ID:  {peer.get('id')}")
        click.echo(f"Hostname: {peer.get('hostname')}")
        click.echo(f"Status:   {str(peer.get('status')).upper()}")
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Registration failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Jobs Command Group
# ---------------------------------------------------------------------------
@cli.group()
def jobs() -> None:
    """Submit, inspect, track, and cancel GPU compute jobs."""


@jobs.command("submit")
@click.option(
    "--preset",
    "-p",
    type=click.Choice(list(WORKLOAD_PRESETS.keys()), case_sensitive=False),
    default=None,
    help="Workload preset: matrix_multiply, vector_add, benchmark, docker",
)
@click.option("--name", "-n", default=None, help="Human-readable job name")
@click.option("--workload-type", "-t", default=None, help="Workload type (e.g. matrix_multiply)")
@click.option("--command", "-c", default=None, help="Execution target or operation")
@click.option("--vram", "-v", "vram_mb", default=None, type=int, help="Required GPU VRAM in MiB")
@click.option("--docker-image", default=None, help="Docker image for container workloads")
@click.pass_context
def jobs_submit(
    ctx: click.Context,
    preset: str | None,
    name: str | None,
    workload_type: str | None,
    command: str | None,
    vram_mb: int | None,
    docker_image: str | None,
) -> None:
    """Submit a GPU computational workload to the CrowdGPU cluster."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        params = resolve_workload(
            preset_name=preset,
            name=name,
            workload_type=workload_type,
            command=command,
            vram_mb=vram_mb,
            docker_image=docker_image,
        )
    except ValueError as exc:
        raise click.ClickException(f"Invalid job parameters: {exc}") from exc

    try:
        job = client.submit_job(
            name=params["name"],
            command=params["command"],
            required_vram_mb=params["required_vram_mb"],
            workload_type=params["workload_type"],
            docker_image=params["docker_image"],
        )
        click.echo("[+] Job submitted successfully!")
        click.echo(f"Job ID:        {job.get('id')}")
        click.echo(f"Name:          {job.get('name')}")
        click.echo(f"Status:        {str(job.get('status')).upper()}")
        click.echo(f"Workload:      {job.get('workload_type')}")
        click.echo(f"Required VRAM: {job.get('vram_required_mb', 0)} MiB")
        if job.get("assigned_peer_id"):
            peer_name = job.get("peer_hostname") or job.get("assigned_peer_id")
            click.echo(f"Assigned Peer: {peer_name}")
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except CoordinatorAuthError as exc:
        raise click.ClickException(f"Auth error: {exc}") from exc
    except CoordinatorValidationError as exc:
        raise click.ClickException(f"Validation error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Job submission failed: {exc}") from exc


@jobs.command("list")
@click.option(
    "--status",
    "-s",
    default=None,
    help="Filter by status: QUEUED, ASSIGNED, RUNNING, COMPLETED, FAILED, CANCELLED",
)
@click.option("--limit", default=50, type=int, help="Maximum number of jobs to list")
@click.pass_context
def jobs_list(ctx: click.Context, status: str | None, limit: int) -> None:
    """List compute jobs with optional status filtering."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        jobs_data = client.list_jobs(status=status, limit=limit)
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except CoordinatorAuthError as exc:
        raise click.ClickException(f"Auth error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to list jobs: {exc}") from exc

    if not jobs_data:
        msg = f"No jobs found with status '{status}'." if status else "No jobs found."
        click.echo(msg)
        return

    click.echo(f"{'JOB ID':<38} {'NAME':<28} {'STATUS':<12} {'WORKLOAD':<18} {'ASSIGNED PEER'}")
    click.echo("-" * 115)
    for job in jobs_data:
        peer = job.get("peer_hostname") or str(job.get("assigned_peer_id") or "None")
        w_type = job.get("workload_type") or job.get("command", "")
        click.echo(
            f"{str(job.get('id', '')):<38} {str(job.get('name', ''))[:26]:<28} "
            f"{str(job.get('status', '')).upper():<12} {str(w_type)[:16]:<18} {peer}"
        )


@jobs.command("status")
@click.argument("job_id")
@click.pass_context
def jobs_status(ctx: click.Context, job_id: str) -> None:
    """Display comprehensive details, status, and execution results for a job."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        job = client.get_job(job_id)
    except CoordinatorNotFoundError:
        raise click.ClickException(f"Job '{job_id}' not found.")
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except CoordinatorAuthError as exc:
        raise click.ClickException(f"Auth error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to get job: {exc}") from exc

    click.echo("=== Job Details ===")
    click.echo(f"Job ID:        {job.get('id')}")
    click.echo(f"Name:          {job.get('name')}")
    click.echo(f"Status:        {str(job.get('status')).upper()}")
    click.echo(f"Workload Type: {job.get('workload_type') or 'N/A'}")
    click.echo(f"Command:       {job.get('command')}")
    click.echo(f"Required VRAM: {job.get('vram_required_mb', 0)} MiB")
    click.echo(f"Attempts:      {job.get('attempt_count', 0)}")

    assigned_peer = job.get("assigned_peer_id")
    if assigned_peer:
        peer_host = job.get("peer_hostname")
        host_str = f" ({peer_host})" if peer_host else ""
        click.echo(f"Assigned Peer: {assigned_peer}{host_str}")
        if job.get("gpu_name"):
            click.echo(f"GPU Hardware:  {job.get('gpu_name')}")
    else:
        click.echo("Assigned Peer: (Unassigned)")

    click.echo(f"Submitted At:  {job.get('created_at') or 'N/A'}")
    if job.get("started_at"):
        click.echo(f"Started At:    {job.get('started_at')}")
    if job.get("completed_at"):
        click.echo(f"Completed At:  {job.get('completed_at')}")

    # Results section
    result = job.get("result")
    error = job.get("error")

    if result or error:
        click.echo("\n--- Execution Outcome ---")
        if error:
            click.echo(f"Error Message: {error}")
        if isinstance(result, dict):
            if "exit_code" in result:
                click.echo(f"Exit Code:     {result.get('exit_code')}")
            if "execution_time_s" in result:
                click.echo(f"Duration:      {result.get('execution_time_s'):.4f}s")
            out = result.get("output")
            if out:
                click.echo("Output Data:")
                if isinstance(out, dict):
                    click.echo(_format_dict(out, indent=4))
                else:
                    click.echo(f"    {out}")
            if result.get("stdout_tail"):
                click.echo(f"Stdout Tail:\n{result.get('stdout_tail')}")


@jobs.command("cancel")
@click.argument("job_id")
@click.pass_context
def jobs_cancel(ctx: click.Context, job_id: str) -> None:
    """Cancel an eligible QUEUED job."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        job = client.cancel_job(job_id)
        click.echo(f"[+] Job {job.get('id')} cancelled successfully.")
        click.echo(f"Status: {str(job.get('status')).upper()}")
    except CoordinatorNotFoundError:
        raise click.ClickException(f"Job '{job_id}' not found.")
    except InvalidStateTransitionError as exc:
        raise click.ClickException(f"Cannot cancel job: {exc}") from exc
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Cancellation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# WebRTC Peer-to-Peer Diagnostics (Preserved from Person 4)
# ---------------------------------------------------------------------------
@cli.group()
def webrtc() -> None:
    """WebRTC peer-to-peer data channel diagnostics and signaling status."""


@webrtc.command("status")
@click.pass_context
def webrtc_status(ctx: click.Context) -> None:
    """Show active WebRTC signaling peers and configured STUN/TURN ICE servers."""
    client: CoordinatorClient = ctx.obj["client"]
    try:
        peers_data = client.list_signaling_peers()
        ice_data = client.get_ice_servers()
    except CoordinatorConnectionError as exc:
        raise click.ClickException(f"Connection error: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Failed to query WebRTC status: {exc}") from exc

    click.echo("=== WebRTC Signaling Status ===")
    click.echo(f"Connected Peers Count: {peers_data.get('count', 0)}")
    click.echo(f"Connected Peers:       {', '.join(peers_data.get('connected_peers', [])) or 'None'}")
    click.echo("\nConfigured ICE Servers:")
    for server in ice_data.get("ice_servers", []):
        urls = ", ".join(server.get("urls", []))
        user = server.get("username")
        click.echo(f"  - URLs: {urls}" + (f" (User: {user})" if user else ""))


@webrtc.command("listen")
@click.option("--peer-id", required=True, help="Receiver peer ID to register with signaling")
@click.option("--stun", "stun_server", default=None, help="Optional STUN server URL")
@click.option("--timeout", default=60, type=int, help="Maximum listening time in seconds (0 = forever)")
@click.option("--auto-echo/--no-auto-echo", default=True, help="Automatically verify and acknowledge received P2P messages")
@click.pass_context
def webrtc_listen(
    ctx: click.Context,
    peer_id: str,
    stun_server: str | None,
    timeout: int,
    auto_echo: bool,
) -> None:
    """Run WebRTC receiver peer, listen for RTCDataChannel connections and direct P2P messages."""
    import asyncio

    try:
        from cli.webrtc.peer import WebRTCPeer
        from cli.webrtc.protocol import verify_p2p_message
    except ImportError as exc:
        raise click.ClickException(
            f"WebRTC dependencies not installed: {exc}. Install with: pip install aiortc websockets"
        ) from exc

    client: CoordinatorClient = ctx.obj["client"]
    ice_servers = [stun_server] if stun_server else None

    async def _run() -> None:
        peer = WebRTCPeer(
            peer_id=peer_id,
            coordinator_url=client.base_url,
            role="receiver",
            ice_servers=ice_servers,
            auto_echo=auto_echo,
        )
        click.echo(f"[*] Starting WebRTC Receiver Peer: '{peer_id}'")
        click.echo(f"[*] Coordinator Signaling: {client.base_url}")
        click.echo(f"[*] Auto-ACK direct P2P messages: {'Enabled' if auto_echo else 'Disabled'}")

        await peer.start()
        click.echo(f"[+] Registered with signaling gateway as '{peer_id}'")
        click.echo("[*] Waiting for remote peer connection and data channel...")

        try:
            wait_limit = timeout if timeout > 0 else None
            await asyncio.wait_for(peer.channel_open.wait(), timeout=wait_limit)
            ice_state = peer.pc.iceConnectionState if peer.pc else "N/A"
            click.echo(f"[+] RTCDataChannel opened successfully with '{peer.target_id}'!")
            click.echo(f"[*] ICE Connection State: {ice_state}")
            click.echo("[*] Listening for direct RTCDataChannel payloads (Press Ctrl+C to stop)...")

            start_time = asyncio.get_event_loop().time()
            while True:
                if peer.channel_closed.is_set():
                    click.echo("[*] Remote peer closed data channel or disconnected.")
                    break

                if timeout > 0:
                    remaining = timeout - (asyncio.get_event_loop().time() - start_time)
                    if remaining <= 0:
                        click.echo("[*] Listen timeout reached.")
                        break
                else:
                    remaining = None

                poll_timeout = min(remaining, 1.0) if remaining else 1.0
                try:
                    msg = await asyncio.wait_for(peer.message_queue.get(), timeout=poll_timeout)
                    is_valid, reason, parsed = verify_p2p_message(msg)
                    if is_valid and parsed:
                        click.echo(f"[<] Direct P2P Message from '{peer.target_id}':")
                        click.echo(f"    - Protocol:        {parsed.get('protocol')}")
                        click.echo(f"    - Request ID:      {parsed.get('request_id')}")
                        click.echo(f"    - Type:            {parsed.get('type')}")
                        click.echo(f"    - SHA-256 Hash:    {parsed.get('payload_sha256')} (VERIFIED)")
                        click.echo(f"    - Payload:         {parsed.get('payload')}")
                        if auto_echo:
                            click.echo(f"[>] Direct P2P ACK dispatched over RTCDataChannel (Response To: {parsed.get('request_id')})")
                    else:
                        click.echo(f"[<] Direct message from '{peer.target_id}': {msg}")
                except TimeoutError:
                    continue

        except TimeoutError:
            click.echo("[-] Timed out waiting for connection or data channel.")
        except KeyboardInterrupt:
            click.echo("\n[*] Stopping listener on user request...")
        finally:
            await peer.close()
            click.echo("[*] Receiver peer closed cleanly.")

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@webrtc.command("connect")
@click.option("--peer-id", required=True, help="Initiator peer ID")
@click.option("--target-id", required=True, help="Target receiver peer ID")
@click.option("--message", default="CrowdGPU Direct P2P Test", help="Message or data description")
@click.option("--stun", "stun_server", default=None, help="Optional STUN server URL")
@click.option("--timeout", default=15.0, type=float, help="Connection timeout in seconds")
@click.pass_context
def webrtc_connect(
    ctx: click.Context,
    peer_id: str,
    target_id: str,
    message: str,
    stun_server: str | None,
    timeout: float,
) -> None:
    """Connect to a target WebRTC peer, send a structured payload over RTCDataChannel, and verify direct ACK."""
    import asyncio
    import time
    import uuid

    try:
        from cli.webrtc.peer import WebRTCPeer
    except ImportError as exc:
        raise click.ClickException(
            f"WebRTC dependencies not installed: {exc}. Install with: pip install aiortc websockets"
        ) from exc

    client: CoordinatorClient = ctx.obj["client"]
    ice_servers = [stun_server] if stun_server else None

    async def _run() -> None:
        peer = WebRTCPeer(
            peer_id=peer_id,
            coordinator_url=client.base_url,
            role="initiator",
            target_id=target_id,
            ice_servers=ice_servers,
        )
        click.echo(f"[*] Starting WebRTC Initiator: '{peer_id}' -> Target: '{target_id}'")
        click.echo(f"[*] Coordinator Signaling: {client.base_url}")

        t0 = time.time()
        await peer.start()
        click.echo(f"[+] Registered with signaling gateway as '{peer_id}'")
        click.echo(f"[*] Dispatched SDP offer to '{target_id}'. Awaiting handshake...")

        try:
            await asyncio.wait_for(peer.channel_open.wait(), timeout=timeout)
            t_open = time.time() - t0
            pc_state = peer.pc.connectionState if peer.pc else "N/A"
            ice_state = peer.pc.iceConnectionState if peer.pc else "N/A"
            click.echo(f"[+] RTCDataChannel opened in {t_open:.2f}s!")
            click.echo(f"[*] RTCPeerConnection State: {pc_state}")
            click.echo(f"[*] ICE Connection State:    {ice_state}")

            # Send structured P2P message
            payload_data = {
                "message": message,
                "session_nonce": uuid.uuid4().hex[:8],
                "transport": "WebRTC RTCDataChannel (Direct P2P)",
            }
            click.echo(f"[*] Sending structured P2P payload directly over data channel...")
            res = await peer.send_p2p_request(payload=payload_data, timeout=timeout)

            click.echo(f"[>] Dispatched message:")
            click.echo(f"    - Request ID:     {res['request_id']}")
            click.echo(f"    - Payload SHA256: {res['payload_sha256']}")
            click.echo(f"[<] Direct P2P Acknowledgement received in {res['rtt_ms']:.1f}ms!")
            click.echo(f"    - Response To:    {res['ack'].get('response_to')}")
            click.echo(f"    - Verified Hash:  {res['ack'].get('verified_sha256')} (INTEGRITY MATCH)")
            click.echo(f"    - Status:         {res['ack'].get('status')}")
            click.echo("[+] Bi-directional WebRTC peer-to-peer data channel VERIFIED (Zero HTTP payload relay)!")

        except TimeoutError as exc:
            click.echo("[-] Connection or data channel handshake timed out.")
            raise click.ClickException("WebRTC connection failed: handshake timed out") from exc
        finally:
            await peer.close()
            click.echo("[*] Initiator peer closed cleanly.")

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    cli()
