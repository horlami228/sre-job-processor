# Runbook: StuckJobsDetected

## Alert Details

- **Severity:** Critical
- **Alert name:** StuckJobsDetected
- **Fires when:** `jobs_stuck_processing > 0` for more than 1 minute

## What is this?

One or more jobs have been in `processing` state for too long.
This means a worker picked up the job, marked it as `processing` in Postgres,
then crashed before finishing. The job is now orphaned — it will never
complete because it has already been removed from the Redis queue.

## Impact

- Affected jobs will never complete
- Users or systems waiting on these jobs are blocked
- The longer this goes unresolved, the more jobs may pile up behind it

---

## Diagnosis Steps

### Step 1 — Confirm how many jobs are stuck and for how long

```sql
SELECT id, payload, created_at, updated_at,
       NOW() - updated_at AS stuck_for
FROM jobs
WHERE status = 'processing'
AND updated_at < NOW() - INTERVAL '5 minutes'
ORDER BY updated_at ASC;
```

If this returns nothing — the alert may have already resolved. Confirm in Grafana.

### Step 2 — Check if the worker is running

```bash
curl http://localhost:8001/metrics | grep "^up"
```

- Returns `up 1` → worker is alive, it crashed on a specific job
- Returns `up 0` or connection refused → worker process is down, go to Step 5

### Step 3 — Check worker logs for the crash reason

```bash
# if running as a process
journalctl -u worker -n 100 --no-pager

# if running manually in terminal
# check the terminal where worker.py is running
```

Look for:

- `ERROR` lines around the time the job got stuck
- `OOMKilled` — worker ran out of memory
- Unhandled exceptions
- Database connection errors

### Step 4 — Inspect the stuck job's payload

```sql
SELECT id, payload, error, created_at, updated_at
FROM jobs
WHERE status = 'processing'
AND updated_at < NOW() - INTERVAL '5 minutes';
```

Does the payload look malformed or unusually large?
A bad payload that causes the worker to crash on every attempt
will cause the same job to get stuck repeatedly after requeue.

---

## Resolution Steps

### Option A — Requeue the stuck job (worker is healthy)

Use this when the worker is alive and the crash was a one-off.

```sql
-- requeue
UPDATE jobs
SET status = 'pending', updated_at = NOW()
WHERE status = 'processing'
AND updated_at < NOW() - INTERVAL '5 minutes';
```

Then push the job IDs back onto the Redis queue:

```bash
# get the stuck job IDs first
psql -U sre -d jobs -c "
SELECT id FROM jobs
WHERE status = 'pending'
AND updated_at > NOW() - INTERVAL '1 minute';"

# push each ID back to Redis
redis-cli RPUSH job_queue <job_id>
```

### Option B — Mark jobs as failed (bad payload or repeated crash)

Use this when the job payload is malformed or the job has been requeued
and crashed again.

```sql
UPDATE jobs
SET status = 'failed',
    error = 'manually failed — worker crash, payload suspected bad',
    updated_at = NOW()
WHERE status = 'processing'
AND updated_at < NOW() - INTERVAL '5 minutes';
```

### Option C — Restart the worker (worker is down)

```bash
# if running as a systemd service
sudo systemctl restart worker

# if running manually
python worker.py

# if running in Kubernetes
kubectl rollout restart deployment/job-worker -n <namespace>
```

---

## Confirm Resolution

1. Check Grafana — **Stuck Jobs** panel should return to `0`
2. Check Grafana — **Job Failure Rate** should not spike after requeue
3. Check queue depth — requeued jobs should be processing normally

```bash
curl http://localhost:8080/queue/depth
```

---

## Escalate if:

- Jobs keep getting stuck after requeue — payload may be consistently bad
- Worker keeps crashing within minutes of restart — memory or dependency issue
- More than 50 jobs are stuck — potential data integrity issue, wake up senior engineer
- Database queries above are timing out — Postgres may be down or overloaded

---

## Related Alerts

- `WorkerTargetDown` — worker process is completely unreachable
- `WorkerNotProcessing` — worker is running but not completing jobs
- `QueueDepthTooHigh` — jobs are piling up faster than workers can process

---

## Post-Incident

After resolving, file a postmortem if:

- More than 10 jobs were affected
- The incident lasted more than 30 minutes
- The root cause was not immediately obvious

Update this runbook with any new steps discovered during the incident.
