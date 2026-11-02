"""
Prometheus metrics registry and definitions.
"""

from prometheus_client import Counter, Gauge

# Gauges
QUEUED_JOBS = Gauge(
    "crowdgpu_queued_jobs",
    "Current count of jobs in QUEUED status",
)
RUNNING_JOBS = Gauge(
    "crowdgpu_running_jobs",
    "Current count of jobs currently executing on worker peers",
)
AVAILABLE_PEERS = Gauge(
    "crowdgpu_available_peers",
    "Current count of peers with available status and fresh heartbeat",
)

# Counters
JOBS_SUBMITTED_TOTAL = Counter(
    "crowdgpu_jobs_submitted_total",
    "Total count of jobs submitted to the coordinator",
)
JOBS_COMPLETED_TOTAL = Counter(
    "crowdgpu_jobs_completed_total",
    "Total count of successfully completed jobs",
)
JOBS_FAILED_TOTAL = Counter(
    "crowdgpu_jobs_failed_total",
    "Total count of failed jobs",
)
SCHEDULER_ATTEMPTS_TOTAL = Counter(
    "crowdgpu_scheduler_attempts_total",
    "Total count of scheduler matching passes attempted",
)
SCHEDULER_ASSIGNMENTS_TOTAL = Counter(
    "crowdgpu_scheduler_assignments_total",
    "Total count of successful peer assignments made by scheduler",
)
