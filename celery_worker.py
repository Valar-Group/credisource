from celery import Celery
import os
import httpx
import traceback
import tempfile
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
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
WINSTON_API_KEY = os.getenv("WINSTON_API_KEY")

# NEW: SightEngine API Keys
SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET")

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
# NEW: SIGHTENGINE DETECTION FUNCTIONS
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
# EXISTING DETECTION FUNCTIONS (keeping for backup)
# ============================================================

def reverse_image_search(url):
    """Use Google to find where this image appears online"""
    
    if not GOOGLE_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        print("⚠️ Google Search not configured, skipping")
        return None
    
    try:
        print(f"🔍 Running Google Search for image context...")
        
        # Extract filename and domain from URL for better search
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = parsed.path.split('/')[-1]
        domain = parsed.netloc
        
        # Search for the image URL and filename
        search_query = f'"{url}" OR "{filename}"'
        
        with httpx.Client(timeout=30.0) as client:
            # Use Google Custom Search API
            response = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_SEARCH_ENGINE_ID,
                    "q": search_query,
                    "num": 10  # Get top 10 results
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
            
            # Analyze the results
            domains = []
            suspicious_keywords = ["ai", "midjourney", "dalle", "stable-diffusion", "generated", "synthetic", "fake", "artificial"]
            suspicious_count = 0
            
            for item in items:
                link = item.get("link", "")
                title = item.get("title", "").lower()
                snippet = item.get("snippet", "").lower()
                
                # Extract domain
                item_domain = urlparse(link).netloc
                domains.append(item_domain)
                
                # Check for AI-related keywords
                text = title + " " + snippet
                if any(keyword in text for keyword in suspicious_keywords):
                    suspicious_count += 1
            
            # Calculate suspicion score
            suspicion_ratio = suspicious_count / len(items) if items else 0
            
            print(f"📊 Suspicious results: {suspicious_count}/{len(items)} ({int(suspicion_ratio*100)}%)")
            
            return {
                "found": True,
                "num_results": len(items),
                "domains": list(set(domains))[:5],  # Top 5 unique domains
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
        
        # Convert image to base64
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
            
            # Parse response
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
                # File upload
                import io
                file_obj = io.BytesIO(url_or_data) if isinstance(url_or_data, bytes) else url_or_data
                
                response = client.post(
                    "https://api.aiornot.com/v1/reports/file",
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"},
                    files={"object": ("file", file_obj, f"{content_type}/jpeg")}
                )
            else:
                # URL
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
            
            # Parse response
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
# UPDATED: IMAGE/VIDEO DETECTION WITH SIGHTENGINE PRIMARY
# ============================================================

def detect_image_video(url):
    """
    Detect AI in images/videos from URL
    NEW: SightEngine as primary, AIorNOT as backup
    """
    
    print(f"🔍 Starting image/video AI detection for URL: {url}")
    
    # Download image data for backup methods
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
    NEW: SightEngine as primary, AIorNOT as backup
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
# TEXT DETECTION (UNCHANGED)
# ============================================================

def detect_text_winston(text_content):
    """Detect AI-generated text using Winston AI (Primary method)"""
    
    if not WINSTON_API_KEY:
        print("⚠️ No Winston AI key configured")
        return None
    
    try:
        print(f"🔍 Calling Winston AI...")
        print(f"📝 Text length: {len(text_content)} characters")
        
        # Truncate if needed (Winston has limits)
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
                    "language": "en",
                    "version": "3.0"
                }
            )
            
            print(f"🔍 Winston response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ Winston API error: {response.text}")
                return None
            
            data = response.json()
            print(f"🔍 Winston response: {data}")
            
            # Winston returns a score from 0-100 where higher = more human
            # We need AI confidence (0-1) where higher = more AI
            if "score" in data:
                human_score = data["score"]  # 0-100, higher = more human
                ai_confidence = (100 - human_score) / 100  # Convert to 0-1, where 1 = definitely AI
                
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
        
        # Truncate if too long
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
            
            # Parse response
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
    
    # Try Winston AI first
    result = detect_text_winston(text_content)
    
    # If Winston fails, use Hugging Face backup
    if result is None:
        print(f"⚠️ Winston AI unavailable, using backup detector")
        result = detect_text_huggingface(text_content)
    
    # If both failed, return error
    if result is None:
        print(f"❌ Text detection failed: All detectors unavailable")
        return create_mock_result(50, "Text detection API unavailable")
    
    # Calculate trust score (inverse of AI confidence)
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
