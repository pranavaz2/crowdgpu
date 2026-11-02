"""
CrowdGPU CLI — main entry point.

Bootstrap phase: only --help and --version are implemented.
Job submission, session management and other commands will be added in later phases.
"""

import click

from cli import __version__


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
    """Manage GPU compute jobs. (Not yet implemented)"""


@jobs.command("submit")
def jobs_submit() -> None:
    """Submit a GPU compute job. (Not yet implemented)"""
    raise click.ClickException(
        "Job submission is not implemented in the bootstrap phase."
    )


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
    """List and inspect GPU peers. (Not yet implemented)"""


@peers.command("list")
def peers_list() -> None:
    """List available GPU peers. (Not yet implemented)"""
    raise click.ClickException(
        "Peer listing is not implemented in the bootstrap phase."
    )


if __name__ == "__main__":
    cli()
