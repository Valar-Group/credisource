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
AIORNOT_API_KEY = os.getenv("AIORNOT_API_KEY")
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
    """Detect AI in images using AI or Not (with polling)"""
    
    if not AIORNOT_API_KEY:
        return create_mock_result(75, "No AI or Not API key configured")
    
    try:
        print(f"🔍 Submitting image to AI or Not: {url}")
        
        # Step 1: Submit the image for analysis
        with httpx.Client(timeout=60.0) as client:
            submit_response = client.post(
                "https://api.aiornot.com/v1/reports/image",
                headers={
                    "Authorization": f"Bearer {AIORNOT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "object": url
                }
            )
            
            print(f"📡 Submit status: {submit_response.status_code}")
            print(f"📡 Submit response: {submit_response.text}")
            
            if submit_response.status_code not in [200, 201]:
                error_msg = f"AI or Not submit error {submit_response.status_code}: {submit_response.text}"
                print(f"⚠️ {error_msg}")
                return create_mock_result(50, error_msg)
            
            submit_data = submit_response.json()
            report_id = submit_data.get("id") or submit_data.get("report_id")
            
            if not report_id:
                print(f"⚠️ No report_id in response: {submit_data}")
                return create_mock_result(50, "No report_id returned")
            
            print(f"✅ Got report_id: {report_id}")
            
            # Step 2: Poll for the result
            import time
            max_attempts = 15
            for attempt in range(max_attempts):
                print(f"🔄 Polling attempt {attempt + 1}/{max_attempts}")
                
                time.sleep(2)
                
                result_response = client.get(
                    f"https://api.aiornot.com/v1/reports/{report_id}",
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"}
                )
                
                if result_response.status_code != 200:
                    print(f"⚠️ Poll error: {result_response.text}")
                    continue
                
                result_data = result_response.json()
                status = result_data.get("status")
                
                print(f"📊 Report status: {status}")
                
                if status == "done":
                    print(f"✅ Complete! Result: {result_data}")
                    
                    report = result_data.get("report", {})
                    verdict = report.get("verdict", "unknown")
                    confidence = report.get("confidence", 0.5)
                    
                    if verdict.lower() in ["human", "real"]:
                        trust_score = int(confidence * 100)
                    elif verdict.lower() in ["ai", "fake"]:
                        trust_score = int((1 - confidence) * 100)
                    else:
                        trust_score = 50
                    
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
                                "signal": f"Verdict: {verdict} ({int(confidence * 100)}% confidence)",
                                "confidence": confidence,
                                "details": {"provider": "aiornot", "verdict": verdict}
                            }
                        ],
                        "metadata": {
                            "url": url,
                            "provider": "AI or Not"
                        }
                    }
                
                elif status in ["failed", "error"]:
                    return create_mock_result(50, f"Analysis failed: {result_data}")
            
            return create_mock_result(50, "Timeout waiting for results")
            
    except Exception as e:
        print(f"⚠️ Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return create_mock_result(50, str(e))
                    
                    # Extract the verdict
                    report = result_data.get("report", {})
                    verdict = report.get("verdict", "unknown")
                    confidence = report.get("confidence", 0.5)
                    
                    # Calculate trust score
                    if verdict.lower() in ["human", "real"]:
                        trust_score = int(confidence * 100)
                    elif verdict.lower() in ["ai", "fake"]:
                        trust_score = int((1 - confidence) * 100)
                    else:
                        trust_score = 50
                    
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
                                "signal": f"Verdict: {verdict} ({int(confidence * 100)}% confidence) - AI or Not",
                                "confidence": confidence,
                                "details": {
                                    "provider": "aiornot",
                                    "verdict": verdict,
                                    "confidence": confidence,
                                    "report_id": report_id
                                }
                            }
                        ],
                        "metadata": {
                            "url": url,
                            "provider": "AI or Not",
                            "content_type": "image",
                            "report_id": report_id
                        }
                    }
                
                elif status in ["failed", "error"]:
                    error_msg = f"AI or Not analysis failed: {result_data.get('error', 'Unknown error')}"
                    print(f"❌ {error_msg}")
                    return create_mock_result(50, error_msg)
            
            # If we get here, polling timed out
            return create_mock_result(50, "AI or Not analysis timed out after 30 seconds")
            
    except Exception as e:
        error_msg = f"AI or Not detection error: {str(e)}"
        print(f"⚠️ {error_msg}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return create_mock_result(50, error_msg)
            
    
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
