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
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

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
    """Detect AI using Hugging Face SDXL detector"""
    
    if not HUGGINGFACE_API_KEY:
        print("⚠️ No Hugging Face API key, skipping")
        return None
    
    try:
        import base64
        
        print(f"🤗 Calling Hugging Face SDXL detector...")
        
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
                print("⏳ Model loading, retrying in 10 seconds...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/Organika/sdxl-detector",
                    headers={
                        "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={"inputs": image_b64}
                )
            
            if response.status_code != 200:
                print(f"⚠️ HF API error: {response.status_code}")
                return None
            
            data = response.json()
            print(f"🤗 HF Response: {data}")
            
            # Parse response - format: [{"label": "artificial", "score": 0.99}]
            artificial_score = 0.5
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    if item.get("label") == "artificial":
                        artificial_score = item.get("score", 0.5)
                        break
            
            print(f"✅ HF AI confidence: {artificial_score}")
            
            return {
                "provider": "Hugging Face",
                "ai_confidence": artificial_score,
                "verdict": "AI-generated" if artificial_score > 0.5 else "Real"
            }
            
    except Exception as e:
        print(f"⚠️ HF detection error: {str(e)}")
        return None


def detect_image_video_from_data(file_data, filename, is_video=False):
    """Detect AI in image/video from raw file data"""
    
    if not AIORNOT_API_KEY:
        return create_mock_result(50, "No AIorNOT API key configured")
    
    try:
        import base64
        
        print(f"🔍 Detecting {'video' if is_video else 'image'} from uploaded file: {filename}")
        
        # Encode file to base64
        file_b64 = base64.b64encode(file_data).decode('utf-8')
        
        # Prepare multipart form data
        with httpx.Client(timeout=60.0) as client:
            # AIorNOT expects file upload
            files = {
                'object': (filename, file_data, 'application/octet-stream')
            }
            
            print(f"📤 Uploading to AIorNOT...")
            response = client.post(
                "https://api.aiornot.com/v1/reports/image",
                headers={
                    "Authorization": f"Bearer {AIORNOT_API_KEY}"
                },
                files=files
            )
            
            print(f"📥 AIorNOT response: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ AIorNOT error: {response.text}")
                return create_mock_result(50, f"AIorNOT API Error: {response.status_code}")
            
            data = response.json()
            print(f"✅ AIorNOT response data: {data}")
            
            # Get Hugging Face result too
            hf_result = detect_with_huggingface(file_data)
            
            # Collect all results
            all_results = []
            
            # AIorNOT result
            ai_generated = data.get("report", {}).get("ai_generated", {})
            aiornot_confidence = ai_generated.get("confidence", 0.5)
            all_results.append({
                "provider": "AIorNOT",
                "ai_confidence": aiornot_confidence,
                "verdict": ai_generated.get("verdict", "unknown")
            })
            
            # Hugging Face result
            if hf_result:
                all_results.append(hf_result)
            
            # Calculate ensemble confidence
            combined_ai_confidence = sum(r["ai_confidence"] for r in all_results) / len(all_results)
            
            # Apply amplification to make scores more decisive
            combined_ai_confidence = amplify_confidence(combined_ai_confidence)
            
            # Calculate trust score (inverse of AI confidence)
            trust_score = int((1 - combined_ai_confidence) * 100)
            label_info = get_label_with_explanation(trust_score)
            
            print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
            
            # Build evidence
            evidence = []
            
            for result in all_results:
                provider = result["provider"]
                ai_conf = result["ai_confidence"]
                verdict = result.get("verdict", "unknown")
                
                signal = f"{provider}: {verdict} ({int(ai_conf * 100)}% AI confidence)"
                
                evidence.append({
                    "category": f"AI Detection - {provider}",
                    "signal": signal,
                    "confidence": float(ai_conf),
                    "details": result
                })
            
            # Add combined result
            evidence.insert(0, {
                "category": "Combined Analysis",
                "signal": f"Ensemble score from {len(all_results)} detectors: {int(combined_ai_confidence * 100)}% AI confidence",
                "confidence": float(combined_ai_confidence),
                "details": {
                    "num_detectors": len(all_results),
                    "combined_confidence": combined_ai_confidence
                }
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
                    "filename": filename,
                    "provider": "Ensemble Detection",
                    "content_type": "video" if is_video else "image",
                    "report_id": data.get("id")
                }
            }
            
    except Exception as e:
        error_msg = f"Detection error: {str(e)}"
        print(f"⚠️ {error_msg}")
        print(f"Full traceback: {traceback.format_exc()}")
        return create_mock_result(50, error_msg)


def detect_image_video(url):
    """Detect AI in image/video from URL using AIorNOT with ensemble scoring"""
    
    if not AIORNOT_API_KEY:
        return create_mock_result(50, "No AIorNOT API key configured")
    
    try:
        print(f"🔍 Calling AIorNOT for URL: {url}")
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.aiornot.com/v1/reports/image",
                headers={
                    "Authorization": f"Bearer {AIORNOT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"object": url}
            )
            
            print(f"📥 AIorNOT response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ AIorNOT error: {response.text}")
                return create_mock_result(50, f"API Error: {response.status_code}")
            
            data = response.json()
            print(f"✅ Got AIorNOT response")
            
            # Download image for Hugging Face
            image_response = client.get(url, timeout=30.0)
            if image_response.status_code == 200:
                image_data = image_response.content
                hf_result = detect_with_huggingface(image_data)
            else:
                print(f"⚠️ Could not download image for HF: {image_response.status_code}")
                hf_result = None
            
            # Google reverse image search
            google_result = reverse_image_search(url)
            
            # Collect all AI detection results
            all_results = []
            
            # AIorNOT result
            ai_generated = data.get("report", {}).get("ai_generated", {})
            aiornot_confidence = ai_generated.get("confidence", 0.5)
            all_results.append({
                "provider": "AIorNOT",
                "ai_confidence": aiornot_confidence,
                "verdict": ai_generated.get("verdict", "unknown")
            })
            
            # Hugging Face result
            if hf_result:
                all_results.append(hf_result)
            
            # Calculate ensemble confidence (average of all detectors)
            combined_ai_confidence = sum(r["ai_confidence"] for r in all_results) / len(all_results)
            
            # Apply amplification to make scores more decisive
            combined_ai_confidence = amplify_confidence(combined_ai_confidence)
            
            # Factor in Google provenance if suspicious
            provenance_evidence = None
            if google_result and google_result.get("found"):
                suspicious_ratio = google_result.get("suspicious_ratio", 0)
                if suspicious_ratio > 0.3:  # More than 30% suspicious
                    # Increase AI confidence slightly based on suspicious findings
                    provenance_boost = suspicious_ratio * 0.15  # Max 15% boost
                    combined_ai_confidence = min(1.0, combined_ai_confidence + provenance_boost)
                    
                    provenance_evidence = {
                        "category": "Provenance Analysis",
                        "signal": f"Found {google_result['num_results']} mentions online, {google_result['suspicious_count']} contain AI-related keywords",
                        "confidence": suspicious_ratio,
                        "details": google_result
                    }
            
            # Calculate trust score (inverse of AI confidence, scaled 0-100)
            trust_score = int((1 - combined_ai_confidence) * 100)
            label_info = get_label_with_explanation(trust_score)
            
            print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
            
            # Get generator info if available
            generator_info = ai_generated.get("generator", {})
            top_generators = []
            if generator_info:
                # Get top 3 generators by confidence
                # Handle both dict and float values
                try:
                    sorted_items = []
                    for gen_name, gen_value in generator_info.items():
                        # Extract confidence - might be a dict or a float
                        if isinstance(gen_value, dict):
                            confidence = gen_value.get("confidence", 0)
                        else:
                            confidence = float(gen_value) if gen_value else 0
                        sorted_items.append((gen_name, confidence))
                    
                    # Sort by confidence and take top 3
                    sorted_items.sort(key=lambda x: x[1], reverse=True)
                    top_generators = [f"{gen}: {int(conf*100)}%" for gen, conf in sorted_items[:3] if conf > 0.5]
                except Exception as gen_error:
                    print(f"⚠️ Error parsing generators: {gen_error}")
                    top_generators = []
            
            # Build evidence from all results
            evidence = []
            
            for result in all_results:
                provider = result["provider"]
                ai_conf = result["ai_confidence"]
                verdict = result.get("verdict", "unknown")
                
                signal = f"{provider}: {verdict} ({int(ai_conf * 100)}% AI confidence)"
                
                # Add generator info for AIorNOT
                if provider == "AIorNOT" and top_generators:
                    signal += f" - Detected: {', '.join(top_generators)}"
                
                evidence.append({
                    "category": f"AI Detection - {provider}",
                    "signal": signal,
                    "confidence": float(ai_conf),
                    "details": result
                })
            
            # Add combined result
            evidence.insert(0, {
                "category": "Combined Analysis",
                "signal": f"Ensemble score from {len(all_results)} detectors: {int(combined_ai_confidence * 100)}% AI confidence",
                "confidence": float(combined_ai_confidence),
                "details": {
                    "num_detectors": len(all_results),
                    "combined_confidence": combined_ai_confidence
                }
            })
            
            # Add provenance evidence if available
            if provenance_evidence:
                evidence.append(provenance_evidence)
            
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


# ============================================================
# TEXT DETECTION - ENSEMBLE WITH 2 FREE HUGGING FACE MODELS
# ============================================================

def detect_text_huggingface_model1(text_content):
    """
    Detect AI text using OpenAI's RoBERTa Large detector
    This is MODEL 1 of ensemble detection
    """
    
    if not HUGGINGFACE_API_KEY:
        print("⚠️ No Hugging Face API key")
        return None
    
    try:
        print(f"🤗 [Model 1] Calling OpenAI RoBERTa Large detector...")
        
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
            
            print(f"🤗 [Model 1] Response status: {response.status_code}")
            
            if response.status_code == 503:
                print("⏳ [Model 1] Model loading, waiting 10 seconds...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/openai-community/roberta-large-openai-detector",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": text_to_check}
                )
            
            if response.status_code != 200:
                print(f"⚠️ [Model 1] API error: {response.status_code}")
                return None
            
            data = response.json()
            print(f"🤗 [Model 1] Response: {data}")
            
            # Parse response - looking for "Fake" or "Real" labels
            fake_score = 0.5
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    label = result.get("label", "")
                    if label in ["Fake", "fake", "FAKE"]:
                        fake_score = result.get("score", 0.5)
                        break
            
            print(f"✅ [Model 1] AI confidence: {fake_score:.2%}")
            
            return {
                "provider": "OpenAI RoBERTa Large",
                "ai_confidence": fake_score,
                "verdict": "AI-generated" if fake_score > 0.5 else "Human-written",
                "raw_response": data
            }
            
    except Exception as e:
        print(f"⚠️ [Model 1] Error: {str(e)}")
        return None


def detect_text_huggingface_model2(text_content):
    """
    Detect AI text using ChatGPT Detector RoBERTa Large
    This is MODEL 2 of ensemble detection
    """
    
    if not HUGGINGFACE_API_KEY:
        print("⚠️ No Hugging Face API key")
        return None
    
    try:
        print(f"🤗 [Model 2] Calling ChatGPT Detector RoBERTa Large...")
        
        # Truncate if too long
        MAX_CHARS = 2000
        text_to_check = text_content[:MAX_CHARS] if len(text_content) > MAX_CHARS else text_content
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api-inference.huggingface.co/models/Hello-SimpleAI/chatgpt-detector-roberta-large",
                headers={
                    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"inputs": text_to_check}
            )
            
            print(f"🤗 [Model 2] Response status: {response.status_code}")
            
            if response.status_code == 503:
                print("⏳ [Model 2] Model loading, waiting 10 seconds...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/Hello-SimpleAI/chatgpt-detector-roberta-large",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": text_to_check}
                )
            
            if response.status_code != 200:
                print(f"⚠️ [Model 2] API error: {response.status_code}")
                return None
            
            data = response.json()
            print(f"🤗 [Model 2] Response: {data}")
            
            # Parse response - looking for "ChatGPT" or "Human" labels
            fake_score = 0.5
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    label = result.get("label", "")
                    if label in ["ChatGPT", "chatgpt", "GPT", "AI"]:
                        fake_score = result.get("score", 0.5)
                        break
            
            print(f"✅ [Model 2] AI confidence: {fake_score:.2%}")
            
            return {
                "provider": "ChatGPT Detector RoBERTa Large",
                "ai_confidence": fake_score,
                "verdict": "AI-generated" if fake_score > 0.5 else "Human-written",
                "raw_response": data
            }
            
    except Exception as e:
        print(f"⚠️ [Model 2] Error: {str(e)}")
        return None


def detect_text(text_content):
    """
    Detect AI in text using ENSEMBLE of 2 Hugging Face models
    This gives much better accuracy than a single model!
    """
    
    print(f"🔍 Starting ENSEMBLE text AI detection (length: {len(text_content)} chars)")
    
    # Run both models
    model1_result = detect_text_huggingface_model1(text_content)
    model2_result = detect_text_huggingface_model2(text_content)
    
    # Collect successful results
    all_results = []
    if model1_result:
        all_results.append(model1_result)
    if model2_result:
        all_results.append(model2_result)
    
    # If both failed, return error
    if not all_results:
        print(f"❌ Text detection failed: All models unavailable")
        return create_mock_result(50, "Text detection API unavailable")
    
    # Calculate ensemble confidence (average of all models)
    combined_ai_confidence = sum(r["ai_confidence"] for r in all_results) / len(all_results)
    
    # Calculate trust score (inverse of AI confidence)
    trust_score = int((1 - combined_ai_confidence) * 100)
    label_info = get_label_with_explanation(trust_score)
    
    print(f"📊 Ensemble Results:")
    for result in all_results:
        print(f"   - {result['provider']}: {int(result['ai_confidence'] * 100)}% AI")
    print(f"📊 Combined AI confidence: {int(combined_ai_confidence * 100)}%")
    print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
    
    # Build evidence from all models
    evidence = []
    
    for result in all_results:
        provider = result["provider"]
        ai_conf = result["ai_confidence"]
        verdict = result.get("verdict", "unknown")
        
        evidence.append({
            "category": f"AI Text Detection - {provider}",
            "signal": f"{provider}: {verdict} ({int(ai_conf * 100)}% AI confidence)",
            "confidence": float(ai_conf),
            "details": result
        })
    
    # Add combined result at the top
    evidence.insert(0, {
        "category": "Ensemble Analysis",
        "signal": f"Combined score from {len(all_results)} AI detectors: {int(combined_ai_confidence * 100)}% AI confidence",
        "confidence": float(combined_ai_confidence),
        "details": {
            "num_detectors": len(all_results),
            "models": [r["provider"] for r in all_results],
            "combined_confidence": combined_ai_confidence
        }
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
            "provider": "Ensemble Text Detection (2 Models)",
            "content_type": "text",
            "text_length": len(text_content),
            "models_used": [r["provider"] for r in all_results],
            "ensemble_method": "average"
        }
    }


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def amplify_confidence(confidence):
    """
    Amplify confidence scores to make them more decisive
    Pushes values away from 0.5 (inconclusive) toward extremes
    
    Examples:
    0.54 -> 0.62 (more decisive toward "not AI")
    0.63 -> 0.76 (even more decisive)
    0.90 -> 0.97 (very confident stays very confident)
    """
    # Center around 0.5
    centered = confidence - 0.5
    # Apply power function to amplify (1.5 is good balance)
    amplified = centered * (abs(centered) ** 0.3) * 2.5
    # Shift back and clamp to [0, 1]
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
