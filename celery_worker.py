from celery import Celery
import os
import httpx
import time
import traceback
import json

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
    """Detect AI in images using AI or Not (with polling) - DIAGNOSTIC VERSION"""
    
    if not AIORNOT_API_KEY:
        print("⚠️ No AIORNOT_API_KEY found")
        return create_mock_result(75, "No AI or Not API key configured")
    
    try:
        print(f"🔍 Submitting image to AI or Not: {url}")
        print(f"🔑 API Key (first 10 chars): {AIORNOT_API_KEY[:10]}...")
        
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
            print(f"📡 Submit response headers: {dict(submit_response.headers)}")
            print(f"📡 Submit response body: {submit_response.text}")
            
            if submit_response.status_code not in [200, 201]:
                error_msg = f"AI or Not submit error {submit_response.status_code}: {submit_response.text}"
                print(f"⚠️ {error_msg}")
                return create_mock_result(50, error_msg)
            
            # Try to parse JSON
            try:
                submit_data = submit_response.json()
                print(f"📋 Parsed submit data: {json.dumps(submit_data, indent=2)}")
            except Exception as json_error:
                print(f"❌ Failed to parse JSON: {json_error}")
                return create_mock_result(50, f"Invalid JSON response: {submit_response.text}")
            
            # Look for report_id in multiple possible locations
            report_id = (
                submit_data.get("id") or 
                submit_data.get("report_id") or 
                submit_data.get("reportId") or
                submit_data.get("data", {}).get("id")
            )
            
            if not report_id:
                print(f"⚠️ No report_id found in response!")
                print(f"Available keys: {list(submit_data.keys())}")
                return create_mock_result(50, f"No report_id returned. Response keys: {list(submit_data.keys())}")
            
            print(f"✅ Got report_id: {report_id}")
            
            # Step 2: Poll for the result
            max_attempts = 20  # Increased from 15
            poll_delay = 3     # Increased from 2 seconds
            
            for attempt in range(max_attempts):
                print(f"🔄 Polling attempt {attempt + 1}/{max_attempts} (waiting {poll_delay}s between polls)")
                
                time.sleep(poll_delay)
                
                result_response = client.get(
                    f"https://api.aiornot.com/v1/reports/{report_id}",
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"}
                )
                
                print(f"📊 Poll status: {result_response.status_code}")
                
                if result_response.status_code != 200:
                    print(f"⚠️ Poll error status {result_response.status_code}: {result_response.text}")
                    continue
                
                try:
                    result_data = result_response.json()
                    print(f"📋 Poll response: {json.dumps(result_data, indent=2)}")
                except Exception as json_error:
                    print(f"❌ Failed to parse poll JSON: {json_error}")
                    continue
                
                # Check status - try multiple possible field names
                status = (
                    result_data.get("status") or 
                    result_data.get("state") or
                    result_data.get("data", {}).get("status")
                )
                
                print(f"📊 Report status: '{status}'")
                
                # Check if processing is done - multiple possible values
                if status in ["done", "completed", "complete", "finished"]:
                    print(f"✅ Analysis complete! Full result: {json.dumps(result_data, indent=2)}")
                    
                    # Extract the verdict - try multiple paths
                    report = result_data.get("report", result_data.get("data", {}))
                    
                    verdict = (
                        report.get("verdict") or 
                        report.get("prediction") or
                        report.get("label") or
                        result_data.get("verdict") or
                        "unknown"
                    )
                    
                    confidence = (
                        report.get("confidence") or
                        report.get("score") or
                        result_data.get("confidence") or
                        0.5
                    )
                    
                    # Convert confidence to float if it's a string percentage
                    if isinstance(confidence, str):
                        confidence = float(confidence.strip('%')) / 100 if '%' in confidence else float(confidence)
                    
                    print(f"🎯 Extracted - Verdict: {verdict}, Confidence: {confidence}")
                    
                    # Calculate trust score
                    if str(verdict).lower() in ["human", "real", "authentic"]:
                        trust_score = int(confidence * 100)
                    elif str(verdict).lower() in ["ai", "fake", "synthetic", "generated"]:
                        trust_score = int((1 - confidence) * 100)
                    else:
                        print(f"⚠️ Unknown verdict '{verdict}', defaulting to 50")
                        trust_score = 50
                    
                    label = get_label(trust_score)
                    
                    print(f"📊 Final trust score: {trust_score} ({label})")
                    
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
                                "confidence": float(confidence),
                                "details": {
                                    "provider": "aiornot",
                                    "verdict": verdict,
                                    "confidence": float(confidence),
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
                
                elif status in ["failed", "error", "errored"]:
                    error_details = result_data.get('error') or result_data.get('message') or 'Unknown error'
                    error_msg = f"AI or Not analysis failed: {error_details}"
                    print(f"❌ {error_msg}")
                    return create_mock_result(50, error_msg)
                
                elif status in ["processing", "pending", "queued", "running"]:
                    print(f"⏳ Still processing... (status: {status})")
                    continue
                
                else:
                    print(f"⚠️ Unknown status: '{status}'. Full response: {result_data}")
                    # Continue polling for unknown statuses
                    continue
            
            # If we get here, polling timed out
            timeout_msg = f"AI or Not analysis timed out after {max_attempts * poll_delay} seconds"
            print(f"⏰ {timeout_msg}")
            return create_mock_result(50, timeout_msg)
            
    except Exception as e:
        error_msg = f"AI or Not detection error: {str(e)}"
        print(f"⚠️ {error_msg}")
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
    print(f"🔧 Creating mock result: score={score}, reason={reason}")
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
            "note": "Mock result - check API keys",
            "reason": reason
        }
    }
