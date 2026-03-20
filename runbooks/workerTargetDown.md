# Runbook: WorkerNotProcessing / WorkerTargetDown

## Alert Details

### WorkerTargetDown

- **Severity:** Critical
- **Fires when:** `up{job="job-worker"} == 0` for more than 1 minute
- **Meaning:** Prometheus cannot reach the worker metrics endpoint — process is likely dead

### WorkerNotProcessing

- **Severity:** Critical
- **Fires when:** Jobs are being submitted but none are completing for more than 3 minutes
- **Meaning:** Worker process may be running but silently doing nothing

## What is this?

The worker that processes jobs from the Redis queue has either stopped completely
or has entered a broken state where it's running but not doing any work.
All submitted jobs will pile up in the queue indefinitely.

## Impact

- All jobs are blocked — nothing is being processed
- Queue depth will grow until Redis runs out of memory
- Complete service degradation for any system depending on job results

---

## Diagnosis Steps

### Step 1 — Check if the worker process is running at all

```bash
# check if the process exists
ps aux | grep worker.py

# check metrics endpoint directly
curl http://localhost:8001/metrics
```

- Gets a response → worker is running, go to Step 3
- Connection refused → worker process is dead, go to Step 5

### Step 2 — Check Prometheus target status

Go to Prometheus UI → Status → Targets
Look at `job-worker` target — is it UP or DOWN?
Note the last scrape time and any error message shown.

### Step 3 — Check worker logs for silent failures

```bash
journalctl -u worker -n 200 --no-pager
```

Look for:

- Is the BLPOP loop running? You should see "Worker started — waiting for jobs..."
- Are there repeated connection errors to Redis or Postgres?
- Is the worker stuck in an infinite error loop?

### Step 4 — Check Redis connectivity from the worker

```bash
redis-cli ping
# Expected: PONG
redis-cli llen job_queue
# Shows how many jobs are waiting
```

### Step 5 — Check Postgres connectivity

```bash
pg_isready -h localhost -p 5432 -U sre -d jobs
# Expected: localhost:5432 - accepting connections
```

### Step 6 — Check system resources

```bash
# memory
free -h

# disk
df -h

# cpu
top
```

A worker killed by OOM (out of memory) will restart but may keep getting killed.

---

## Resolution Steps

### Option A — Worker process is dead, restart it

```bash
# if running manually
python worker.py

# if running as systemd service
sudo systemctl restart worker
sudo systemctl status worker

# if running in Kubernetes
kubectl rollout restart deployment/job-worker
kubectl get pods -l app=job-worker
```

### Option B — Worker is running but not connecting to Redis

```bash
# verify Redis is running
redis-cli ping

# if Redis is down, restart it
sudo systemctl restart redis
# or with Docker
docker compose restart redis
```

### Option C — Worker is running but not connecting to Postgres

```bash
# verify Postgres is running
pg_isready -h localhost -p 5432

# if Postgres is down
sudo systemctl restart postgresql
# or with Docker
docker compose restart postgres
```

### Option D — Worker keeps crashing (OOM)

```bash
# check how much memory the worker is using
ps aux | grep worker.py

# check system memory
free -h
```

If memory is exhausted:

- Kill any other processes consuming memory
- Reduce worker concurrency
- Add more memory to the server
- Escalate to senior engineer for permanent fix

---

## Confirm Resolution

1. Worker metrics endpoint responds:

```bash
curl http://localhost:8001/metrics | grep "^up"
# Expected: up 1
```

2. Prometheus target shows UP — check Status → Targets
3. Submit a test job and confirm it completes:

```bash
curl -s -X POST http://localhost:8080/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": "worker-recovery-test"}' | jq .id
# then check status
curl http://localhost:8080/jobs/<job_id> | jq .status
# Expected: "done"
```

4. Grafana — **Worker Target Down** panel shows green `1`
5. Grafana — **Queue Depth** trending down as backlog drains

---

## Escalate if:

- Worker keeps dying within minutes of restart
- Redis and Postgres are both healthy but worker won't connect
- System is out of memory and adding more is not possible
- Queue has grown beyond 10,000 jobs during the outage

---

## Related Alerts

- `QueueDepthTooHigh` — will fire shortly after this if worker stays down
- `StuckJobsDetected` — may fire if worker died mid-job before going down

---

## Post-Incident

File a postmortem if:

- Worker was down for more than 10 minutes
- More than 500 jobs were delayed
- Root cause was OOM — add memory limits and alerts to action items
- Root cause was unknown — add additional logging to worker startup
