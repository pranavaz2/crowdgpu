"""
CrowdGPU CLI — main entry point.

Bootstrap phase: only --help and --version are implemented.
Job submission, session management and other commands will be added in later phases.
"""

import click

from cli import __version__
from cli.client import CoordinatorClient


@click.group()
@click.version_option(version=__version__, prog_name="crowdgpu-cli")
def cli() -> None:
    """
    CrowdGPU — Intelligent P2P GPU Resource Sharing Platform.

    \b
    Use --help on any subcommand for detailed usage information.

    \b
    Status: Bootstrap phase.
    Commands for job submission, session management, and resource listing
    will be available in subsequent phases.
    """


# ---------------------------------------------------------------------------
# Planned command groups (stubs — not implemented in bootstrap)
# ---------------------------------------------------------------------------

@cli.group()
def jobs() -> None:
    """Manage GPU compute jobs."""


@jobs.command("submit")
@click.option("--owner-id", required=True, help="Owner UUID")
@click.option("--docker-image", required=True, help="Docker image to run")
@click.option("--command", required=True, help="Command to execute inside the container")
def jobs_submit(owner_id: str, docker_image: str, command: str) -> None:
    """Submit a GPU compute job."""
    client = CoordinatorClient()
    try:
        job = client.submit_job(owner_id, docker_image, command)
        click.echo(f"Job submitted successfully. Job ID: {job['id']}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@jobs.command("list")
@click.option("--owner-id", help="Filter by owner UUID")
def jobs_list(owner_id: str | None) -> None:
    """List jobs."""
    client = CoordinatorClient()
    try:
        jobs_data = client.list_jobs(owner_id)
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not jobs_data:
        click.echo("No jobs found.")
        return

    click.echo(f"{'ID':<38} {'Owner':<38} {'Status':<10} {'Image'}")
    click.echo("-" * 100)
    for job in jobs_data:
        click.echo(f"{job['id']:<38} {job['owner_id']:<38} {job['status']:<10} {job['docker_image']}")


@jobs.command("status")
@click.argument("job_id")
def jobs_status(job_id: str) -> None:
    """Get job status."""
    client = CoordinatorClient()
    try:
        job = client.get_job(job_id)
        click.echo(f"Job ID: {job['id']}")
        click.echo(f"Status: {job['status']}")
        click.echo(f"Image:  {job['docker_image']}")
        click.echo(f"Command: {job['command']}")
        if job.get("assigned_peer_id"):
            click.echo(f"Assigned Peer: {job['assigned_peer_id']}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@jobs.command("assign")
@click.argument("job_id")
@click.option("--peer-id", required=True, help="Peer UUID to assign this job to")
def jobs_assign(job_id: str, peer_id: str) -> None:
    """Assign a pending compute job to a peer."""
    client = CoordinatorClient()
    try:
        job = client.assign_job(job_id=job_id, peer_id=peer_id)
        click.echo(f"Job {job['id']} assigned to peer {job['assigned_peer_id']}. Status: {job['status']}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@jobs.command("schedule")
def jobs_schedule() -> None:
    """Trigger coordinator scheduler to dispatch oldest pending job to an available peer."""
    client = CoordinatorClient()
    try:
        job = client.schedule_job()
        if not job:
            click.echo("No pending jobs or no available peers for scheduling.")
            return
        click.echo(f"Scheduled job {job['id']} to peer {job['assigned_peer_id']}. Status: {job['status']}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@cli.group()
def sessions() -> None:
    """Manage remote rendering sessions. (Not yet implemented)"""


@sessions.command("start")
def sessions_start() -> None:
    """Start a remote rendering session. (Not yet implemented)"""
    raise click.ClickException(
        "Remote sessions are not implemented in the bootstrap phase."
    )


@cli.group()
def peers() -> None:
    """List and inspect GPU peers."""


@peers.command("register")
@click.option("--owner-id", required=True, help="Owner user UUID")
@click.option("--hostname", required=True, help="Peer hostname or alias")
@click.option("--gpu", "gpu_name", default="NVIDIA GeForce RTX 4090", help="GPU model name")
@click.option("--vram", "vram_mb", default=24576, type=int, help="Total GPU VRAM in MiB")
def peers_register(owner_id: str, hostname: str, gpu_name: str, vram_mb: int) -> None:
    """Register a provider peer node with GPU capabilities."""
    client = CoordinatorClient()
    try:
        peer = client.register_peer(owner_id=owner_id, hostname=hostname, gpu_name=gpu_name, vram_mb=vram_mb)
        click.echo(f"Peer registered successfully. Peer ID: {peer['id']}")
        click.echo(f"Hostname: {peer['hostname']}, Status: {peer['status']}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@peers.command("list")
def peers_list() -> None:
    """List available GPU peers."""
    client = CoordinatorClient()
    try:
        peers_data = client.list_peers()
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not peers_data:
        click.echo("No peers found.")
        return

    # Basic table formatting
    click.echo(f"{'ID':<38} {'Hostname':<20} {'Status':<10} {'GPUs'}")
    click.echo("-" * 80)
    for peer in peers_data:
        gpus = peer.get("gpu_capabilities", [])
        gpu_summary = ", ".join(f"{g['gpu_name']} ({g['vram_mb']} MiB)" for g in gpus)
        click.echo(f"{peer['id']:<38} {peer['hostname']:<20} {peer['status']:<10} {gpu_summary}")


# ---------------------------------------------------------------------------
# WebRTC Peer-to-Peer Data Channel Commands
# ---------------------------------------------------------------------------

@cli.group()
def webrtc() -> None:
    """WebRTC peer-to-peer data channel management and connectivity."""


@webrtc.command("status")
@click.option("--coordinator-url", default=None, help="Coordinator URL override")
def webrtc_status(coordinator_url: str | None) -> None:
    """Show active WebRTC signaling peers and configured ICE servers."""
    client = CoordinatorClient()
    if coordinator_url:
        client.base_url = coordinator_url.rstrip("/")

    try:
        peers_data = client.list_signaling_peers()
        ice_data = client.get_ice_servers()
    except Exception as exc:
        raise click.ClickException(str(exc))

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
@click.option("--coordinator-url", default=None, help="Coordinator URL override")
@click.option("--stun", "stun_server", default=None, help="Optional STUN server URL")
@click.option("--timeout", default=60, type=int, help="Maximum listening time in seconds (0 = forever)")
@click.option("--auto-echo/--no-auto-echo", default=True, help="Automatically echo back received messages")
def webrtc_listen(
    peer_id: str,
    coordinator_url: str | None,
    stun_server: str | None,
    timeout: int,
    auto_echo: bool,
) -> None:
    """Run WebRTC receiver peer, wait for connection, and receive data channel messages."""
    import asyncio

    from cli.config import settings
    from cli.webrtc.peer import WebRTCPeer

    coord_url = coordinator_url or settings.coordinator_url
    ice_servers = [stun_server] if stun_server else None

    async def _run() -> None:
        peer = WebRTCPeer(
            peer_id=peer_id,
            coordinator_url=coord_url,
            role="receiver",
            ice_servers=ice_servers,
            auto_echo=auto_echo,
        )

        click.echo(f"[*] Starting WebRTC Receiver: '{peer_id}'")
        click.echo(f"[*] Coordinator: {coord_url}")
        click.echo(f"[*] Auto-echo replies: {'Enabled' if auto_echo else 'Disabled'}")

        await peer.start()
        click.echo(f"[+] Registered with signaling gateway as '{peer_id}'")
        click.echo("[*] Waiting for remote peer connection and data channel...")

        try:
            wait_limit = timeout if timeout > 0 else None
            await asyncio.wait_for(peer.channel_open.wait(), timeout=wait_limit)
            ice_state = peer.pc.iceConnectionState if peer.pc else "N/A"
            click.echo(f"[+] RTCDataChannel opened successfully with '{peer.target_id}'!")
            click.echo(f"[*] ICE Connection State: {ice_state}")

            # Keep listening for messages
            click.echo("[*] Listening for incoming messages (Press Ctrl+C to stop)...")
            start_time = asyncio.get_event_loop().time()
            while True:
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
                    click.echo(f"[<] Message from '{peer.target_id}': {msg}")
                except TimeoutError:
                    continue

        except TimeoutError:
            click.echo("[-] Timed out waiting for connection or data channel.")
        except KeyboardInterrupt:
            click.echo("\n[*] Stopping listener on user request...")
        finally:
            await peer.close()
            click.echo("[*] Receiver peer closed.")

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@webrtc.command("connect")
@click.option("--peer-id", required=True, help="Initiator peer ID to register with signaling")
@click.option("--target-id", required=True, help="Target receiver peer ID")
@click.option("--coordinator-url", default=None, help="Coordinator URL override")
@click.option("--message", default="Hello from CrowdGPU WebRTC Peer!", help="Message to transmit")
@click.option("--stun", "stun_server", default=None, help="Optional STUN server URL")
@click.option("--timeout", default=15.0, type=float, help="Connection timeout in seconds")
def webrtc_connect(
    peer_id: str,
    target_id: str,
    coordinator_url: str | None,
    message: str,
    stun_server: str | None,
    timeout: float,
) -> None:
    """Connect to a target WebRTC peer, send a message over RTCDataChannel, and await reply."""
    import asyncio
    import time

    from cli.config import settings
    from cli.webrtc.peer import WebRTCPeer

    coord_url = coordinator_url or settings.coordinator_url
    ice_servers = [stun_server] if stun_server else None

    async def _run() -> None:
        peer = WebRTCPeer(
            peer_id=peer_id,
            coordinator_url=coord_url,
            role="initiator",
            target_id=target_id,
            ice_servers=ice_servers,
        )

        click.echo(f"[*] Starting WebRTC Initiator: '{peer_id}' -> Target: '{target_id}'")
        click.echo(f"[*] Coordinator: {coord_url}")

        t0 = time.time()
        await peer.start()
        click.echo(f"[+] Registered with signaling gateway as '{peer_id}'")
        click.echo(f"[*] SDP offer dispatched to '{target_id}'. Waiting for handshake...")

        try:
            await asyncio.wait_for(peer.channel_open.wait(), timeout=timeout)
            t_open = time.time() - t0
            pc_state = peer.pc.connectionState if peer.pc else "N/A"
            ice_state = peer.pc.iceConnectionState if peer.pc else "N/A"
            click.echo(f"[+] RTCDataChannel opened in {t_open:.2f}s!")
            click.echo(f"[*] RTCPeerConnection State: {pc_state}")
            click.echo(f"[*] ICE Connection State:    {ice_state}")

            # Send payload
            click.echo(f"[>] Sending message: '{message}'")
            t_send = time.time()
            await peer.send_message(message)

            # Wait for reply
            click.echo("[*] Waiting for reply from remote peer...")
            try:
                reply = await asyncio.wait_for(peer.wait_for_message(), timeout=timeout)
                t_rtt = (time.time() - t_send) * 1000.0
                click.echo(f"[<] Reply received in {t_rtt:.1f}ms: '{reply}'")
                click.echo("[+] Bi-directional WebRTC data-channel communication VERIFIED!")
            except TimeoutError:
                click.echo("[!] No reply received within timeout.")

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
