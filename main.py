from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from celery.result import AsyncResult
import uuid
import os
from celery import Celery
import httpx
from typing import Optional
import base64

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
    content_type: str  # 'image', 'video', 'text', 'news'

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
            "verify_image": "POST /verify/image",
            "verify_video": "POST /verify/video",
            "verify_news": "POST /verify/news",
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

# Image Verification Endpoint
@app.post("/verify/image", response_model=JobResponse)
async def verify_image(request: VerifyURLRequest):
    """
    Verify image from URL (convenience endpoint)
    Accepts URL and automatically sets content_type to 'image'
    """
    request.content_type = "image"
    return await verify_url(request)

# Video Verification Endpoint
@app.post("/verify/video", response_model=JobResponse)
async def verify_video(request: VerifyURLRequest):
    """
    Verify video from URL (convenience endpoint)
    Accepts URL and automatically sets content_type to 'video'
    """
    request.content_type = "video"
    return await verify_url(request)

# News Verification Endpoint
@app.post("/verify/news", response_model=JobResponse)
async def verify_news(request: VerifyURLRequest):
    """
    Verify news article from URL (convenience endpoint)
    Checks source credibility + content authenticity + cross-reference
    """
    request.content_type = "news"
    return await verify_url(request)

# Text Verification Endpoint
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

# File Upload Endpoint - COMPLETELY REWRITTEN TO AVOID ENCODING ERRORS
@app.post("/verify/file")
async def verify_file(request: Request):
    """
    Upload a file for content verification
    Uses manual form parsing to avoid FastAPI's encoding issues
    """
    try:
        # Parse form data manually
        form = await request.form()
        
        # Get file from form
        file = form.get("file")
        if not file:
            return JSONResponse(
                status_code=400,
                content={"job_id": "", "status": "error", "message": "No file provided"}
            )
        
        # Get content type (default to image)
        content_type = form.get("content_type", "image")
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Read file content
        file_content = await file.read()
        
        # Validate file has content
        if not file_content or len(file_content) == 0:
            return JSONResponse(
                status_code=400,
                content={"job_id": job_id, "status": "error", "message": "Empty file uploaded"}
            )
        
        # Handle text files
        if content_type == "text":
            try:
                text_content = file_content.decode('utf-8')
                
                if len(text_content) < 50:
                    return JSONResponse(
                        status_code=400,
                        content={"job_id": job_id, "status": "error", "message": "Text too short (minimum 50 characters)"}
                    )
                
                # Queue text verification
                task = celery_app.send_task(
                    'credisource.verify_content',
                    args=[job_id, text_content, "text"],
                    task_id=job_id
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "job_id": job_id,
                        "status": "queued",
                        "message": f"Text verification queued. Check status at /job/{job_id}"
                    }
                )
            except UnicodeDecodeError:
                return JSONResponse(
                    status_code=400,
                    content={"job_id": job_id, "status": "error", "message": "Invalid text file encoding"}
                )
        
        # Handle images and videos - encode to base64 using ASCII
        file_base64 = base64.b64encode(file_content).decode('ascii')
        
        # Queue the job
        task = celery_app.send_task(
            'credisource.verify_content_file',
            args=[job_id, file_base64, file.filename, content_type],
            task_id=job_id
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "status": "queued",
                "message": f"File uploaded and verification queued. Check status at /job/{job_id}"
            }
        )
        
    except Exception as e:
        # Log error but return clean JSON response
        print(f"❌ File upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={
                "job_id": str(uuid.uuid4()),
                "status": "error",
                "message": f"Error processing file: {str(e)}"
            }
        )

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
