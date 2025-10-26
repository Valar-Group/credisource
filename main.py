from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from celery.result import AsyncResult
import uuid
import os
from celery import Celery
import httpx
from typing import Optional

app = FastAPI(
    title="CrediSource API",
    description="AI Content Verification API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery('credisource', broker=REDIS_URL, backend=REDIS_URL)

# Models
class VerifyURLRequest(BaseModel):
    url: str
    content_type: str  # 'image', 'video', 'text'

class VerifyTextRequest(BaseModel):
    text: str

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

# Health check
@app.get("/")
def read_root():
    return {
        "service": "CrediSource API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "verify_url": "POST /verify/url",
            "verify_file": "POST /verify/file",
            "verify_text": "POST /verify/text",
            "job_status": "GET /job/{job_id}",
            "health": "GET /health"
        }
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# URL Verification Endpoint
@app.post("/verify/url", response_model=JobResponse)
async def verify_url(request: VerifyURLRequest):
    """
    Submit a URL for content verification
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Queue the job
    task = celery_app.send_task(
        'credisource.verify_content',
        args=[job_id, request.url, request.content_type],
        task_id=job_id
    )
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Verification job queued. Check status at /job/{job_id}"
    }

# Text Verification Endpoint (for pasted text)
@app.post("/verify/text", response_model=JobResponse)
async def verify_text(request: VerifyTextRequest):
    """
    Submit text content for AI detection
    Perfect for articles, essays, social media posts, etc.
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Validate text length
    if len(request.text) < 50:
        raise HTTPException(
            status_code=400,
            detail="Text too short. Please provide at least 50 characters for accurate detection."
        )
    
    if len(request.text) > 50000:
        raise HTTPException(
            status_code=400,
            detail="Text too long. Maximum 50,000 characters."
        )
    
    # Queue the job
    task = celery_app.send_task(
        'credisource.verify_content',
        args=[job_id, request.text, 'text'],
        task_id=job_id
    )
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Text verification queued. Check status at /job/{job_id}"
    }

# NEW: File Upload Endpoint
@app.post("/verify/file", response_model=JobResponse)
async def verify_file(
    file: UploadFile = File(...),
    content_type: str = "image"
):
    """
    Upload a file for content verification
    Supports: 
    - Images (jpg, png, webp, gif, bmp)
    - Videos (mp4, mov, avi, webm)
    - Text (txt, text files or pasted text)
    """
    # Validate file type based on content_type
    if content_type == "image":
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif", "image/bmp", "image/heif", "image/avif"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image file type. Allowed: JPG, PNG, WEBP, GIF, BMP, HEIF, AVIF"
            )
    elif content_type == "video":
        allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid video file type. Allowed: MP4, MOV, AVI, WEBM, MKV"
            )
    elif content_type == "text":
        # Text can be uploaded as .txt file or pasted directly
        allowed_types = ["text/plain", "application/octet-stream"]
        # Allow any content type for text since it's flexible
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    try:
        # Read file content
        file_content = await file.read()
        
        # For text files, we can process directly
        if content_type == "text":
            try:
                # Try to decode as text
                text_content = file_content.decode('utf-8')
                
                # Queue text verification task directly
                task = celery_app.send_task(
                    'credisource.verify_content',
                    args=[job_id, text_content, "text"],
                    task_id=job_id
                )
                
                return {
                    "job_id": job_id,
                    "status": "queued",
                    "message": f"Text verification queued. Check status at /job/{job_id}"
                }
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Invalid text file encoding. Please use UTF-8.")
        
        # For images and videos, convert to base64
        import base64
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # Queue the job with file data
        task = celery_app.send_task(
            'credisource.verify_content_file',
            args=[job_id, file_base64, file.filename, content_type],
            task_id=job_id
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": f"File uploaded and verification queued. Check status at /job/{job_id}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# Job Status Endpoint
@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Check the status of a verification job
    """
    result = AsyncResult(job_id, app=celery_app)
    
    if result.state == 'PENDING':
        return {
            "job_id": job_id,
            "status": "pending",
            "progress": 0
        }
    elif result.state == 'STARTED':
        return {
            "job_id": job_id,
            "status": "processing",
            "progress": 50
        }
    elif result.state == 'SUCCESS':
        return {
            "job_id": job_id,
            "status": "completed",
            "progress": 100,
            "result": result.result
        }
    elif result.state == 'FAILURE':
        return {
            "job_id": job_id,
            "status": "failed",
            "progress": 0,
            "error": str(result.info)
        }
    else:
        return {
            "job_id": job_id,
            "status": result.state.lower(),
            "progress": 25
        }

# Test endpoint to check worker
@app.get("/test-worker")
async def test_worker():
    """Test if Celery worker is connected"""
    try:
        task = celery_app.send_task('credisource.test_task')
        result = task.get(timeout=5)
        return {"status": "success", "worker_response": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
