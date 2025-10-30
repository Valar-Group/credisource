"""
RapidAPI Social Media Video Downloader Integration
Handles downloads from YouTube, Instagram, Facebook, TikTok, etc.
"""

import os
import httpx
import tempfile
from typing import Dict, Optional

RAPID_API_KEY = os.getenv("RAPID_API_SOCIAL_VIDEO_DOWNLOADER")
RAPID_API_HOST = os.getenv("RAPID_API_HOST", "social-media-video-downloader.p.rapidapi.com")


async def download_with_rapidapi(url: str, platform: str = "auto") -> Dict:
    """
    Download video from social media using RapidAPI
    
    Args:
        url: Social media URL (YouTube, Instagram, Facebook, TikTok, etc.)
        platform: Platform name (auto-detect if not specified)
    
    Returns:
        Dict with download_url and metadata
    """
    
    print(f"🌐 Attempting RapidAPI download for: {url}")
    
    if not RAPID_API_KEY:
        print("❌ RAPID_API_KEY not configured")
        return {"success": False, "error": "RapidAPI key not configured"}
    
    # Auto-detect platform if not specified
    if platform == "auto":
        platform = detect_platform(url)
        print(f"   Detected platform: {platform}")
    
    try:
        # Map platform to RapidAPI endpoint
        endpoint = get_rapidapi_endpoint(platform, url)
        
        headers = {
            "x-rapidapi-key": RAPID_API_KEY,
            "x-rapidapi-host": RAPID_API_HOST
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"   Calling RapidAPI: {endpoint}")
            response = await client.get(endpoint, headers=headers)
            
            if response.status_code != 200:
                print(f"   ❌ RapidAPI error: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return {
                    "success": False,
                    "error": f"RapidAPI returned {response.status_code}"
                }
            
            data = response.json()
            print(f"   ✅ RapidAPI success!")
            
            # Extract download URL from response
            download_url = extract_download_url(data, platform)
            
            if not download_url:
                print(f"   ❌ Could not extract download URL from response")
                return {
                    "success": False,
                    "error": "No download URL in response"
                }
            
            # Download the video file
            print(f"   📥 Downloading video from: {download_url[:50]}...")
            video_path = await download_video_file(download_url)
            
            if not video_path:
                return {
                    "success": False,
                    "error": "Failed to download video file"
                }
            
            print(f"   ✅ Video saved to: {video_path}")
            
            return {
                "success": True,
                "video_path": video_path,
                "platform": platform,
                "metadata": data
            }
    
    except Exception as e:
        print(f"   ❌ RapidAPI download failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


def detect_platform(url: str) -> str:
    """Detect which platform the URL is from"""
    url_lower = url.lower()
    
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "instagram.com" in url_lower:
        return "instagram"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "linkedin.com" in url_lower:
        return "linkedin"
    elif "pinterest.com" in url_lower:
        return "pinterest"
    else:
        return "unknown"


def get_rapidapi_endpoint(platform: str, url: str) -> str:
    """
    Get the appropriate RapidAPI endpoint for the platform
    
    Note: Check the actual API documentation for correct endpoints
    These are example endpoints - adjust based on the actual API
    """
    
    base_url = f"https://{RAPID_API_HOST}"
    
    # URL encode the video URL
    from urllib.parse import quote
    encoded_url = quote(url, safe='')
    
    # Map platforms to their endpoints
    # NOTE: These may need adjustment based on actual API docs
    endpoints = {
        "youtube": f"{base_url}/youtube/video?url={encoded_url}",
        "instagram": f"{base_url}/instagram?url={encoded_url}",
        "facebook": f"{base_url}/facebook?url={encoded_url}",
        "tiktok": f"{base_url}/tiktok?url={encoded_url}",
        "twitter": f"{base_url}/twitter?url={encoded_url}",
        "linkedin": f"{base_url}/linkedin?url={encoded_url}",
        "pinterest": f"{base_url}/pinterest?url={encoded_url}",
    }
    
    return endpoints.get(platform, f"{base_url}/download?url={encoded_url}")


def extract_download_url(data: Dict, platform: str) -> Optional[str]:
    """
    Extract the actual video download URL from API response
    
    Note: Response format varies by API - adjust as needed
    Common patterns:
    - data['url']
    - data['download_url']
    - data['video_url']
    - data['media'][0]['url']
    """
    
    # Try common response patterns
    possible_keys = [
        'url',
        'download_url',
        'video_url',
        'downloadUrl',
        'videoUrl',
        'link',
        'file',
        'media_url'
    ]
    
    for key in possible_keys:
        if key in data:
            return data[key]
    
    # Try nested structures
    if 'data' in data:
        for key in possible_keys:
            if key in data['data']:
                return data['data'][key]
    
    if 'media' in data and isinstance(data['media'], list) and len(data['media']) > 0:
        return data['media'][0].get('url')
    
    if 'videos' in data and isinstance(data['videos'], list) and len(data['videos']) > 0:
        return data['videos'][0].get('url')
    
    # If we can't find it, return None
    print(f"   ⚠️ Could not find download URL in response keys: {list(data.keys())}")
    return None


async def download_video_file(download_url: str) -> Optional[str]:
    """
    Download the actual video file from the URL
    
    Returns:
        Path to downloaded file, or None if failed
    """
    
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(download_url)
            
            if response.status_code != 200:
                print(f"   ❌ Download failed: {response.status_code}")
                return None
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
                f.write(response.content)
                return f.name
    
    except Exception as e:
        print(f"   ❌ Video download error: {e}")
        return None


# Synchronous wrapper for use in Celery tasks
def download_with_rapidapi_sync(url: str, platform: str = "auto") -> Dict:
    """Synchronous wrapper for Celery"""
    import asyncio
    
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(download_with_rapidapi(url, platform))
        return result
    finally:
        loop.close()
