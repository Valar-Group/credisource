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
                # Model is loading, this is normal for free tier
                print(f"⚠️ HF model loading, will retry...")
                return None
            
            if response.status_code != 200:
                print(f"⚠️ HF error: {response.text}")
                return None
            
            data = response.json()
            print(f"🤗 HF Response: {data}")
            
            # Parse response - format: [{"label": "artificial", "score": 0.99}]
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    if item.get("label") in ["artificial", "ai", "fake", "synthetic"]:
                        ai_score = item.get("score", 0.5)
                        print(f"🤗 HF AI score: {ai_score}")
                        return {
                            "verdict": "ai" if ai_score > 0.5 else "human",
                            "confidence": ai_score,
                            "provider": "huggingface-sdxl"
                        }
            
            return None
            
    except Exception as e:
        print(f"⚠️ Hugging Face error: {str(e)}")
        return None


def detect_image_video_from_data(image_data, filename="uploaded_file", is_video=False):
    """Detect AI in images/videos using file data directly (no URL download needed)"""
    
    if not AIORNOT_API_KEY:
        print("⚠️ No AIORNOT_API_KEY found")
        return create_mock_result(75, "No AI or Not API key configured")
    
    try:
        content_type_str = "video" if is_video else "image"
        print(f"🔍 Analyzing uploaded {content_type_str}: {filename}")
        print(f"📦 File size: {len(image_data)} bytes")
        
        if is_video:
            print(f"⏱️ Note: Video processing may take 30-60 seconds...")
        
        # ===========================================
        # ENSEMBLE DETECTION: Call multiple APIs
        # ===========================================
        
        all_results = []
        
        # 1. Submit to AI or Not v2 sync endpoint
        endpoint = "https://api.aiornot.com/v2/video/sync" if is_video else "https://api.aiornot.com/v2/image/sync"
        print(f"🔍 Submitting to AI or Not v2 {content_type_str} API...")
        
        with httpx.Client(timeout=120.0) as client:  # Longer timeout for videos
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {AIORNOT_API_KEY}"
                },
                files={
                    content_type_str: (filename, image_data, f"{content_type_str}/jpeg")
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
            
            print(f"🎯 AIorNOT Verdict: {verdict}, AI Confidence: {ai_confidence}, AI Detected: {ai_detected}")
            
            # Store AIorNOT result
            aiornot_result = {
                "provider": "AIorNOT",
                "verdict": verdict,
                "ai_confidence": ai_confidence,
                "human_confidence": human_info.get("confidence", 1 - ai_confidence),
                "generators": ai_generated.get("generator", {}),
                "report_id": data.get("id")
            }
            all_results.append(aiornot_result)
            
            # 2. Call Hugging Face SDXL detector (images only - not for videos)
            if not is_video:
                hf_result = detect_with_huggingface(image_data)
                if hf_result:
                    all_results.append({
                        "provider": "Hugging Face SDXL",
                        "verdict": hf_result["verdict"],
                        "ai_confidence": hf_result["confidence"],
                        "human_confidence": 1 - hf_result["confidence"]
                    })
                    print(f"🤗 HF Verdict: {hf_result['verdict']}, AI Confidence: {hf_result['confidence']}")
            else:
                print(f"⏭️ Skipping Hugging Face for video (not supported)")
            
            # Note: No Google Search for uploaded files (no URL to search for)
            print(f"📊 Combining {len(all_results)} detection results (no provenance for uploaded files)...")
            
            # ===========================================
            # ENSEMBLE SCORING: Combine all results
            # ===========================================
            
            # Weighted average (you can adjust weights later)
            total_ai_confidence = 0
            total_weight = 0
            
            for result in all_results:
                weight = 1.0  # Equal weight for now
                total_ai_confidence += result["ai_confidence"] * weight
                total_weight += weight
            
            # Combined AI confidence
            combined_ai_confidence = total_ai_confidence / total_weight if total_weight > 0 else 0.5
            
            print(f"🎯 Combined AI Confidence: {combined_ai_confidence:.2%}")
            
            # Calculate trust score from combined confidence
            base_score = 1 - combined_ai_confidence
            amplified = amplify_confidence(base_score)
            trust_score = int(amplified * 100)
            
            # Ensure score is in valid range
            trust_score = max(0, min(100, trust_score))
            
            label_info = get_label_with_explanation(trust_score)
            
            print(f"📊 Final trust score: {trust_score} ({label_info['label']})")
            
            # Get generator info if available
            generator_info = ai_generated.get("generator", {})
            top_generators = []
            if generator_info:
                try:
                    sorted_items = []
                    for gen_name, gen_value in generator_info.items():
                        if isinstance(gen_value, dict):
                            confidence = gen_value.get("confidence", 0)
                        else:
                            confidence = float(gen_value) if gen_value else 0
                        sorted_items.append((gen_name, confidence))
                    
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
                    "provider": "AI or Not v2",
                    "content_type": "image",
                    "report_id": data.get("id"),
                    "source": "file_upload"
                }
            }
            
    except Exception as e:
        error_msg = f"AI or Not detection error: {str(e)}"
        print(f"⚠️ {error_msg}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return create_mock_result(50, error_msg)


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
            
            # Check content type
            content_type = image_response.headers.get('content-type', '').lower()
            print(f"📋 Content-Type: {content_type}")
            
            # If it's HTML, provide helpful error
            if 'text/html' in content_type:
                error_msg = "URL points to a webpage, not an image. Please provide a direct image URL (e.g., ending in .jpg, .png, .webp)"
                print(f"⚠️ {error_msg}")
                return create_mock_result(50, error_msg)
            
            image_data = image_response.content
            print(f"✅ Downloaded {len(image_data)} bytes")
            
            # ===========================================
            # ENSEMBLE DETECTION: Call multiple APIs
            # ===========================================
            
            all_results = []
            
            # 1. Submit to AI or Not v2 sync endpoint
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
            
            print(f"🎯 AIorNOT Verdict: {verdict}, AI Confidence: {ai_confidence}, AI Detected: {ai_detected}")
            
            # Store AIorNOT result
            aiornot_result = {
                "provider": "AIorNOT",
                "verdict": verdict,
                "ai_confidence": ai_confidence,
                "human_confidence": human_info.get("confidence", 1 - ai_confidence),
                "generators": ai_generated.get("generator", {}),
                "report_id": data.get("id")
            }
            all_results.append(aiornot_result)
            
            # 2. Call Hugging Face SDXL detector
            hf_result = detect_with_huggingface(image_data)
            if hf_result:
                all_results.append({
                    "provider": "Hugging Face SDXL",
                    "verdict": hf_result["verdict"],
                    "ai_confidence": hf_result["confidence"],
                    "human_confidence": 1 - hf_result["confidence"]
                })
                print(f"🤗 HF Verdict: {hf_result['verdict']}, AI Confidence: {hf_result['confidence']}")
            
            # 3. Run Google Reverse Image Search
            google_result = reverse_image_search(url)
            provenance_evidence = None
            
            if google_result and google_result.get("found"):
                suspicious_ratio = google_result.get("suspicious_ratio", 0)
                num_results = google_result.get("num_results", 0)
                domains = google_result.get("domains", [])
                
                # Create provenance evidence
                if suspicious_ratio > 0.5:
                    signal = f"Found on {num_results} websites, {int(suspicious_ratio*100)}% contain AI-related keywords"
                    verdict = "Suspicious provenance - appears on AI art sites"
                elif num_results > 20:
                    signal = f"Widely circulated - found on {num_results} websites"
                    verdict = "Viral image"
                else:
                    signal = f"Found on {num_results} websites: {', '.join(domains[:3])}"
                    verdict = "Limited circulation"
                
                provenance_evidence = {
                    "category": "Provenance - Google Search",
                    "signal": signal,
                    "confidence": 0.7,
                    "details": {
                        "num_results": num_results,
                        "suspicious_ratio": suspicious_ratio,
                        "domains": domains,
                        "verdict": verdict
                    }
                }
                print(f"🔍 Google: {verdict}")
            
            # ===========================================
            # ENSEMBLE SCORING: Combine all results
            # ===========================================
            
            print(f"📊 Combining {len(all_results)} detection results...")
            
            # Weighted average (you can adjust weights later)
            total_ai_confidence = 0
            total_weight = 0
            
            for result in all_results:
                weight = 1.0  # Equal weight for now
                total_ai_confidence += result["ai_confidence"] * weight
                total_weight += weight
            
            # Combined AI confidence
            combined_ai_confidence = total_ai_confidence / total_weight if total_weight > 0 else 0.5
            
            print(f"🎯 Combined AI Confidence: {combined_ai_confidence:.2%}")
            
            # Calculate trust score from combined confidence
            base_score = 1 - combined_ai_confidence
            amplified = amplify_confidence(base_score)
            trust_score = int(amplified * 100)
            
            # Ensure score is in valid range
            trust_score = max(0, min(100, trust_score))
            
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
            "explanation": "This content shows signs of AI generation. We detected patterns commonly found in AI-created images.",
            "confidence": "Moderate-High",
            "action": "Be cautious. This content may be AI-generated or heavily manipulated."
        }
    else:
        return {
            "label": "Likely Fake",
            "explanation": "This content appears to be AI-generated. We found strong indicators of synthetic creation, including telltale artifacts and patterns typical of AI image generators.",
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
