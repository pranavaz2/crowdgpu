"""
Tests for worker startup and configuration.
"""

from worker.config import WorkerSettings
from worker.status import WorkerStatus, get_status


def test_settings_loads_defaults() -> None:
    """WorkerSettings should load with default values without requiring env vars."""
    s = WorkerSettings()
    assert s.worker_mode in ("development", "production")
    assert s.worker_id
    assert s.worker_coordinator_url.startswith("http")


def test_development_mode_default() -> None:
    """Default mode should be development."""
    s = WorkerSettings()
    assert s.worker_mode == "development"


def test_get_status_development_mode() -> None:
    """get_status() should return a WorkerStatus in development mode."""
    status = get_status()
    assert isinstance(status, WorkerStatus)


def test_status_mode_is_development() -> None:
    """Status mode field should be development."""
    status = get_status()
    assert status.mode == "development"


def test_status_gpu_not_available_in_dev() -> None:
    """GPU should not be reported as available in development mode."""
    status = get_status()
    assert status.gpu_available is False


def test_status_has_timestamp() -> None:
    """Status should include a non-empty timestamp."""
    status = get_status()
    assert status.timestamp
