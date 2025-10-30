"""
RapidAPI Social Media Video Downloader Integration
Handles downloads from YouTube, Instagram, Facebook, TikTok, etc.
"""
print("🔄 RAPIDAPI DOWNLOADER MODULE LOADED - VERSION 2.0") 

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
    Based on actual API documentation from RapidAPI playground
    """
    
    base_url = f"https://{RAPID_API_HOST}"
    
    # URL encode the video URL
    from urllib.parse import quote
    encoded_url = quote(url, safe='')
    
    # Extract video ID for YouTube
    if platform == "youtube":
        # Extract video ID from various YouTube URL formats
        video_id = extract_youtube_id(url)
        if video_id:
            return f"{base_url}/youtube/v3/video/details?videoId={video_id}&renderableFormats=720p,highres&urlAccess=proxied&getTranscript=false"
    
    # Map platforms to their endpoints (based on actual API)
    endpoints = {
        "instagram": f"{base_url}/instagram/v3/media/details?url={encoded_url}",
        "facebook": f"{base_url}/facebook/v3/post/details?url={encoded_url}&renderableFormats=720p,highres",
        "tiktok": f"{base_url}/tiktok/v3/post/details?url={encoded_url}",
        "twitter": f"{base_url}/twitter/v3/post/details?url={encoded_url}",
    }
    
    return endpoints.get(platform, f"{base_url}/smvd/get/all?url={encoded_url}")


def extract_youtube_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    """
    import re
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def extract_download_url(data: Dict, platform: str) -> Optional[str]:
    """
    Extract the actual video download URL from API response
    
    The v3 API returns data in various structures depending on platform
    """
    
    print(f"   📋 Parsing API response for {platform}...")
    
    # Check for 'contents' key (YouTube v3 API format)
    if 'contents' in data:
        contents = data['contents']
        
        # Contents might have formats or videos array
        if isinstance(contents, dict):
            # Look for formats
            if 'formats' in contents and isinstance(contents['formats'], list):
                formats = contents['formats']
                if len(formats) > 0 and 'url' in formats[0]:
                    print(f"   ✅ Found download URL in contents.formats[0]")
                    return formats[0]['url']
            
            # Look for videos
            if 'videos' in contents and isinstance(contents['videos'], list):
                videos = contents['videos']
                if len(videos) > 0 and 'url' in videos[0]:
                    print(f"   ✅ Found download URL in contents.videos[0]")
                    return videos[0]['url']
            
            # Check direct URL in contents
            if 'url' in contents:
                print(f"   ✅ Found download URL in contents.url")
                return contents['url']
            
            # Log contents structure for debugging
            print(f"   🔍 contents keys: {list(contents.keys())}")
    
    # v3 API format - look for formats array in data
    if 'data' in data and 'formats' in data['data']:
        formats = data['data']['formats']
        if isinstance(formats, list) and len(formats) > 0:
            # Get the first available format
            first_format = formats[0]
            if 'url' in first_format:
                print(f"   ✅ Found download URL in data.formats[0]")
                return first_format['url']
    
    # Fallback: Try common response patterns
    possible_keys = [
        'url',
        'download_url',
        'video_url',
        'downloadUrl',
        'videoUrl',
        'link',
        'file',
        'media_url',
        'downloadLink'
    ]
    
    # Check top level
    for key in possible_keys:
        if key in data:
            print(f"   ✅ Found download URL at top level: {key}")
            return data[key]
    
    # Check nested in 'data'
    if 'data' in data:
        for key in possible_keys:
            if key in data['data']:
                print(f"   ✅ Found download URL in data.{key}")
                return data['data'][key]
    
    # Check media array
    if 'media' in data and isinstance(data['media'], list) and len(data['media']) > 0:
        media_url = data['media'][0].get('url')
        if media_url:
            print(f"   ✅ Found download URL in media[0]")
            return media_url
    
    # Check videos array  
    if 'videos' in data and isinstance(data['videos'], list) and len(data['videos']) > 0:
        video_url = data['videos'][0].get('url')
        if video_url:
            print(f"   ✅ Found download URL in videos[0]")
            return video_url
    
    # If we can't find it, log the response structure
    print(f"   ⚠️ Could not find download URL in response")
    print(f"   Response keys: {list(data.keys())}")
    if 'data' in data:
        print(f"   data keys: {list(data['data'].keys())}")
    if 'contents' in data and isinstance(data['contents'], dict):
        print(f"   contents keys: {list(data['contents'].keys())}")
    
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
