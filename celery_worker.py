from celery import Celery
import os
import httpx
import asyncio

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

# API Keys from environment
HIVE_API_KEY = os.getenv("HIVE_API_KEY")
SAPLING_API_KEY = os.getenv("SAPLING_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")

@app.task(name='credisource.test_task')
def test_task():
    return {"status": "Worker is running!"}

@app.task(name='credisource.verify_content')
def verify_content_task(job_id, url, content_type):
    """Process verification job with REAL AI detection"""
    
    print(f"🔍 Processing job {job_id} for {url} (type: {content_type})")
    
    try:
        # Run detection based on content type
        if content_type in ['image', 'video']:
            result = detect_image_video(url)
        elif content_type == 'text':
            result = detect_text(url)
        else:
            result = {"error": "Unsupported content type"}
        
        print(f"✅ Completed job {job_id}: Score {result.get('trust_score', {}).get('score', 'N/A')}")
        return result
        
    except Exception as e:
        print(f"❌ Error in job {job_id}: {str(e)}")
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e)
        }

def detect_image_video(url):
    """Detect AI in images/videos using Hive AI"""
    
    if not HIVE_API_KEY:
        return create_mock_result(75, "No Hive API key configured")
    
    try:
        # Call Hive AI API
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.thehive.ai/api/v2/task/sync",
                headers={
                    "Authorization": f"Token {HIVE_API_KEY}",
                    "Accept": "application/json"
                },
                files={"media": ("image.jpg", httpx.get(url).content)}
            )
            
            if response.status_code != 200:
                print(f"⚠️ Hive API error: {response.status_code}")
                return create_mock_result(50, f"API Error: {response.status_code}")
            
            data = response.json()
            
            # Extract AI probability from Hive response
            ai_score = extract_hive_score(data)
            
            # Calculate trust score (inverse of AI probability)
            trust_score = int((1 - ai_score) * 100)
            
            # Determine label
            label = get_label(trust_score)
            
            return {
                "trust_score": {
                    "score": trust_score,
                    "label": label,
                    "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
                },
                "evidence": [
                    {
                        "category": "AI Detection",
                        "signal": f"{int(ai_score * 100)}% AI probability detected (Hive AI)",
                        "confidence": 0.85,
                        "details": {"provider": "hive", "raw_score": ai_score}
                    }
                ],
                "metadata": {
                    "url": url,
                    "provider": "Hive AI",
                    "content_type": "image/video"
                }
            }
            
    except Exception as e:
        print(f"⚠️ Hive detection error: {str(e)}")
        return create_mock_result(50, f"Detection error: {str(e)}")

def detect_text(text_content):
    """Detect AI in text using Sapling AI"""
    
    if not SAPLING_API_KEY:
        return create_mock_result(70, "No Sapling API key configured")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.sapling.ai/api/v1/aidetect",
                json={
                    "key": SAPLING_API_KEY,
                    "text": text_content
                }
            )
            
            if response.status_code != 200:
                print(f"⚠️ Sapling API error: {response.status_code}")
                return create_mock_result(50, f"API Error: {response.status_code}")
            
            data = response.json()
            ai_score = data.get("score", 0.5)
            
            # Calculate trust score
            trust_score = int((1 - ai_score) * 100)
            label = get_label(trust_score)
            
            return {
                "trust_score": {
                    "score": trust_score,
                    "label": label,
                    "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
                },
                "evidence": [
                    {
                        "category": "AI Text Detection",
                        "signal": f"{int(ai_score * 100)}% AI probability (Sapling AI)",
                        "confidence": 0.83,
                        "details": {"provider": "sapling", "raw_score": ai_score}
                    }
                ],
                "metadata": {
                    "provider": "Sapling AI",
                    "content_type": "text"
                }
            }
            
    except Exception as e:
        print(f"⚠️ Sapling detection error: {str(e)}")
        return create_mock_result(50, f"Detection error: {str(e)}")

def extract_hive_score(hive_response):
    """Extract AI probability from Hive API response"""
    try:
        classes = hive_response.get('status', [{}])[0].get('response', {}).get('output', [{}])[0].get('classes', [])
        
        # Look for AI-generated class
        for cls in classes:
            if 'ai_generated' in cls.get('class', '').lower() or 'generated' in cls.get('class', '').lower():
                return cls.get('score', 0.5)
        
        # Default if not found
        return 0.5
        
    except Exception as e:
        print(f"⚠️ Error parsing Hive response: {e}")
        return 0.5

def get_label(score):
    """Convert score to human-readable label"""
    if score >= 75:
        return "Likely Authentic"
    elif score >= 55:
        return "Leaning Authentic"
    elif score >= 45:
        return "Inconclusive"
    else:
        return "Likely AI"

def create_mock_result(score, reason):
    """Create mock result when API unavailable"""
    return {
        "trust_score": {
            "score": score,
            "label": get_label(score),
            "confidence_band": [max(0, score - 10), min(100, score + 10)]
        },
        "evidence": [
            {
                "category": "System",
                "signal": reason,
                "confidence": 0.5
            }
        ],
        "metadata": {
            "note": "Mock result - check API keys"
        }
    }
