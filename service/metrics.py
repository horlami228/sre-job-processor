from prometheus_client import Counter, Histogram, Gauge

# Total jobs submitted
JOBS_SUBMITTED = Counter(
    "jobs_submitted_total",
    "Total number of jobs submitted"
)

# Jobs completed by final status
JOBS_COMPLETED = Counter(
    "jobs_completed_total",
    "Total number of jobs completed",
    ["status"]  # label: done or failed
)

# How long jobs take to process
JOB_PROCESSING_DURATION = Histogram(
    "job_processing_duration_seconds",
    "Time spent processing a job",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Current queue depth — this is a Gauge because it goes up and down
QUEUE_DEPTH = Gauge(
    "job_queue_depth",
    "Number of jobs currently pending in Redis"
)

# Jobs stuck in processing — the stuck job metric
JOBS_STUCK = Gauge(
    "jobs_stuck_processing",
    "Number of jobs stuck in processing state"
)