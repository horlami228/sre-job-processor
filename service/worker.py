"""
Worker process — run this separately from the API:
    python worker.py

It blocks on Redis BLPOP, picks up job IDs, updates Postgres status,
simulates work, then marks jobs done or failed.

This is where you'll introduce failures for SRE practice.
"""
import asyncio
import logging
import random
import time

import redis.asyncio as aioredis
from sqlalchemy import select
from prometheus_client import start_http_server

from config import settings
from database import AsyncSessionLocal, engine, Base
from models import Job, JobStatus
from metrics import JOBS_COMPLETED, JOB_PROCESSING_DURATION, QUEUE_DEPTH
from prometheus_client import start_http_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def process_job(job_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            log.warning(f"Job {job_id} not found in DB — skipping")
            return

        # Mark as processing
        job.status = JobStatus.processing
        await db.commit()

        raise Exception("worker crashed") # for crashing simulation

        log.info(f"Processing job {job_id} | payload={job.payload}")

        start_time = time.time()
        try:
            # Simulate work — replace this with real logic later
            await asyncio.sleep(random.uniform(0.5, 2.0))

            # Uncomment to simulate random failures (good for SRE practice):
            # if random.random() < 0.3:
            #     raise ValueError("Simulated processing failure")

            job.status = JobStatus.done
            job.result = f"Processed: {job.payload}"
            log.info(f"Job {job_id} completed")

            JOBS_COMPLETED.labels(status="done").inc()

        except Exception as e:
            job.status = JobStatus.failed
            job.error = str(e)
            log.error(f"Job {job_id} failed: {e}")

            JOBS_COMPLETED.labels(status="failed").inc()
        
        finally:
            # Always record duration and update queue gauge regardless of outcome
            duration = time.time() - start_time
            JOB_PROCESSING_DURATION.observe(duration)

        await db.commit()


async def main():
    # Ensure tables exist (useful if worker starts before API)
    start_http_server(8001)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    redis = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    log.info("Worker started — waiting for jobs...")

    while True:
        # BLPOP blocks until a job arrives (timeout=5 to allow clean shutdown)
        item = await redis.blpop(settings.JOB_QUEUE_KEY, timeout=5)
        if item is None:
            continue  # timeout, loop again

        _, job_id = item
        await process_job(job_id)


if __name__ == "__main__":
    asyncio.run(main())