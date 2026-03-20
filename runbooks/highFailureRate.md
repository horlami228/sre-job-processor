# Runbook: HighJobFailureRate

## Alert Details

- **Severity:** Warning
- **Alert name:** HighJobFailureRate
- **Fires when:** More than 20% of jobs are failing over a 5 minute window

## What is this?

A significant percentage of jobs are completing with a `failed` status.
Unlike stuck jobs, these jobs did finish — just badly. The worker caught
an exception and marked them failed. Something in the processing logic
or a downstream dependency is broken.

## Impact

- Jobs are not producing results
- Upstream systems receiving failed job responses
- If failure rate reaches 100%, the service is effectively down

---

## Diagnosis Steps

### Step 1 — Check current failure rate

```bash
curl http://localhost:8080/jobs?status=failed | python3 -m json.tool | head -50
```

Or in Prometheus:

```
rate(jobs_completed_total{status="failed"}[5m])
/
rate(jobs_completed_total[5m])
```

### Step 2 — Check when failures started

Look at the **Job Failure Rate** panel in Grafana.

- Did it spike suddenly? → likely a deployment or dependency change
- Has it been gradually rising? → likely a resource or load issue

### Step 3 — Check the error messages on failed jobs

```sql
SELECT error, COUNT(*) as count
FROM jobs
WHERE status = 'failed'
AND updated_at > NOW() - INTERVAL '30 minutes'
GROUP BY error
ORDER BY count DESC;
```

Are all jobs failing with the same error? That points to a specific root cause.

### Step 4 — Check worker logs

```bash
journalctl -u worker -n 200 --no-pager | grep ERROR
```

Look for:

- Database connection errors → Postgres may be struggling
- Timeout errors → a downstream service is slow
- Memory errors → worker is running out of memory
- Specific exception types that match the SQL error messages

### Step 5 — Check if a recent deployment happened

```bash
git log --oneline -10
```

Did a code change go out around the time failures started?
If yes — consider rolling back.

### Step 6 — Check Postgres health

```sql
-- are there slow queries?
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- are connections healthy?
SELECT count(*), state
FROM pg_stat_activity
GROUP BY state;
```

---

## Resolution Steps

### Option A — Code bug introduced by deployment

```bash
# roll back to previous version
git revert HEAD
# restart the worker
sudo systemctl restart worker
```

### Option B — Downstream dependency is down

Identify which dependency is failing from the error messages.

- Redis down → restart Redis, check `redis-cli ping`
- Postgres down → check `pg_isready -h localhost -p 5432`
- External API down → check the API status page, implement retry logic

### Option C — Worker overloaded

If the worker is processing too many jobs simultaneously:

- Reduce concurrency if running multiple workers
- Scale down job submission rate
- Add more worker instances

### Option D — Bad payload causing failures

```sql
-- find what payloads are consistently failing
SELECT payload, error, COUNT(*)
FROM jobs
WHERE status = 'failed'
AND updated_at > NOW() - INTERVAL '30 minutes'
GROUP BY payload, error
ORDER BY COUNT(*) DESC;
```

If specific payloads keep failing — fix the upstream system sending bad data.

---

## Confirm Resolution

1. Grafana — **Job Failure Rate** drops below 20%
2. Prometheus query returns expected value:

```
rate(jobs_completed_total{status="failed"}[5m])
/
rate(jobs_completed_total[5m])
```

3. Submit a test job and confirm it completes successfully:

```bash
curl -s -X POST http://localhost:8080/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": "runbook-test"}' | jq .status
```

---

## Escalate if:

- Failure rate is 100% and cause is not obvious
- Failures persist after worker restart
- Database queries are timing out or returning errors
- The issue started without any deployment or config change

---

## Related Alerts

- `StuckJobsDetected` — worker crashing mid-job
- `WorkerNotProcessing` — worker completely stopped
- `QueueDepthTooHigh` — jobs piling up as a result of failures

---

## Post-Incident

File a postmortem if:

- Failure rate exceeded 50% for more than 10 minutes
- More than 100 jobs failed
- Root cause was a deployment — add to deployment checklist
