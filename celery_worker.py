from celery import Celery
import os
import httpx
import traceback
import tempfile
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

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
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
WINSTON_API_KEY = os.getenv("WINSTON_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# SightEngine API Keys
SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET")


# ============================================================
# YOUR PROPRIETARY SOURCE CREDIBILITY DATABASE
# This is YOUR IP - Build and maintain this!
# ============================================================

SOURCE_CREDIBILITY = {
    # Tier 1: Highly Trusted (90-100)
    "bbc.com": {"score": 95, "bias": "center", "tier": "tier1", "type": "established_news"},
    "bbc.co.uk": {"score": 95, "bias": "center", "tier": "tier1", "type": "established_news"},
    "reuters.com": {"score": 98, "bias": "center", "tier": "tier1", "type": "wire_service"},
    "apnews.com": {"score": 98, "bias": "center", "tier": "tier1", "type": "wire_service"},
    "theguardian.com": {"score": 90, "bias": "center-left", "tier": "tier1", "type": "established_news"},
    "nytimes.com": {"score": 92, "bias": "center-left", "tier": "tier1", "type": "established_news"},
    "wsj.com": {"score": 92, "bias": "center-right", "tier": "tier1", "type": "established_news"},
    "economist.com": {"score": 93, "bias": "center", "tier": "tier1", "type": "analysis"},
    "npr.org": {"score": 91, "bias": "center-left", "tier": "tier1", "type": "public_media"},
    
    # Tier 2: Generally Reliable (70-89)
    "cnn.com": {"score": 80, "bias": "left", "tier": "tier2", "type": "cable_news"},
    "foxnews.com": {"score": 75, "bias": "right", "tier": "tier2", "type": "cable_news"},
    "cbsnews.com": {"score": 85, "bias": "center-left", "tier": "tier2", "type": "broadcast_news"},
    "nbcnews.com": {"score": 85, "bias": "center-left", "tier": "tier2", "type": "broadcast_news"},
    "washingtonpost.com": {"score": 88, "bias": "center-left", "tier": "tier2", "type": "established_news"},
    "bloomberg.com": {"score": 87, "bias": "center", "tier": "tier2", "type": "financial_news"},
    "ft.com": {"score": 90, "bias": "center", "tier": "tier2", "type": "financial_news"},
    
    # Tier 3: Mixed Reliability (50-69)
    "dailymail.co.uk": {"score": 55, "bias": "right", "tier": "tier3", "type": "tabloid"},
    "huffpost.com": {"score": 65, "bias": "left", "tier": "tier3", "type": "digital_news"},
    "buzzfeed.com": {"score": 60, "bias": "left", "tier": "tier3", "type": "digital_news"},
    "newsweek.com": {"score": 68, "bias": "center", "tier": "tier3", "type": "weekly_magazine"},
    
    # Tier 4: Low Credibility (0-49)
    "infowars.com": {"score": 10, "bias": "extreme-right", "tier": "tier4", "type": "conspiracy"},
    "breitbart.com": {"score": 35, "bias": "extreme-right", "tier": "tier4", "type": "partisan"},
    "naturalnews.com": {"score": 15, "bias": "extreme-right", "tier": "tier4", "type": "conspiracy"},
    "rt.com": {"score": 30, "bias": "varies", "tier": "tier4", "type": "state_media"},
    "presstv.ir": {"score": 25, "bias": "varies", "tier": "tier4", "type": "state_media"},
}


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
        elif content_type == 'news':
            result = verify_news(url)
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

@app.task(name='credisource.verify_content_file')
def verify_content_file_task(job_id, file_base64, filename, content_type):
    """Process verification job for uploaded files"""
    
    print(f"🔍 Processing uploaded file job {job_id}: {filename} (type: {content_type})")
    
    try:
        import base64
        
        # Decode file from base64
        file_data = base64.b64decode(file_base64)
        print(f"📦 Decoded file: {len(file_data)} bytes")
        
        # Run detection based on content type
        if content_type == 'image':
            result = detect_image_video_from_data(file_data, filename)
        elif content_type == 'video':
            # Videos use the same detection as images (AIorNOT supports both)
            print(f"🎬 Processing video file...")
            result = detect_image_video_from_data(file_data, filename, is_video=True)
        elif content_type == 'text':
            # For text files, decode as string
            text_content = file_data.decode('utf-8')
            result = detect_text(text_content)
        else:
            result = {"error": "Unsupported content type"}
        
        print(f"✅ Completed file job {job_id}: Score {result.get('trust_score', {}).get('score', 'N/A')}")
        return result
        
    except Exception as e:
        print(f"❌ Error in file job {job_id}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e)
        }


# ============================================================
# SIGHTENGINE DETECTION FUNCTIONS
# ============================================================

def detect_with_sightengine_url(image_url):
    """
    SightEngine AI detection via URL
    Returns: AI confidence 0-1 (0=human, 1=AI)
    """
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        print("⚠️ SightEngine credentials not configured")
        return None
    
    try:
        print(f"👁️ Calling SightEngine (URL)...")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                "https://api.sightengine.com/1.0/check.json",
                params={
                    'models': 'genai',
                    'api_user': SIGHTENGINE_API_USER,
                    'api_secret': SIGHTENGINE_API_SECRET,
                    'url': image_url
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"👁️ SightEngine response: {data}")
                
                # Extract AI probability
                ai_prob = data.get('type', {}).get('ai_generated', 0.5)
                
                print(f"✅ SightEngine: {int((1-ai_prob)*100)}% human ({int(ai_prob*100)}% AI)")
                
                return {
                    "provider": "SightEngine",
                    "ai_confidence": ai_prob,
                    "verdict": "AI-generated" if ai_prob > 0.5 else "Real",
                    "raw_response": data
                }
            else:
                print(f"⚠️ SightEngine error: {response.status_code}")
                print(f"⚠️ Response: {response.text}")
                return None
                
    except Exception as e:
        print(f"⚠️ SightEngine exception: {str(e)}")
        traceback.print_exc()
        return None


def detect_with_sightengine_file(image_data, filename):
    """
    SightEngine AI detection via file upload
    Returns: AI confidence 0-1 (0=human, 1=AI)
    """
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        print("⚠️ SightEngine credentials not configured")
        return None
    
    try:
        print(f"👁️ Calling SightEngine (file upload)...")
        
        # Create a temporary file-like object for the upload
        import io
        file_obj = io.BytesIO(image_data)
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.sightengine.com/1.0/check.json",
                data={
                    'models': 'genai',
                    'api_user': SIGHTENGINE_API_USER,
                    'api_secret': SIGHTENGINE_API_SECRET
                },
                files={
                    'media': (filename, file_obj, 'image/jpeg')
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"👁️ SightEngine file response: {data}")
                
                ai_prob = data.get('type', {}).get('ai_generated', 0.5)
                
                print(f"✅ SightEngine: {int((1-ai_prob)*100)}% human")
                
                return {
                    "provider": "SightEngine",
                    "ai_confidence": ai_prob,
                    "verdict": "AI-generated" if ai_prob > 0.5 else "Real",
                    "raw_response": data
                }
            else:
                print(f"⚠️ SightEngine error: {response.status_code}")
                return None
                
    except Exception as e:
        print(f"⚠️ SightEngine file exception: {str(e)}")
        traceback.print_exc()
        return None


# ============================================================
# BACKUP DETECTION FUNCTIONS
# ============================================================

def reverse_image_search(url):
    """Use Google to find where this image appears online"""
    
    if not GOOGLE_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        print("⚠️ Google Search not configured, skipping")
        return None
    
    try:
        print(f"🔍 Running Google Search for image context...")
        
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = parsed.path.split('/')[-1]
        domain = parsed.netloc
        
        search_query = f'"{url}" OR "{filename}"'
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_SEARCH_ENGINE_ID,
                    "q": search_query,
                    "num": 10
                }
            )
            
            print(f"🔍 Google response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ Google Search error: {response.text}")
                return None
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                print(f"📭 No results found")
                return {
                    "found": False,
                    "num_results": 0
                }
            
            print(f"✅ Found {len(items)} results mentioning this image")
            
            domains = []
            suspicious_keywords = ["ai", "midjourney", "dalle", "stable-diffusion", "generated", "synthetic", "fake", "artificial"]
            suspicious_count = 0
            
            for item in items:
                link = item.get("link", "")
                title = item.get("title", "").lower()
                snippet = item.get("snippet", "").lower()
                
                item_domain = urlparse(link).netloc
                domains.append(item_domain)
                
                text = title + " " + snippet
                if any(keyword in text for keyword in suspicious_keywords):
                    suspicious_count += 1
            
            suspicion_ratio = suspicious_count / len(items) if items else 0
            
            print(f"📊 Suspicious results: {suspicious_count}/{len(items)} ({int(suspicion_ratio*100)}%)")
            
            return {
                "found": True,
                "num_results": len(items),
                "domains": list(set(domains))[:5],
                "suspicious_ratio": suspicion_ratio,
                "suspicious_count": suspicious_count
            }
            
    except Exception as e:
        print(f"⚠️ Google Search error: {str(e)}")
        return None


def detect_with_huggingface(image_data):
    """Detect AI using Hugging Face SDXL detector - BACKUP METHOD"""
    
    if not HUGGINGFACE_API_KEY:
        print("⚠️ No Hugging Face API key, skipping")
        return None
    
    try:
        import base64
        
        print(f"🤗 Calling Hugging Face SDXL detector (backup)...")
        
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api-inference.huggingface.co/models/Organika/sdxl-detector",
                headers={
                    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "inputs": image_b64
                }
            )
            
            print(f"🤗 HF Response status: {response.status_code}")
            
            if response.status_code == 503:
                print("⏳ Model loading, waiting 10 seconds...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/Organika/sdxl-detector",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": image_b64}
                )
            
            if response.status_code != 200:
                print(f"⚠️ HF API error: {response.status_code}")
                return None
            
            data = response.json()
            print(f"🤗 HF Response: {data}")
            
            ai_confidence = 0.5
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    label = result.get("label", "")
                    score = result.get("score", 0.5)
                    if label in ["artificial", "AI", "LABEL_1"]:
                        ai_confidence = score
                        break
            
            print(f"✅ HF AI confidence: {ai_confidence:.2%}")
            
            return {
                "provider": "Hugging Face (Backup)",
                "ai_confidence": ai_confidence,
                "verdict": "AI-generated" if ai_confidence > 0.5 else "Real",
                "raw_response": data
            }
            
    except Exception as e:
        print(f"⚠️ Hugging Face error: {str(e)}")
        return None


def detect_with_aiornot(url_or_data, is_file=False, is_video=False):
    """Detect AI using AIorNOT API - BACKUP METHOD"""
    
    if not AIORNOT_API_KEY:
        print("⚠️ No AIorNOT API key, skipping")
        return None
    
    try:
        content_type = "video" if is_video else "image"
        print(f"🔍 Calling AIorNOT API ({content_type})...")
        
        with httpx.Client(timeout=60.0) as client:
            if is_file:
                import io
                file_obj = io.BytesIO(url_or_data) if isinstance(url_or_data, bytes) else url_or_data
                
                response = client.post(
                    "https://api.aiornot.com/v1/reports/file",
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"},
                    files={"object": ("file", file_obj, f"{content_type}/jpeg")}
                )
            else:
                response = client.post(
                    "https://api.aiornot.com/v1/reports/url",
                    headers={
                        "Authorization": f"Bearer {AIORNOT_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={"url": url_or_data}
                )
            
            print(f"🔍 AIorNOT Response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ AIorNOT error: {response.text}")
                return None
            
            data = response.json()
            print(f"🔍 AIorNOT Response: {data}")
            
            verdict = data.get("verdict", "unknown")
            ai_confidence = 0.5
            
            if verdict == "ai":
                ai_confidence = 0.9
            elif verdict == "human":
                ai_confidence = 0.1
            elif verdict == "unknown":
                ai_confidence = 0.5
            
            print(f"✅ AIorNOT verdict: {verdict} (AI confidence: {ai_confidence:.2%})")
            
            return {
                "provider": "AIorNOT (Backup)",
                "ai_confidence": ai_confidence,
                "verdict": verdict,
                "raw_response": data
            }
            
    except Exception as e:
        print(f"⚠️ AIorNOT error: {str(e)}")
        traceback.print_exc()
        return None


# ============================================================
# IMAGE/VIDEO DETECTION WITH SIGHTENGINE PRIMARY
# ============================================================

def detect_image_video(url):
    """
    Detect AI in images/videos from URL
    SightEngine as primary, AIorNOT as backup
    """
    
    print(f"🔍 Starting image/video AI detection for URL: {url}")
    
    try:
        print(f"📥 Downloading image...")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                print(f"❌ Failed to download: {response.status_code}")
                return create_mock_result(50, "Failed to download content")
            image_data = response.content
            print(f"✅ Downloaded {len(image_data)} bytes")
    except Exception as e:
        print(f"❌ Download error: {str(e)}")
        return create_mock_result(50, f"Download error: {str(e)}")
    
    # Try SightEngine first (PRIMARY)
    sightengine_result = detect_with_sightengine_url(url)
    
    # Try AIorNOT as backup
    aiornot_result = detect_with_aiornot(url, is_file=False)
    
    # If both primary methods fail, try Hugging Face
    hf_result = None
    if sightengine_result is None and aiornot_result is None:
        print(f"⚠️ Both primary detectors failed, trying Hugging Face backup...")
        hf_result = detect_with_huggingface(image_data)
    
    # Collect all successful results
    results = []
    if sightengine_result:
        results.append(sightengine_result)
    if aiornot_result:
        results.append(aiornot_result)
    if hf_result:
        results.append(hf_result)
    
    # If all failed
    if not results:
        print(f"❌ All detectors failed")
        return create_mock_result(50, "All AI detectors unavailable")
    
    # Calculate ensemble score
    total_confidence = sum(r["ai_confidence"] for r in results)
    avg_confidence = total_confidence / len(results)
    
    # Amplify for more decisive results
    amplified_confidence = amplify_confidence(avg_confidence)
    
    # Convert to trust score (inverse of AI confidence)
    trust_score = int((1 - amplified_confidence) * 100)
    label_info = get_label_with_explanation(trust_score)
    
    print(f"📊 Ensemble results from {len(results)} detector(s)")
    print(f"📊 Average AI confidence: {int(avg_confidence * 100)}%")
    print(f"📊 Amplified confidence: {int(amplified_confidence * 100)}%")
    print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
    
    # Build evidence
    evidence = [
        {
            "category": "Combined Analysis",
            "signal": f"Ensemble score from {len(results)} detector(s): {int(amplified_confidence * 100)}% AI confidence",
            "confidence": float(amplified_confidence),
            "details": {
                "num_detectors": len(results),
                "combined_confidence": float(amplified_confidence)
            }
        }
    ]
    
    for result in results:
        evidence.append({
            "category": f"AI Detection - {result['provider']}",
            "signal": f"{result['provider']}: {result['verdict']} ({int(result['ai_confidence'] * 100)}% AI confidence)",
            "confidence": float(result['ai_confidence']),
            "details": result
        })
    
    return {
        "trust_score": {
            "score": trust_score,
            "label": label_info["label"],
            "explanation": label_info["explanation"],
            "confidence": label_info["confidence"],
            "recommended_action": label_info["action"],
            "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
        },
        "evidence": evidence,
        "metadata": {
            "provider": "Ensemble Detection",
            "content_type": "image",
            "num_detectors": len(results),
            "detectors": [r["provider"] for r in results]
        }
    }


def detect_image_video_from_data(image_data, filename, is_video=False):
    """
    Detect AI in images/videos from uploaded file data
    SightEngine as primary, AIorNOT as backup
    """
    
    content_type = "video" if is_video else "image"
    print(f"🔍 Starting {content_type} AI detection for uploaded file: {filename}")
    print(f"📦 File size: {len(image_data)} bytes")
    
    # Try SightEngine first (PRIMARY)
    sightengine_result = detect_with_sightengine_file(image_data, filename)
    
    # Try AIorNOT as backup
    aiornot_result = detect_with_aiornot(image_data, is_file=True, is_video=is_video)
    
    # If both primary methods fail, try Hugging Face (images only)
    hf_result = None
    if sightengine_result is None and aiornot_result is None and not is_video:
        print(f"⚠️ Both primary detectors failed, trying Hugging Face backup...")
        hf_result = detect_with_huggingface(image_data)
    
    # Collect all successful results
    results = []
    if sightengine_result:
        results.append(sightengine_result)
    if aiornot_result:
        results.append(aiornot_result)
    if hf_result:
        results.append(hf_result)
    
    # If all failed
    if not results:
        print(f"❌ All detectors failed")
        return create_mock_result(50, "All AI detectors unavailable")
    
    # Calculate ensemble score
    total_confidence = sum(r["ai_confidence"] for r in results)
    avg_confidence = total_confidence / len(results)
    
    # Amplify for more decisive results
    amplified_confidence = amplify_confidence(avg_confidence)
    
    # Convert to trust score (inverse of AI confidence)
    trust_score = int((1 - amplified_confidence) * 100)
    label_info = get_label_with_explanation(trust_score)
    
    print(f"📊 Ensemble results from {len(results)} detector(s)")
    print(f"📊 Average AI confidence: {int(avg_confidence * 100)}%")
    print(f"📊 Amplified confidence: {int(amplified_confidence * 100)}%")
    print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
    
    # Build evidence
    evidence = [
        {
            "category": "Combined Analysis",
            "signal": f"Ensemble score from {len(results)} detector(s): {int(amplified_confidence * 100)}% AI confidence",
            "confidence": float(amplified_confidence),
            "details": {
                "num_detectors": len(results),
                "combined_confidence": float(amplified_confidence)
            }
        }
    ]
    
    for result in results:
        evidence.append({
            "category": f"AI Detection - {result['provider']}",
            "signal": f"{result['provider']}: {result['verdict']} ({int(result['ai_confidence'] * 100)}% AI confidence)",
            "confidence": float(result['ai_confidence']),
            "details": result
        })
    
    import uuid
    return {
        "trust_score": {
            "score": trust_score,
            "label": label_info["label"],
            "explanation": label_info["explanation"],
            "confidence": label_info["confidence"],
            "recommended_action": label_info["action"],
            "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
        },
        "evidence": evidence,
        "metadata": {
            "filename": filename,
            "provider": "Ensemble Detection",
            "content_type": content_type,
            "report_id": str(uuid.uuid4())
        }
    }


# ============================================================
# TEXT DETECTION
# ============================================================

def detect_text_winston(text_content):
    """Detect AI-generated text using Winston AI (Primary method)"""
    
    if not WINSTON_API_KEY:
        print("⚠️ No Winston AI key configured")
        return None
    
    try:
        print(f"🔍 Calling Winston AI...")
        print(f"📝 Text length: {len(text_content)} characters")
        
        MAX_CHARS = 10000
        text_to_check = text_content[:MAX_CHARS] if len(text_content) > MAX_CHARS else text_content
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.gowinston.ai/v2/plagiarism",
                headers={
                    "Authorization": f"Bearer {WINSTON_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "text": text_to_check,
                    "language": "en"
                }
            )
            
            print(f"🔍 Winston response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ Winston error: {response.text}")
                return None
            
            data = response.json()
            print(f"🔍 Winston response: {data}")
            
            if "score" in data:
                human_score = data["score"]
                ai_confidence = (100 - human_score) / 100
                
                print(f"✅ Winston: {human_score}% human = {int(ai_confidence * 100)}% AI confidence")
                
                return {
                    "provider": "Winston AI",
                    "ai_confidence": ai_confidence,
                    "verdict": "AI-generated" if ai_confidence > 0.5 else "Human-written",
                    "raw_response": data,
                    "details": {
                        "winston_human_score": human_score
                    }
                }
            else:
                print(f"⚠️ Could not extract score from Winston response")
                return None
            
    except Exception as e:
        print(f"⚠️ Winston AI error: {str(e)}")
        traceback.print_exc()
        return None


def detect_text_huggingface(text_content):
    """Detect AI-generated text using OpenAI's RoBERTa Large detector - BACKUP"""
    
    if not HUGGINGFACE_API_KEY:
        print("⚠️ No Hugging Face API key")
        return None
    
    try:
        print(f"🤗 Calling OpenAI RoBERTa Large (backup)...")
        
        MAX_CHARS = 2000
        text_to_check = text_content[:MAX_CHARS] if len(text_content) > MAX_CHARS else text_content
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api-inference.huggingface.co/models/openai-community/roberta-large-openai-detector",
                headers={
                    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"inputs": text_to_check}
            )
            
            if response.status_code == 503:
                print("⏳ Model loading, waiting 10 seconds...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/openai-community/roberta-large-openai-detector",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": text_to_check}
                )
            
            if response.status_code != 200:
                print(f"⚠️ Backup API error: {response.status_code}")
                return None
            
            data = response.json()
            
            ai_confidence = 0.5
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    label = result.get("label", "")
                    score = result.get("score", 0.5)
                    if label == "LABEL_1":
                        ai_confidence = score
                        break
            
            print(f"✅ Backup AI confidence: {ai_confidence:.2%}")
            
            return {
                "provider": "OpenAI RoBERTa (Backup)",
                "ai_confidence": ai_confidence,
                "verdict": "AI-generated" if ai_confidence > 0.5 else "Human-written",
                "raw_response": data
            }
            
    except Exception as e:
        print(f"⚠️ Backup detector error: {str(e)}")
        return None


def detect_text(text_content):
    """Detect AI in text using Winston AI (primary) with Hugging Face backup"""
    
    print(f"🔍 Starting text AI detection (length: {len(text_content)} chars)")
    
    result = detect_text_winston(text_content)
    
    if result is None:
        print(f"⚠️ Winston AI unavailable, using backup detector")
        result = detect_text_huggingface(text_content)
    
    if result is None:
        print(f"❌ Text detection failed: All detectors unavailable")
        return create_mock_result(50, "Text detection API unavailable")
    
    ai_confidence = result.get("ai_confidence", 0.5)
    trust_score = int((1 - ai_confidence) * 100)
    label_info = get_label_with_explanation(trust_score)
    
    print(f"📊 AI confidence: {int(ai_confidence * 100)}%")
    print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
    
    return {
        "trust_score": {
            "score": trust_score,
            "label": label_info["label"],
            "explanation": label_info["explanation"],
            "confidence": label_info["confidence"],
            "recommended_action": label_info["action"],
            "confidence_band": [max(0, trust_score - 10), min(100, trust_score + 10)]
        },
        "evidence": [
            {
                "category": "AI Text Detection",
                "signal": f"{result['provider']}: {result['verdict']} ({int(ai_confidence * 100)}% AI confidence)",
                "confidence": float(ai_confidence),
                "details": result
            }
        ],
        "metadata": {
            "provider": result["provider"],
            "content_type": "text",
            "text_length": len(text_content),
            "detector": result["provider"]
        }
    }


# ============================================================
# NEWS VERIFICATION FUNCTIONS (YOUR PROPRIETARY IP!)
# ============================================================

def extract_article(url):
    """Extract article content from URL - YOUR CODE"""
    print(f"📰 Extracting article from: {url}")
    
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            response = client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {"error": f"Failed to fetch article: {response.status_code}"}
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            domain = urlparse(url).netloc.replace('www.', '')
            
            # Extract title
            title = None
            if soup.find('h1'):
                title = soup.find('h1').get_text(strip=True)
            elif soup.find('meta', property='og:title'):
                title = soup.find('meta', property='og:title')['content']
            elif soup.find('title'):
                title = soup.find('title').get_text(strip=True)
            
            # Extract author
            author = None
            author_meta = soup.find('meta', attrs={'name': 'author'})
            if author_meta:
                author = author_meta.get('content')
            
            # Extract date
            date = None
            date_meta = soup.find('meta', property='article:published_time')
            if date_meta:
                date = date_meta.get('content')
            
            # Extract text
            for script in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                script.decompose()
            
            article_text = ""
            article_tag = soup.find('article')
            if article_tag:
                paragraphs = article_tag.find_all('p')
                article_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
            else:
                paragraphs = soup.find_all('p')
                article_text = ' '.join([p.get_text(strip=True) for p in paragraphs[:20]])
            
            # Extract images
            images = []
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and not src.startswith('data:'):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = f"https://{domain}{src}"
                    images.append(src)
            
            print(f"✅ Extracted: {len(article_text)} chars, {len(images)} images")
            
            return {
                "url": url,
                "domain": domain,
                "title": title,
                "author": author,
                "date": date,
                "text": article_text,
                "images": images[:5],
                "word_count": len(article_text.split())
            }
            
    except Exception as e:
        print(f"❌ Extraction error: {str(e)}")
        return {"error": str(e)}


def check_source_credibility(domain):
    """Check source credibility using YOUR database - YOUR IP!"""
    print(f"🔍 Checking source credibility: {domain}")
    
    if domain in SOURCE_CREDIBILITY:
        source = SOURCE_CREDIBILITY[domain]
        print(f"✅ Found in database: {source['score']}/100 ({source['tier']})")
        return {
            "known_source": True,
            "credibility_score": source["score"],
            "bias": source["bias"],
            "tier": source["tier"],
            "type": source["type"],
            "verdict": get_source_verdict(source["score"])
        }
    
    print(f"⚠️ Unknown source, using heuristics...")
    
    heuristic_score = calculate_domain_heuristics(domain)
    
    return {
        "known_source": False,
        "credibility_score": heuristic_score,
        "bias": "unknown",
        "tier": "unknown",
        "type": "unknown",
        "verdict": "Unknown source - verify independently",
        "warning": "This source is not in our verified database"
    }


def calculate_domain_heuristics(domain):
    """YOUR algorithm for unknown sources"""
    score = 50
    
    red_flags = [
        'truth', 'real', 'patriot', 'freedom', 'news24', 'breaking',
        'exclusive', 'insider', 'leaked', 'exposed'
    ]
    for flag in red_flags:
        if flag in domain.lower():
            score -= 10
    
    if domain.endswith('.gov'):
        score += 20
    elif domain.endswith('.edu'):
        score += 15
    elif domain.endswith('.org'):
        score += 5
    
    if domain.count('.') > 2:
        score -= 5
    
    return max(0, min(100, score))


def get_source_verdict(score):
    """Convert source score to verdict"""
    if score >= 90:
        return "Highly credible source"
    elif score >= 70:
        return "Generally reliable source"
    elif score >= 50:
        return "Mixed reliability - verify claims"
    else:
        return "Low credibility source - high skepticism advised"


def cross_reference_story(title, text):
    """Cross-reference story using News API - YOUR ALGORITHM"""
    
    if not NEWS_API_KEY:
        print("⚠️ No News API key - skipping cross-reference")
        return {"checked": False, "reason": "News API key not configured"}
    
    try:
        print(f"🔍 Cross-referencing story...")
        
        # Extract key terms from title for search
        search_query = title[:100] if title else text[:100]
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": search_query,
                    "apiKey": NEWS_API_KEY,
                    "pageSize": 20,
                    "sortBy": "relevancy"
                }
            )
            
            if response.status_code != 200:
                print(f"⚠️ News API error: {response.status_code}")
                return {"checked": False, "reason": f"API error: {response.status_code}"}
            
            data = response.json()
            articles = data.get("articles", [])
            
            if not articles:
                return {
                    "checked": True,
                    "corroboration_score": 10,
                    "verdict": "No corroborating sources found",
                    "num_sources": 0
                }
            
            # Analyze sources
            unique_sources = set()
            trusted_sources = []
            
            for article in articles:
                source_name = article.get("source", {}).get("name", "")
                domain = urlparse(article.get("url", "")).netloc.replace('www.', '')
                
                unique_sources.add(domain)
                
                if domain in SOURCE_CREDIBILITY:
                    if SOURCE_CREDIBILITY[domain]["score"] >= 70:
                        trusted_sources.append(domain)
            
            corroboration_score = min(100, (len(unique_sources) * 10) + (len(trusted_sources) * 20))
            
            print(f"✅ Found {len(unique_sources)} sources, {len(trusted_sources)} trusted")
            
            return {
                "checked": True,
                "num_sources": len(unique_sources),
                "trusted_sources": len(trusted_sources),
                "corroboration_score": corroboration_score,
                "verdict": get_corroboration_verdict(corroboration_score),
                "source_list": list(unique_sources)[:5]
            }
            
    except Exception as e:
        print(f"❌ Cross-reference error: {str(e)}")
        return {"checked": False, "reason": str(e)}


def get_corroboration_verdict(score):
    """Convert corroboration score to verdict"""
    if score >= 70:
        return "Story widely reported by multiple sources"
    elif score >= 40:
        return "Some corroboration from other sources"
    else:
        return "Limited corroboration - single source story"


def calculate_news_trust_score(source_check, text_detection, image_detections, cross_ref, article):
    """YOUR PROPRIETARY SCORING ALGORITHM - THE SECRET SAUCE!"""
    
    scores = []
    weights = []
    factors = []
    
    # Factor 1: Source Credibility (40%)
    source_score = source_check["credibility_score"]
    scores.append(source_score)
    weights.append(0.40)
    factors.append({
        "factor": "Source Credibility",
        "score": source_score,
        "weight": "40%",
        "verdict": source_check["verdict"]
    })
    
    # Factor 2: Content Authenticity (30%)
    if text_detection:
        content_score = text_detection["trust_score"]["score"]
        scores.append(content_score)
        weights.append(0.30)
        factors.append({
            "factor": "Text Authenticity",
            "score": content_score,
            "weight": "30%",
            "verdict": text_detection["trust_score"]["label"]
        })
    else:
        # If text detection skipped (short article), use source score as proxy
        print(f"💡 Text detection skipped - using source credibility as proxy")
        scores.append(source_score)
        weights.append(0.30)
        factors.append({
            "factor": "Text Authenticity",
            "score": source_score,
            "weight": "30%",
            "verdict": "Not analyzed (article too short - based on source trust)"
        })
    
    # Factor 3: Image Authenticity (15%)
    if image_detections:
        avg_image_score = sum((1 - img["ai_confidence"]) * 100 for img in image_detections) / len(image_detections)
        scores.append(avg_image_score)
        weights.append(0.15)
        factors.append({
            "factor": "Image Authenticity",
            "score": int(avg_image_score),
            "weight": "15%",
            "verdict": f"{len(image_detections)} images analyzed"
        })
    
    # Factor 4: Cross-Reference (15%)
    if cross_ref.get("checked"):
        corr_score = cross_ref.get("corroboration_score", 50)
        scores.append(corr_score)
        weights.append(0.15)
        factors.append({
            "factor": "Cross-Reference",
            "score": corr_score,
            "weight": "15%",
            "verdict": cross_ref["verdict"]
        })
    
    # Calculate weighted average
    if scores:
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        final_score = sum(s * w for s, w in zip(scores, normalized_weights))
        final_score = int(final_score)
    else:
        final_score = 50
    
    label_info = get_label_with_explanation(final_score)
    
    return {
        "score": final_score,
        "label": label_info["label"],
        "explanation": label_info["explanation"],
        "confidence": label_info["confidence"],
        "recommended_action": label_info["action"],
        "scoring_factors": factors,
        "methodology": "Multi-factor weighted ensemble"
    }


def verify_news(url):
    """
    YOUR PROPRIETARY NEWS VERIFICATION ENGINE
    This is YOUR IP - the secret sauce!
    """
    print(f"\n🗞️ Starting news verification for: {url}")
    print(f"=" * 60)
    
    # Step 1: Extract article
    article = extract_article(url)
    if "error" in article:
        return {
            "error": article["error"],
            "trust_score": {"score": 0, "label": "Error"}
        }
    
    # Step 2: Check source credibility (YOUR DATABASE!)
    source_check = check_source_credibility(article["domain"])
    
    # Step 3: Detect AI in text
    text_detection = None
    if article["text"] and len(article["text"]) > 300:
        # Only run text detection on substantial text
        # Skip very short snippets (live blogs, etc.) that cause false positives
        if article["word_count"] > 100:  # At least 100 words
            text_detection = detect_text(article["text"])
        else:
            print(f"⚠️ Skipping text AI detection - article too short ({article['word_count']} words)")
            print(f"💡 Short articles (live blogs, updates) often trigger false positives")
    
    # Step 4: Detect AI in images
    image_detections = []
    if article["images"]:
        for img_url in article["images"][:3]:
            result = detect_with_sightengine_url(img_url)
            if result:
                image_detections.append(result)
    
    # Step 5: Cross-reference check (YOUR ALGORITHM!)
    cross_ref = cross_reference_story(article["title"], article["text"])
    
    # Step 6: Calculate YOUR PROPRIETARY TRUST SCORE
    trust_score = calculate_news_trust_score(
        source_check,
        text_detection,
        image_detections,
        cross_ref,
        article
    )
    
    print(f"=" * 60)
    print(f"📊 Final News Trust Score: {trust_score['score']}/100")
    print(f"\n")
    
    return {
        "trust_score": trust_score,
        "article": {
            "title": article["title"],
            "domain": article["domain"],
            "author": article["author"],
            "date": article["date"],
            "word_count": article["word_count"]
        },
        "source_credibility": source_check,
        "content_analysis": {
            "text_ai_detection": text_detection.get("trust_score") if text_detection else None,
            "images_checked": len(image_detections),
            "image_ai_detection": image_detections
        },
        "cross_reference": cross_ref,
        "metadata": {
            "provider": "CrediSource News Engine",
            "content_type": "news_article",
            "verification_layers": 5
        }
    }


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def amplify_confidence(confidence):
    """Amplify confidence scores to make them more decisive"""
    centered = confidence - 0.5
    amplified = centered * (abs(centered) ** 0.3) * 2.5
    result = 0.5 + amplified
    return max(0.0, min(1.0, result))


def get_label_with_explanation(score):
    """Convert score to consumer-friendly label with explanation"""
    if score >= 65:
        return {
            "label": "Likely Real",
            "explanation": "This content appears to be authentic. Our AI detection found strong indicators that this was created by a human or captured with a real camera.",
            "confidence": "High",
            "action": "This content is likely trustworthy."
        }
    elif score >= 50:
        return {
            "label": "Probably Real", 
            "explanation": "This content likely appears authentic, but we detected some minor inconsistencies. This could be due to image editing or compression.",
            "confidence": "Moderate-High",
            "action": "This content is probably trustworthy, but verify important details."
        }
    elif score >= 35:
        return {
            "label": "Probably Fake",
            "explanation": "This content shows signs of AI generation. We detected patterns commonly found in AI-created images or text.",
            "confidence": "Moderate-High",
            "action": "Be cautious. This content may be AI-generated or heavily manipulated."
        }
    else:
        return {
            "label": "Likely Fake",
            "explanation": "This content appears to be AI-generated. We found strong indicators of synthetic creation, including telltale artifacts and patterns typical of AI generators.",
            "confidence": "High",
            "action": "This content is likely fake. Do not trust without additional verification."
        }

def get_label(score):
    """Convert score to consumer-friendly label (backward compatibility)"""
    return get_label_with_explanation(score)["label"]

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
