# Runbook: HighProcessingTime (p95 / p99)

## Alert Details

### HighProcessingTime95thPercentile

- **Severity:** Warning
- **Fires when:** p95 job processing time exceeds your threshold for 5 minutes
- **Meaning:** 5% of jobs are taking longer than expected

### HighProcessingTime99thPercentile

- **Severity:** Critical
- **Fires when:** p99 job processing time exceeds your threshold for 5 minutes
- **Meaning:** 1% of jobs are taking extremely long — your slowest tail is growing

## What is this?

Jobs are taking longer to process than the established baseline.
This does not mean jobs are failing — they are completing, just slowly.
Left unresolved, slow processing leads to queue depth growing, which
leads to further delays, which can cascade into a full outage.

## Impact

- Users waiting longer than expected for job results
- Queue depth may start growing if processing is slow enough
- If p99 is high, a small number of jobs may be timing out upstream

---

## Diagnosis Steps

### Step 1 — Confirm current processing times

In Prometheus:

```
# p95
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket{job="job-worker"}[5m]))

# p99
histogram_quantile(0.99, rate(job_processing_duration_seconds_bucket{job="job-worker"}[5m]))
```

How far above the baseline are we? Is it still climbing or stabilizing?

### Step 2 — Check when slowdown started

Look at the **Processing Time p95 vs p99** panel in Grafana.

- Sudden spike → likely a specific event — deployment, traffic surge, dependency change
- Gradual increase → likely a resource leak or growing dataset

### Step 3 — Check if queue depth is also growing

```bash
curl http://localhost:8080/queue/depth
```

If queue is growing alongside slow processing — workers can't keep up.
If queue is stable — slowness is contained, less urgent.

### Step 4 — Check Postgres query performance

Slow database queries are the most common cause of slow job processing.

```sql
-- find slow queries running right now
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
AND now() - pg_stat_activity.query_start > INTERVAL '1 second'
ORDER BY duration DESC;
```

```sql
-- check if jobs table is missing indexes or doing full scans
EXPLAIN ANALYZE
SELECT * FROM jobs WHERE status = 'pending' LIMIT 10;
```

### Step 5 — Check worker memory and CPU

```bash
# find the worker process ID
ps aux | grep worker.py

# check its resource usage
top -p <pid>
```

High memory usage can cause swapping which makes everything slow.
High CPU could mean the processing logic itself is expensive.

### Step 6 — Check if a specific type of payload is slow

```sql
-- find jobs that took the longest recently
SELECT id, payload,
       EXTRACT(EPOCH FROM (updated_at - created_at)) AS duration_seconds
FROM jobs
WHERE status = 'done'
AND updated_at > NOW() - INTERVAL '30 minutes'
ORDER BY duration_seconds DESC
LIMIT 20;
```

Is there a pattern in the slow jobs? Same payload type? Same size?

### Step 7 — Check for lock contention in Postgres

```sql
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_statement,
       blocking_activity.query AS blocking_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

If rows are returned — there is lock contention. Queries are blocking each other.

---

## Resolution Steps

### Option A — Slow Postgres queries

```sql
-- kill a specific slow query
SELECT pg_terminate_backend(<pid>);

-- or kill all queries running longer than 5 minutes
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE now() - query_start > INTERVAL '5 minutes'
AND state != 'idle';
```

Then investigate why the query was slow — missing index, table bloat, bad query plan.

### Option B — Worker running out of memory

```bash
# check current memory
free -h

# restart the worker to clear memory
sudo systemctl restart worker
```

If it keeps happening — add memory limits and monitoring, escalate for permanent fix.

### Option C — Traffic surge causing slowness

```bash
# scale up workers temporarily
python worker.py &  # run a second worker instance

# in Kubernetes
kubectl scale deployment job-worker --replicas=3
```

### Option D — Specific payload type is slow

If certain payloads consistently take much longer:

- Add payload size or type validation at submission time
- Rate limit submissions of expensive payload types
- Escalate to developers to optimize processing logic for that payload type

### Option E — Recent deployment caused regression

```bash
git log --oneline -5
# identify the last deployment

git revert HEAD
sudo systemctl restart worker
```

---

## Confirm Resolution

1. In Prometheus — p95 and p99 returning to baseline:

```
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket{job="job-worker"}[5m]))
```

2. Grafana — **Processing Time p95 vs p99** panel trending back down
3. Grafana — **Queue Depth** stable or decreasing

---

## Escalate if:

- p99 is more than 5x the baseline and cause is not obvious
- Postgres queries are slow but no locking or missing indexes found
- Slowness persists after worker restart and scaling
- Queue depth is growing alongside the slowness — becoming a full outage

---

## Related Alerts

- `QueueDepthTooHigh` — often follows high processing time
- `HighJobFailureRate` — jobs timing out can show up as failures
- `StuckJobsDetected` — extreme slowness can look like stuck jobs

---

## Post-Incident

File a postmortem if:

- p99 exceeded 3x baseline for more than 15 minutes
- Queue depth grew significantly as a result
- Root cause was a missing database index — add index review to deployment checklist
- Root cause was a code regression — add performance benchmarks to CI pipeline
