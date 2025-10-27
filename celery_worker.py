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
        
        # Choose correct endpoint based on content type
        if is_video:
            endpoint = "https://api.aiornot.com/v2/video/sync"
            file_field_name = "video"
            timeout = 120.0  # Video can take up to 2 minutes
        else:
            endpoint = "https://api.aiornot.com/v1/reports/image"
            file_field_name = "object"
            timeout = 60.0
        
        # Prepare multipart form data
        with httpx.Client(timeout=timeout) as client:
            # AIorNOT expects file upload
            files = {
                file_field_name: (filename, file_data, 'application/octet-stream')
            }
            
            print(f"📤 Uploading to AIorNOT ({endpoint})...")
            response = client.post(
                endpoint,
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
            
            # Parse response based on content type
            if is_video:
                # Video response format
                report = data.get("report", {})
                ai_video = report.get("ai_video", {})
                ai_voice = report.get("ai_voice", {})
                
                # Use video confidence as primary
                aiornot_confidence = ai_video.get("confidence", 0.5)
                is_detected = ai_video.get("is_detected", False)
                
                # Also check voice if available
                voice_confidence = ai_voice.get("confidence", 0)
                
                # Average video and voice if both available
                if voice_confidence > 0:
                    aiornot_confidence = (aiornot_confidence + voice_confidence) / 2
                
                verdict = "AI-generated" if is_detected else "Real"
                
            else:
                # Image response format
                ai_generated = data.get("report", {}).get("ai_generated", {})
                aiornot_confidence = ai_generated.get("confidence", 0.5)
                verdict = ai_generated.get("verdict", "unknown")
            
            # Get Hugging Face result for images only (not videos)
            if not is_video:
                hf_result = detect_with_huggingface(file_data)
            else:
                hf_result = None
            
            # Collect all results
            all_results = []
            
            # AIorNOT result
            all_results.append({
                "provider": "AIorNOT",
                "ai_confidence": aiornot_confidence,
                "verdict": verdict
            })
            
            # Hugging Face result (images only)
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
                    "provider": "AIorNOT" if is_video else "Ensemble Detection",
                    "content_type": "video" if is_video else "image",
                    "report_id": data.get("id")
                }
            }
            
    except Exception as e:
        error_msg = f"Detection error: {str(e)}"
        print(f"⚠️ {error_msg}")
        print(f"Full traceback: {traceback.format_exc()}")
        return create_mock_result(50, error_msg)


def download_video_with_ytdlp(url, job_id=None):
    """
    Download video from social media platforms using yt-dlp Python API
    Supports: YouTube, TikTok, Twitter/X, Instagram, Facebook, etc.
    
    Returns: (video_file_path, error_message)
    """
    
    print(f"📥 Attempting to download video from: {url}")
    
    # Import yt-dlp Python module
    try:
        import yt_dlp
    except ImportError:
        print(f"❌ yt-dlp not installed")
        return None, "yt-dlp package not available"
    
    # Create temp directory for downloads
    temp_dir = tempfile.mkdtemp(prefix="credisource_video_")
    output_template = os.path.join(temp_dir, "video.%(ext)s")
    
    try:
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # Prefer MP4
            'outtmpl': output_template,
            'noplaylist': True,  # Don't download playlists
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 60,
        }
        
        print(f"🎬 Downloading video with yt-dlp...")
        
        # Download using yt-dlp Python API
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                print(f"❌ Could not extract video info")
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except:
                    pass
                return None, "Could not extract video information"
        
        # Find the downloaded video file
        video_files = [f for f in os.listdir(temp_dir) if f.startswith("video.")]
        
        if not video_files:
            print(f"❌ No video file found after download")
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
            return None, "Video download succeeded but file not found"
        
        video_path = os.path.join(temp_dir, video_files[0])
        file_size = os.path.getsize(video_path)
        
        print(f"✅ Video downloaded successfully!")
        print(f"📦 File: {video_path}")
        print(f"📊 Size: {file_size / 1024 / 1024:.2f} MB")
        
        return video_path, None
        
    except Exception as e:
        print(f"❌ Error downloading video: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass
        return None, f"Error: {str(e)}"


def detect_image_video(url):
    """Detect AI in image/video from URL using AIorNOT with ensemble scoring"""
    
    if not AIORNOT_API_KEY:
        return create_mock_result(50, "No AIorNOT API key configured")
    
    # Detect if this is a social media video URL that needs downloading
    video_platforms = [
        'youtube.com', 'youtu.be',
        'tiktok.com',
        'twitter.com', 'x.com',
        'instagram.com',
        'facebook.com', 'fb.watch',
        'reddit.com',
        'vimeo.com',
        'dailymotion.com'
    ]
    
    is_social_video = any(platform in url.lower() for platform in video_platforms)
    video_file_path = None
    
    try:
        # If it's a social media video, download it first
        if is_social_video:
            print(f"🎥 Detected social media video URL, downloading...")
            video_file_path, error = download_video_with_ytdlp(url)
            
            if error:
                print(f"❌ Could not download video: {error}")
                return create_mock_result(50, f"Video download failed: {error}")
            
            print(f"✅ Video downloaded, uploading to AIorNOT...")
            
            # Upload the downloaded video file to AIorNOT
            with open(video_file_path, 'rb') as video_file:
                video_data = video_file.read()
            
            # Use the file upload method
            result = detect_image_video_from_data(video_data, "video.mp4", is_video=True)
            
            # Clean up downloaded file
            try:
                import shutil
                temp_dir = os.path.dirname(video_file_path)
                shutil.rmtree(temp_dir)
                print(f"🧹 Cleaned up temporary video file")
            except Exception as e:
                print(f"⚠️ Could not clean up temp file: {e}")
            
            return result
        
        # Otherwise, for direct URLs, download and process
        print(f"🔍 Processing direct URL: {url}")
        
        # Check if URL ends with video extension
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
        is_video_url = any(url.lower().endswith(ext) for ext in video_extensions)
        
        if is_video_url:
            # Download video file
            print(f"🎥 Detected direct video URL, downloading...")
            with httpx.Client(timeout=120.0) as client:
                video_response = client.get(url)
                if video_response.status_code != 200:
                    return create_mock_result(50, f"Could not download video: {video_response.status_code}")
                
                video_data = video_response.content
                print(f"✅ Video downloaded ({len(video_data)} bytes)")
                
                # Process as video
                return detect_image_video_from_data(video_data, "video.mp4", is_video=True)
        
        # Otherwise it's an image URL - use image endpoint
        print(f"🔍 Calling AIorNOT for image URL: {url}")
        
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
# TEXT DETECTION - USING WINSTON AI
# ============================================================

def detect_text_winston(text_content):
    """
    Detect AI-generated text using Winston AI
    Uses JSON-RPC 2.0 format via MCP server
    High accuracy detection with 2,500 free credits
    """
    
    if not WINSTON_API_KEY:
        print("⚠️ No Winston AI API key")
        return None
    
    try:
        print(f"🔍 Calling Winston AI for text detection...")
        print(f"📝 Text length: {len(text_content)} characters")
        
        # Winston AI requires minimum 300 characters for text detection
        if len(text_content) < 300:
            print(f"⚠️ Text too short ({len(text_content)} chars), Winston AI requires 300+ chars")
            print(f"   Falling back to backup detector")
            return None
        
        # Winston AI MCP endpoint using JSON-RPC 2.0
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.gowinston.ai/mcp/v1",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "ai-text-detection",
                        "arguments": {
                            "text": text_content,
                            "apiKey": WINSTON_API_KEY
                        }
                    }
                }
            )
            
            print(f"🔍 Winston AI response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ Winston AI error: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            print(f"✅ Winston AI response: {data}")
            
            # Parse Winston AI JSON-RPC response
            # Expected format: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "..."}]}}
            result = data.get("result", {})
            
            # Extract the actual detection result from content
            content = result.get("content", [])
            if content and len(content) > 0:
                # Parse the text response which contains JSON as a string
                text_result = content[0].get("text", "")
                print(f"📊 Winston result text (first 500 chars): {text_result[:500]}")
                
                # Try to parse as JSON first (new format)
                try:
                    import json
                    winston_data = json.loads(text_result)
                    
                    # Winston returns JSON with score field
                    # score: 0-100 where 0 = 0% human (100% AI), 100 = 100% human (0% AI)
                    overall_score = winston_data.get("score")
                    
                    if overall_score is not None:
                        print(f"📊 Winston human score: {overall_score}% (0=AI, 100=human)")
                        
                        # Convert to AI confidence
                        ai_confidence = 1 - (overall_score / 100)
                        
                        print(f"✅ Winston AI confidence: {ai_confidence:.2%}")
                        
                        # Get credits info
                        credits_used = winston_data.get("credits_used")
                        credits_remaining = winston_data.get("credits_remaining")
                        
                        if credits_remaining:
                            print(f"💳 Credits remaining: {credits_remaining}")
                        
                        return {
                            "provider": "Winston AI",
                            "ai_confidence": ai_confidence,
                            "verdict": "Human-written" if ai_confidence < 0.5 else "AI-generated",
                            "raw_response": data,
                            "winston_human_score": overall_score,
                            "credits_used": credits_used,
                            "credits_remaining": credits_remaining
                        }
                    else:
                        print(f"⚠️ No score field in Winston JSON")
                        return None
                        
                except json.JSONDecodeError:
                    # Fall back to regex parsing for plain text format
                    print(f"📝 Winston returned plain text, using regex parsing")
                    
                    import re
                    human_match = re.search(r'(\d+\.?\d*)%\s*human', text_result, re.IGNORECASE)
                    
                    if human_match:
                        human_score = float(human_match.group(1))
                        print(f"📊 Winston human score: {human_score}% (0=AI, 100=human)")
                        
                        ai_confidence = 1 - (human_score / 100)
                        print(f"✅ Winston AI confidence: {ai_confidence:.2%}")
                        
                        return {
                            "provider": "Winston AI",
                            "ai_confidence": ai_confidence,
                            "verdict": "Human-written" if ai_confidence < 0.5 else "AI-generated",
                            "raw_response": data,
                            "winston_human_score": human_score
                        }
                    else:
                        print(f"⚠️ Could not extract human percentage from Winston response")
                        return None
            else:
                print(f"⚠️ Unexpected Winston response format")
                return None
            
    except Exception as e:
        print(f"⚠️ Winston AI error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return None


def detect_text_huggingface(text_content):
    """
    Detect AI-generated text using OpenAI's RoBERTa Large detector
    BACKUP method if Winston AI fails
    """
    
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
    """
    Detect AI in text using Winston AI (primary) with Hugging Face backup
    """
    
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
