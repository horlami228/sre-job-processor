# Runbook: QueueDepthTooHigh

## Alert Details

- **Severity:** Warning
- **Alert name:** QueueDepthTooHigh
- **Fires when:** `job_queue_depth > 100` for more than 5 minutes

## What is this?

More than 100 jobs are sitting in the Redis queue waiting to be processed.
Workers are not keeping up with the rate of job submissions.
This could mean workers are too slow, there are not enough workers,
or workers have stopped entirely.

## Impact

- Jobs are delayed — users are waiting longer than expected
- If queue keeps growing, Redis memory will eventually be exhausted
- System latency increases across the board

---

## Diagnosis Steps

### Step 1 — Check current queue state

```bash
curl http://localhost:8080/queue/depth
```

Note all three values:

- `redis_queue_depth` — jobs waiting to be picked up
- `db_pending` — Postgres agrees these are pending
- `db_processing` — jobs currently being worked on

If `db_processing` is 0 and `redis_queue_depth` is high → workers are down.
If `db_processing` is high → workers are running but very slow.

### Step 2 — Check the rate of growth

In Prometheus:

```
deriv(job_queue_depth[5m])
```

A positive number means queue is growing. A negative number means it's draining.
How fast is it growing? Is it accelerating?

### Step 3 — Check if workers are running

```bash
curl http://localhost:8001/metrics | grep "^up"
```

- `up 1` → worker is running
- `up 0` → worker is down, go to Step 6

### Step 4 — Check job submission rate vs completion rate

In Prometheus:

```
rate(jobs_submitted_total[5m])
```

```
rate(jobs_completed_total[5m])
```

If submission rate >> completion rate → not enough workers or workers too slow.
If submission rate spiked suddenly → unexpected traffic surge.

### Step 5 — Check worker processing time

```
histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))
```

Has p95 increased significantly? If yes — jobs are taking longer than usual.
Look for slow database queries or external dependency slowness.

### Step 6 — Check worker logs

```bash
journalctl -u worker -n 100 --no-pager
```

---

## Resolution Steps

### Option A — Workers are down

```bash
sudo systemctl restart worker
# or
python worker.py
# or in Kubernetes
kubectl rollout restart deployment/job-worker
```

The queue will drain automatically once workers are back up.

### Option B — Not enough workers (traffic surge)

Scale up the number of worker instances:

```bash
# run a second worker in another terminal
python worker.py

# in Kubernetes — scale the deployment
kubectl scale deployment job-worker --replicas=3
```

### Option C — Workers are slow (processing time increased)

- Check Postgres for slow queries
- Check if an external dependency the worker uses has slowed down
- Check worker memory usage — if it's swapping, processing will be slow

### Option D — Submission rate spiked unexpectedly

- Identify the source of the spike — is it legitimate traffic or a bug?
- If a bug — fix the upstream system sending too many jobs
- If legitimate — scale workers immediately

---

## Confirm Resolution

1. Grafana — **Queue Depth** panel trending down toward 0
2. Verify queue is draining:

```bash
watch -n 5 curl -s http://localhost:8080/queue/depth
```

3. Confirm queue reaches 0 within a reasonable time

---

## Escalate if:

- Queue is growing faster than workers can drain it
- Workers are running but queue isn't draining
- Redis memory usage is above 80% — check with `redis-cli info memory`
- Queue depth exceeds 10,000 jobs

---

## Related Alerts

- `WorkerTargetDown` — workers are completely down
- `WorkerNotProcessing` — workers running but not completing jobs
- `StuckJobsDetected` — may be causing backup if many jobs are stuck

---

## Post-Incident

File a postmortem if:

- Queue exceeded 1000 jobs
- Users were impacted for more than 15 minutes
- Root cause was insufficient worker capacity — add autoscaling to action items
