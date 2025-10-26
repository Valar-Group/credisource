from celery import Celery
import os
import httpx
import traceback

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
    """Detect AI in images using AI or Not v2 SYNC API (no polling needed!)"""
    
    if not AIORNOT_API_KEY:
        print("⚠️ No AIORNOT_API_KEY found")
        return create_mock_result(75, "No AI or Not API key configured")
    
    try:
        print(f"🔍 Analyzing image with AI or Not v2: {url}")
        
        # Use v2 sync API - returns results immediately!
        with httpx.Client(timeout=90.0) as client:
            # Download the image first
            print(f"📥 Downloading image from URL...")
            image_response = client.get(url)
            
            if image_response.status_code != 200:
                error_msg = f"Failed to download image: {image_response.status_code}"
                print(f"⚠️ {error_msg}")
                return create_mock_result(50, error_msg)
            
            image_data = image_response.content
            print(f"✅ Downloaded {len(image_data)} bytes")
            
            # Submit to AI or Not v2 sync endpoint
            print(f"🔍 Submitting to AI or Not v2 sync API...")
            response = client.post(
                "https://api.aiornot.com/v2/image/sync",
                headers={
                    "Authorization": f"Bearer {AIORNOT_API_KEY}"
                },
                files={
                    "image": ("image.jpg", image_data, "image/jpeg")
                }
            )
            
            print(f"📡 Response status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"AI or Not API error {response.status_code}: {response.text}"
                print(f"⚠️ {error_msg}")
                return create_mock_result(50, error_msg)
            
            # Parse the response
            data = response.json()
            print(f"✅ Got response: {data.get('id')}")
            
            # Extract the AI detection results
            report = data.get("report", {})
            ai_generated = report.get("ai_generated", {})
            
            verdict = ai_generated.get("verdict", "unknown")
            ai_info = ai_generated.get("ai", {})
            human_info = ai_generated.get("human", {})
            
            ai_confidence = ai_info.get("confidence", 0.5)
            ai_detected = ai_info.get("is_detected", False)
            
            print(f"🎯 Verdict: {verdict}, AI Confidence: {ai_confidence}, AI Detected: {ai_detected}")
            
            # Calculate trust score
            if verdict.lower() in ["human", "real"]:
                # If verdict is human, use human confidence
                trust_score = int(human_info.get("confidence", 1 - ai_confidence) * 100)
            elif verdict.lower() in ["ai", "fake", "synthetic"]:
                # If verdict is AI, inverse of AI confidence
                trust_score = int((1 - ai_confidence) * 100)
            else:
                # Inconclusive
                trust_score = 50
            
            # Ensure score is in valid range
            trust_score = max(0, min(100, trust_score))
            
            label = get_label(trust_score)
            
            print(f"📊 Final trust score: {trust_score} ({label})")
            
            # Get generator info if available
            generator_info = ai_generated.get("generator", {})
            top_generators = []
            if generator_info:
                # Get top 3 generators by confidence
                sorted_gens = sorted(generator_info.items(), key=lambda x: x[1], reverse=True)[:3]
                top_generators = [f"{gen}: {int(conf*100)}%" for gen, conf in sorted_gens if conf > 0.5]
            
            evidence_signal = f"Verdict: {verdict} ({int(ai_confidence * 100)}% AI confidence)"
            if top_generators:
                evidence_signal += f" - Possible generators: {', '.join(top_generators)}"
            
            return {
                "trust_score": {
                    "score": trust_score,
                    "label": label,
                    "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
                },
                "evidence": [
                    {
                        "category": "AI Detection",
                        "signal": evidence_signal,
                        "confidence": float(ai_confidence),
                        "details": {
                            "provider": "aiornot",
                            "verdict": verdict,
                            "ai_confidence": float(ai_confidence),
                            "ai_detected": ai_detected,
                            "generators": generator_info
                        }
                    }
                ],
                "metadata": {
                    "url": url,
                    "provider": "AI or Not v2",
                    "content_type": "image",
                    "report_id": data.get("id")
                }
            }
            
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
