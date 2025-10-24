from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
from enum import Enum
import uuid
from datetime import datetime
import os
from celery import Celery

app = FastAPI(
    title="CrediSource API",
    description="Verify content authenticity with AI-powered detection",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Celery connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery('credisource', broker=REDIS_URL, backend=REDIS_URL)

# Models
class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"

class VerificationRequest(BaseModel):
    url: Optional[HttpUrl] = None
    content_type: ContentType
    platform: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: Optional[int] = None
    result: Optional[Dict] = None

@app.get("/")
async def root():
    return {
        "service": "CrediSource API",
        "version": "0.1.0",
        "status": "operational"
    }

@app.get("/health")
async def health():
    return {
        "api": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/verify/url", response_model=JobStatus)
async def verify_url(request: VerificationRequest):
    """Verify content from URL"""
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    job_id = str(uuid.uuid4())
    
    # Send job to Celery worker
    celery_app.send_task(
        'credisource.verify_content',
        args=[job_id, str(request.url), request.content_type.value],
        task_id=job_id
    )
    
    return JobStatus(
        job_id=job_id,
        status="pending",
        progress=0
    )

@app.post("/verify/upload", response_model=JobStatus)
async def verify_upload(
    file: UploadFile = File(...),
    content_type: ContentType = ContentType.IMAGE
):
    """Verify uploaded file"""
    job_id = str(uuid.uuid4())
    
    # Send job to worker
    celery_app.send_task(
        'credisource.verify_content',
        args=[job_id, file.filename, content_type.value],
        task_id=job_id
    )
    
    return JobStatus(
        job_id=job_id,
        status="pending",
        progress=0
    )

@app.get("/job/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get job status"""
    # Get result from Celery
    result = celery_app.AsyncResult(job_id)
    
    if result.state == 'PENDING':
        return JobStatus(job_id=job_id, status="pending", progress=0)
    elif result.state == 'STARTED':
        return JobStatus(job_id=job_id, status="processing", progress=50)
    elif result.state == 'SUCCESS':
        return JobStatus(
            job_id=job_id,
            status="completed",
            progress=100,
            result=result.result
        )
    elif result.state == 'FAILURE':
        return JobStatus(
            job_id=job_id,
            status="failed",
            progress=0,
            result={"error": str(result.info)}
        )
    else:
        return JobStatus(job_id=job_id, status=result.state.lower(), progress=0)

@app.get("/stats")
async def get_stats():
    """Get platform statistics"""
    return {
        "status": "operational",
        "worker_connected": True
    }
