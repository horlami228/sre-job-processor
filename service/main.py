from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import uuid

from database import engine, get_db, Base
from redis_client import get_redis, redis_client
from models import Job, JobStatus
from config import settings
from prometheus_fastapi_instrumentator import Instrumentator
from metrics import JOBS_SUBMITTED, QUEUE_DEPTH, JOBS_STUCK

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup on shutdown
    await redis_client.aclose()
    await engine.dispose()

app = FastAPI(title="Job Processor", lifespan=lifespan)

# Auto-instruments all routes with request duration, status codes etc
# exposes /metrics endpoint for Prometheus to scrape
Instrumentator().instrument(app).expose(app)
# --- Schemas ---

class JobSubmit(BaseModel):
    payload: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    status: str
    payload: Optional[str]
    result: Optional[str]
    error: Optional[str]

    class Config:
        from_attributes = True

# --- Routes ---

@app.post("/jobs", response_model=JobResponse, status_code=201)
async def submit_job(
    body: JobSubmit,    
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    job = Job(id=str(uuid.uuid4()), payload=body.payload)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Push job ID onto the Redis queue — worker will pick it up
    await redis.rpush(settings.JOB_QUEUE_KEY, job.id)

      # Track job submission
    JOBS_SUBMITTED.inc()
    QUEUE_DEPTH.inc()
 
    return job


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/jobs")
async def list_jobs(status: str = None, db: AsyncSession = Depends(get_db)):
    query = select(Job)
    if status:
        query = query.where(Job.status == status)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return jobs


@app.get("/queue/depth")
async def queue_depth(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Two signals SREs care about:
    - redis_depth: jobs not yet picked up by a worker
    - db_pending: jobs the DB thinks are still pending (should stay close to redis_depth)
    A growing gap between these two = workers are crashing mid-job.
    """
    redis_depth = await redis.llen(settings.JOB_QUEUE_KEY)

    db_result = await db.execute(
        select(func.count()).where(Job.status == JobStatus.pending)
    )
    db_pending = db_result.scalar()

    db_processing = await db.execute(
        select(func.count()).where(Job.status == JobStatus.processing)
    )

    processing_count = db_processing.scalar()

    QUEUE_DEPTH.set(redis_depth)
    JOBS_STUCK.set(processing_count)
    print(processing_count)

    return {
        "redis_queue_depth": redis_depth,
        "db_pending": db_pending,
        "db_processing": processing_count,
    }


@app.get("/health")
async def health(redis=Depends(get_redis)):
    """Checks both Postgres (via pool) and Redis connectivity."""
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": "ok" if redis_ok else "unreachable",
    }