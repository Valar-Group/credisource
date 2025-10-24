from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    'credisource',
    broker=REDIS_URL,
    backend=REDIS_URL
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@app.task(name='credisource.test_task')
def test_task():
    return {"status": "Worker is running!"}

@app.task(name='credisource.verify_content')
def verify_content_task(job_id, url, content_type):
    """Process verification job"""
    print(f"Processing job {job_id} for {url}")
    
    # TODO: Add actual detection logic here
    # For now, return a mock result
    
    return {
        "job_id": job_id,
        "trust_score": {
            "score": 75,
            "label": "Test Result"
        },
        "status": "completed"
    }
