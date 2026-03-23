# sre-job-processor

A production-grade job processing service built as a hands-on SRE learning platform. Designed to simulate realistic production failure scenarios and practice the full SRE lifecycle — from instrumentation to incident response.

---

## Architecture

```
                        ┌─────────────────┐
                        │   Client/curl   │
                        └────────┬────────┘
                                 │ HTTP
                                 ▼
                        ┌─────────────────┐
                        │   FastAPI App   │ :8000
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
           ┌─────────────────┐      ┌─────────────────┐
           │    PostgreSQL    │      │      Redis       │
           │  (job state)    │      │  (job queue)    │
           └─────────────────┘      └────────┬────────┘
                    ▲                         │ BLPOP
                    │                         ▼
                    │               ┌─────────────────┐
                    └───────────────│     Worker      │
                                    │  (job processor)│
                                    └─────────────────┘

                    ┌─────────────────────────────────┐
                    │         Observability           │
                    │                                 │
                    │  Prometheus ──► Alertmanager    │
                    │      │              │           │
                    │      ▼              ▼           │
                    │   Grafana         Slack         │
                    └─────────────────────────────────┘
```

**Flow:**

1. Client submits a job via `POST /jobs`
2. App writes job to Postgres (`status: pending`) and pushes job ID to Redis
3. Worker picks up job ID via `BLPOP` from Redis
4. Worker marks job `processing` in Postgres, does work, marks `done` or `failed`
5. Prometheus scrapes metrics from both app and worker
6. Alerts fire to Alertmanager which routes to Slack

---

## Stack

| Component     | Technology        | Why                                     |
| ------------- | ----------------- | --------------------------------------- |
| API           | FastAPI + asyncpg | Async, production-grade Python          |
| Queue         | Redis (BLPOP)     | Efficient blocking queue, no polling    |
| Database      | PostgreSQL        | Source of truth for job state           |
| Worker        | Python asyncio    | Background job processor                |
| Metrics       | Prometheus        | Industry standard for SRE observability |
| Dashboards    | Grafana           | Real-time operational visibility        |
| Alerting      | Alertmanager      | Alert routing and deduplication         |
| Notifications | Slack             | Alert delivery                          |
| Containers    | Docker + Compose  | Local development                       |
| Orchestration | Kubernetes (Kind) | Production deployment                   |

---

## Project Structure

```
sre-job-processor/
├── service/
│   ├── main.py           # FastAPI app + endpoints
│   ├── worker.py         # Background job processor
│   ├── database.py       # Postgres connection pool
│   ├── models.py         # Job model + status enum
│   ├── metrics.py        # Prometheus metrics definitions
│   ├── redis_client.py   # Redis client singleton
│   ├── config.py         # Pydantic settings
│   └── requirements.txt
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── postgres/
│   ├── redis/
│   ├── app/
│   ├── worker/
│   ├── prometheus/
│   ├── alertmanager/
│   └── grafana/
├── prometheus/
│   ├── prometheus.yaml
│   ├── alerting_rules.yaml
│   └── alertManager.yaml
├── runbooks/
│   ├── stuckJobs.md
│   ├── highFailureRate.md
│   ├── queueDepthTooHigh.md
│   ├── workerTargetDown.md
│   └── highProcessingTime.md
├── Dockerfile
├── docker-compose.yml
└── .gitignore
```

---

## Local Development

**Prerequisites:**

- Python 3.12+
- uv
- Docker + Docker Compose
- PostgreSQL
- Redis

**Setup:**

```bash
git clone https://github.com/horlami228/sre-job-processor
cd sre-job-processor

# create virtual environment
uv venv
source .venv/bin/activate

# install dependencies
uv pip install -r service/requirements.txt
```

**Run locally:**

```bash
# terminal 1 — start the API
uvicorn main:app --reload --port 8000

# terminal 2 — start the worker
python service/worker.py

# terminal 3 — start Prometheus
prometheus --config.file=prometheus/prometheus.yaml

# terminal 4 — start Alertmanager
alertmanager --config.file=prometheus/alertManager.yaml
```

---

## Docker

Run the entire stack with one command:

```bash
docker compose up
```

This starts:

- FastAPI app on port 8000
- Worker
- PostgreSQL on port 5432
- Redis on port 6379
- Prometheus on port 9090
- Alertmanager on port 9093
- Grafana on port 3000

**Test it:**

```bash
# submit a job
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": "test"}' | jq .

# check queue depth
curl http://localhost:8000/queue/depth

# check health
curl http://localhost:8000/health
```

---

## Kubernetes

**Prerequisites:**

- kubectl
- Kind cluster

**Deploy:**

```bash
# create namespace
kubectl apply -f k8s/namespace.yaml

# create config and secrets
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# deploy infrastructure
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/redis/

# deploy application
kubectl apply -f k8s/app/
kubectl apply -f k8s/worker/

# deploy observability
kubectl apply -f k8s/prometheus/
kubectl apply -f k8s/alertmanager/
kubectl apply -f k8s/grafana/
```

**Access services:**

```bash
# API — via NodePort
curl http://localhost:30001/jobs

# Prometheus
kubectl port-forward svc/prometheus 9090:9090

# Grafana
kubectl port-forward svc/grafana 3000:3000

# Alertmanager
kubectl port-forward svc/alertmanager 9093:9093
```

**Verify everything is running:**

```bash
kubectl get pods -n sre-job-processor
kubectl get svc -n sre-job-processor
kubectl get pvc -n sre-job-processor
```

---

## API Endpoints

| Method | Endpoint              | Description          |
| ------ | --------------------- | -------------------- |
| `POST` | `/jobs`               | Submit a new job     |
| `GET`  | `/jobs/{id}`          | Get job status       |
| `GET`  | `/jobs?status=failed` | List jobs by status  |
| `GET`  | `/queue/depth`        | Current queue depth  |
| `GET`  | `/health`             | Service health check |
| `GET`  | `/metrics`            | Prometheus metrics   |

---

## Observability

### Metrics

| Metric                            | Type      | Description                    |
| --------------------------------- | --------- | ------------------------------ |
| `jobs_submitted_total`            | Counter   | Total jobs submitted           |
| `jobs_completed_total{status}`    | Counter   | Jobs completed by status       |
| `job_processing_duration_seconds` | Histogram | Job processing duration        |
| `job_queue_depth`                 | Gauge     | Current Redis queue depth      |
| `jobs_stuck_processing`           | Gauge     | Jobs stuck in processing state |

### Alerts

| Alert                              | Severity | Condition                        |
| ---------------------------------- | -------- | -------------------------------- |
| `StuckJobsDetected`                | Critical | Jobs stuck in processing > 1 min |
| `WorkerTargetDown`                 | Critical | Worker unreachable > 1 min       |
| `HighJobFailureRate`               | Warning  | Failure rate > 20% for 5 mins    |
| `QueueDepthTooHigh`                | Warning  | Queue depth > 100 for 5 mins     |
| `HighProcessingTime95thPercentile` | Warning  | p95 > threshold for 5 mins       |
| `HighProcessingTime99thPercentile` | Warning  | p99 > threshold for 5 mins       |

### Dashboards

Grafana dashboard covers:

- Queue depth (real-time)
- Job failure rate
- Processing time p95 vs p99
- Stuck jobs
- Worker target status

---

## Runbooks

Every alert has a corresponding runbook with diagnosis steps, resolution options and escalation criteria:

| Alert              | Runbook                                                 |
| ------------------ | ------------------------------------------------------- |
| StuckJobsDetected  | [stuckJobs.md](runbooks/stuckJobs.md)                   |
| HighJobFailureRate | [highFailureRate.md](runbooks/highFailureRate.md)       |
| QueueDepthTooHigh  | [queueDepthTooHigh.md](runbooks/queueDepthTooHigh.md)   |
| WorkerTargetDown   | [workerTargetDown.md](runbooks/workerTargetDown.md)     |
| HighProcessingTime | [highProcessingTime.md](runbooks/highProcessingTime.md) |

---

## Failure Scenarios

Intentional failure modes built into the service for SRE practice:

**Stuck jobs** — worker crashes after marking job as `processing`, job is orphaned in Postgres

```python
# uncomment in worker.py
raise Exception("worker crashed")
```

**Random failures** — 30% of jobs fail with a simulated error

```python
# uncomment in worker.py
if random.random() < 0.3:
    raise ValueError("Simulated processing failure")
```

**Queue depth spike** — scale worker to 0 while submitting jobs

```bash
kubectl scale deployment worker --replicas=0
for i in {1..200}; do curl -s -X POST http://localhost:30001/jobs \
  -H "Content-Type: application/json" \
  -d "{\"payload\": \"job $i\"}" > /dev/null; done
```

---

## Roadmap

- [ ] Horizontal Pod Autoscaler — auto scale workers based on queue depth
- [ ] Liveness and readiness probes
- [ ] Resource limits on all pods
- [ ] Ingress controller
- [ ] CI/CD pipeline — auto deploy on push to main
- [ ] Terraform — provision infrastructure as code
- [ ] Distributed tracing with Tempo
- [ ] Log aggregation with Loki
- [ ] Chaos engineering scenarios
- [ ] SLOs and error budgets
