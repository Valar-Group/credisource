"""
CrediSource Celery Worker - Enhanced with Phase 2 Safeguards
Processes background verification jobs for images, videos, text, and news

UPDATES (October 28, 2025):
- Added 70+ news sources (from 50)
- Phase 2 safeguards: Domain age, SSL check, suspicious patterns
- Smart cross-reference with story type detection
- Satire site instant detection
- Fake news site flagging
"""

import os
import json
import time
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlparse, quote_plus
import re
import ssl
import socket

from celery import Celery
import redis

import httpx
import traceback
import base64

# API Keys
SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER", "")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET", "")
AIORNOT_API_KEY = os.getenv("AIORNOT_API_KEY", "")
WINSTON_API_KEY = os.getenv("WINSTON_API_KEY", "")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")

# ↓ THEN YOUR EXISTING CODE CONTINUES
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ============================================================================
# CONFIGURATION
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Initialize Celery
app = Celery('credisource', broker=REDIS_URL, backend=REDIS_URL)
redis_client = redis.from_url(REDIS_URL)

# ============================================================================
# TASK ROUTING - ADD THIS RIGHT AFTER "redis_client = redis.from_url(REDIS_URL)"
# This routes API calls to the correct verification function
# ============================================================================

@app.task(name='credisource.verify_content', bind=True)
def verify_content(self, job_id: str, url_or_text: str, content_type: str) -> Dict:
    """
    Universal content verification task with SMART AUTO-DETECTION
    Routes to appropriate handler and auto-corrects user mistakes
    
    BEGINNER NOTE: This is like a "traffic cop" that receives all requests
    and sends them to the right verification function. It also detects when
    users paste article URLs but select "image" and automatically corrects it.
    """
    print(f"\n{'='*80}")
    print(f"📥 RECEIVED VERIFICATION REQUEST")
    print(f"{'='*80}")
    print(f"Job ID: {job_id}")
    print(f"Content Type (user selected): {content_type}")
    print(f"URL/Text: {url_or_text[:100]}...")
    print(f"{'='*80}\n")
    
    try:
        # SMART AUTO-DETECTION: Fix common user mistakes
        if content_type == "image":
            # Check if URL ends with image extension (strip query params first)
            url_without_params = url_or_text.split('?')[0].split('#')[0]
            is_image_url = url_without_params.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'))

            if not is_image_url:
                print("⚠️ AUTO-DETECT: User selected 'image' but URL doesn't have image extension")
                print(f"   URL: {url_or_text[:100]}")
                
                # Check if it looks like a webpage/article
                webpage_indicators = [
                    '://' in url_or_text,  # Has protocol (http/https)
                    '.com/' in url_or_text.lower(),
                    '.org/' in url_or_text.lower(),
                    '.net/' in url_or_text.lower(),
                    '.tv/' in url_or_text.lower(),
                    '.co.uk/' in url_or_text.lower(),
                    'news' in url_or_text.lower(),
                    'article' in url_or_text.lower(),
                    'post' in url_or_text.lower(),
                    'blog' in url_or_text.lower(),
                ]
                
                if any(webpage_indicators):
                    print("   ✅ AUTO-DETECTED: This looks like a news article/webpage")
                    print("   📰 Routing to NEWS verification instead of image")
                    print(f"{'='*80}\n")
                    return verify_news(url_or_text)
                else:
                    # Not an image URL and doesn't look like news either
                    return {
                        "trust_score": 0,
                        "label": "Invalid URL",
                        "verdict": "⚠️ This doesn't appear to be a direct image URL. Please either: (1) Select 'News' if this is an article, (2) Right-click the image and select 'Copy Image Address', or (3) Upload the image file directly.",
                        "error": "URL must end with .jpg, .png, .gif, etc. or be changed to 'News' type"
                    }
        
        # Normal routing (no auto-correction needed)
        if content_type == "news":
            return verify_news(url_or_text)
        elif content_type == "image":
            return verify_image_task(url_or_text)
        elif content_type == "video":
            return verify_video_task(url_or_text)
        elif content_type == "text":
            return verify_text_task(url_or_text)
        else:
            return {
                "trust_score": 0,
                "label": "Error",
                "verdict": f"Unknown content type: {content_type}",
                "error": f"Supported types: news, image, video, text"
            }

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}",
            "error": str(e)
        }

@app.task(name='credisource.verify_content_file', bind=True)
def verify_content_file(self, job_id: str, file_base64: str, filename: str, content_type: str) -> Dict:
    """
    Handle file uploads (images/videos encoded as base64)
    Decodes base64 data and passes to appropriate detector
    """
    print(f"\n{'='*80}")
    print(f"📤 RECEIVED FILE UPLOAD")
    print(f"{'='*80}")
    print(f"Job ID: {job_id}")
    print(f"Filename: {filename}")
    print(f"Content Type: {content_type}")
    print(f"File Size: {len(file_base64)} bytes (base64)")
    print(f"{'='*80}\n")
    
    try:
        # Decode base64 to bytes
        file_data = base64.b64decode(file_base64)
        print(f"✅ Decoded {len(file_data)} bytes")
        
        # Route to appropriate handler
        if content_type == "image":
            return verify_image_file(file_data, filename)
        elif content_type == "video":
            return verify_video_file(file_data, filename)
        elif content_type == "text":
            # For text files, decode as string
            text_content = file_data.decode('utf-8')
            return verify_text_task(text_content)
        else:
            return {
                "trust_score": 0,
                "label": "Error",
                "verdict": f"Unsupported file type: {content_type}"
            }
    
    except Exception as e:
        print(f"❌ File processing error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"File processing failed: {str(e)}",
            "error": str(e)
        }


# Continue with the rest of your celery_worker.py file...
# (All your Phase 2 functions, source database, etc.)

# ============================================================================
# PHASE 2 SAFEGUARDS - NEW FUNCTIONS
# ============================================================================

def check_domain_age(domain: str) -> Dict:
    """
    Check how old the domain is
    New domains (<6 months) are often used for fake news
    
    Returns:
        - age_days: Domain age in days (or None if unknown)
        - penalty: Points to deduct (0-20)
        - warning: Human-readable warning message
    """
    try:
        import whois
        
        w = whois.whois(domain)
        creation_date = w.creation_date
        
        if isinstance(creation_date, list):
            creation_date = creation_date[0]
        
        if creation_date:
            age_days = (datetime.now() - creation_date).days
            
            if age_days < 180:  # Less than 6 months
                return {
                    "age_days": age_days,
                    "penalty": 20,
                    "warning": f"Very new domain ({age_days} days old) - highly suspicious"
                }
            elif age_days < 365:  # Less than 1 year
                return {
                    "age_days": age_days,
                    "penalty": 10,
                    "warning": f"New domain ({age_days} days old) - somewhat suspicious"
                }
            else:
                return {
                    "age_days": age_days,
                    "penalty": 0,
                    "warning": None
                }
    except Exception as e:
        print(f"   Could not check domain age: {e}")
        pass
    
    return {"age_days": None, "penalty": 0, "warning": None}


def check_suspicious_domain_patterns(domain: str) -> Dict:
    """
    Check for red flag patterns in domain names
    Fake news sites often use specific patterns to appear legitimate
    
    Checks for:
    - Copycat domains (cnn-news.com, bbc-breaking.com)
    - Excessive hyphens
    - Numbers in domain
    - Suspicious TLDs (.tk, .ml, .ga, etc.)
    - Clickbait keywords (real, true, patriot, freedom)
    
    Returns:
        - red_flags: List of detected patterns
        - penalty: Total points to deduct (0-30 max)
    """
    red_flags = []
    penalty = 0
    
    # Pattern 1: Mimics real news sites
    fake_patterns = [
        "cnn-", "bbc-", "fox-", "news-", "msnbc-",
        "abcnews-", "cbsnews-", "reuters-", "ap-",
        "-news.com", "-times.com", "-post.com", "-herald.com"
    ]
    for pattern in fake_patterns:
        if pattern in domain.lower():
            red_flags.append(f"Domain mimics legitimate outlet (pattern: {pattern})")
            penalty += 15
            break
    
    # Pattern 2: Excessive hyphens (real sites rarely use 3+)
    hyphen_count = domain.count('-')
    if hyphen_count >= 3:
        red_flags.append(f"Excessive hyphens in domain ({hyphen_count} hyphens)")
        penalty += 10
    
    # Pattern 3: Numbers in domain (except year-based like cnn2024.com)
    domain_name = domain.split('.')[0]
    if any(char.isdigit() for char in domain_name):
        # Check if it's just a year (2024, 2025, etc.)
        if not re.search(r'20\d{2}$', domain_name):
            red_flags.append("Suspicious numbers in domain name")
            penalty += 5
    
    # Pattern 4: Unusual/free TLDs (commonly used by scammers)
    suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.pw', '.top', '.xyz']
    for tld in suspicious_tlds:
        if domain.endswith(tld):
            red_flags.append(f"Suspicious free top-level domain ({tld})")
            penalty += 15
            break
    
    # Pattern 5: Clickbait keywords in domain
    clickbait_words = ['real', 'true', 'patriot', 'freedom', 'truth', 'expose', 
                       'uncensored', 'insider', 'leaked', 'exclusive']
    domain_lower = domain.lower()
    for word in clickbait_words:
        if word in domain_lower:
            red_flags.append(f"Clickbait keyword in domain: '{word}'")
            penalty += 5
            break
    
    return {
        "red_flags": red_flags,
        "penalty": min(penalty, 30)  # Cap at 30 points max
    }


def check_ssl_certificate(domain: str) -> Dict:
    """
    Check SSL certificate validity and age
    Legitimate news sites always have valid, established SSL certificates
    
    Returns:
        - cert_age_days: Certificate age in days
        - penalty: Points to deduct (0-20)
        - warning: Human-readable warning
    """
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                
                # Check certificate age
                not_before = ssl.cert_time_to_seconds(cert['notBefore'])
                cert_age_days = (time.time() - not_before) / 86400
                
                # Very new SSL certificate = suspicious
                if cert_age_days < 30:
                    return {
                        "cert_age_days": int(cert_age_days),
                        "penalty": 15,
                        "warning": f"Very new SSL certificate ({int(cert_age_days)} days old)"
                    }
                
                return {
                    "cert_age_days": int(cert_age_days),
                    "penalty": 0,
                    "warning": None
                }
    except ssl.SSLError:
        return {
            "cert_age_days": None,
            "penalty": 20,
            "warning": "Invalid or self-signed SSL certificate"
        }
    except Exception as e:
        return {
            "cert_age_days": None,
            "penalty": 15,
            "warning": f"No valid SSL certificate"
        }


def advanced_unknown_source_check(domain: str, url: str) -> Dict:
    """
    PHASE 2: Comprehensive check for unknown sources
    Combines domain age, pattern detection, and SSL checks
    
    This is what catches random Facebook/Twitter fake news that our
    database doesn't know about!
    
    Returns:
        - score: Adjusted credibility score (0-100)
        - red_flags: List of all detected issues
        - penalty: Total points deducted
        - verdict: Summary of findings
    """
    
    print(f"🔍 Running Phase 2 advanced checks on unknown source: {domain}")
    
    checks = []
    total_penalty = 0
    
    # Check 1: Domain age
    print(f"   Checking domain age...")
    age_check = check_domain_age(domain)
    if age_check["penalty"] > 0:
        checks.append(age_check["warning"])
        total_penalty += age_check["penalty"]
        print(f"   ❌ Domain age issue: {age_check['warning']}")
    elif age_check["age_days"]:
        print(f"   ✅ Domain age OK: {age_check['age_days']} days old")
    
    # Check 2: Suspicious domain patterns
    print(f"   Checking domain patterns...")
    pattern_check = check_suspicious_domain_patterns(domain)
    if pattern_check["penalty"] > 0:
        checks.extend(pattern_check["red_flags"])
        total_penalty += pattern_check["penalty"]
        print(f"   ❌ Found {len(pattern_check['red_flags'])} suspicious patterns")
        for flag in pattern_check["red_flags"]:
            print(f"      • {flag}")
    else:
        print(f"   ✅ Domain patterns OK")
    
    # Check 3: SSL certificate
    print(f"   Checking SSL certificate...")
    ssl_check = check_ssl_certificate(domain)
    if ssl_check["penalty"] > 0:
        checks.append(ssl_check["warning"])
        total_penalty += ssl_check["penalty"]
        print(f"   ❌ SSL issue: {ssl_check['warning']}")
    elif ssl_check["cert_age_days"]:
        print(f"   ✅ SSL certificate OK: {ssl_check['cert_age_days']} days old")
    
    # Calculate adjusted score
    base_score = 35  # Unknown source baseline (already includes penalty)
    adjusted_score = max(0, base_score - total_penalty)
    
    print(f"   📊 Phase 2 Results:")
    print(f"      Base score: {base_score}/100")
    print(f"      Red flags found: {len(checks)}")
    print(f"      Total penalty: -{total_penalty} points")
    print(f"      Final adjusted score: {adjusted_score}/100")
    
    # Build verdict
    if len(checks) == 0:
        verdict = "Unknown source (no major red flags detected)"
    elif len(checks) == 1:
        verdict = f"Unknown source with 1 suspicious indicator"
    else:
        verdict = f"Unknown source with {len(checks)} suspicious indicators"
    
    return {
        "score": adjusted_score,
        "red_flags": checks,
        "penalty": total_penalty,
        "verdict": verdict
    }


# ============================================================================
# NEWS SOURCE DATABASE (70+ SOURCES)
# ============================================================================

SOURCE_CREDIBILITY = {
    # TIER 1: Wire Services & Public Broadcasters (90-100)
    "apnews.com": {"score": 95, "bias": "center", "tier": "tier1", "type": "wire"},
    "reuters.com": {"score": 95, "bias": "center", "tier": "tier1", "type": "wire"},
    "bbc.com": {"score": 95, "bias": "center-left", "tier": "tier1", "type": "public"},
    "bbc.co.uk": {"score": 95, "bias": "center-left", "tier": "tier1", "type": "public"},
    "npr.org": {"score": 90, "bias": "center-left", "tier": "tier1", "type": "public"},
    "pbs.org": {"score": 90, "bias": "center", "tier": "tier1", "type": "public"},
    "c-span.org": {"score": 95, "bias": "center", "tier": "tier1", "type": "public"},
    
    # TIER 2: Major National News (70-89)
    "nytimes.com": {"score": 85, "bias": "center-left", "tier": "tier2", "type": "national"},
    "washingtonpost.com": {"score": 85, "bias": "center-left", "tier": "tier2", "type": "national"},
    "wsj.com": {"score": 85, "bias": "center-right", "tier": "tier2", "type": "national"},
    "theguardian.com": {"score": 80, "bias": "center-left", "tier": "tier2", "type": "national"},
    "usatoday.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "national"},
    "cnn.com": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "broadcast"},
    "cbsnews.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "broadcast"},
    "nbcnews.com": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "broadcast"},
    "abcnews.go.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "broadcast"},
    
    # UK Sources (TIER 2)
    "news.sky.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "broadcast"},
    "independent.co.uk": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "national"},
    "telegraph.co.uk": {"score": 75, "bias": "center-right", "tier": "tier2", "type": "national"},
    "itv.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "broadcast"},
    "channel4.com": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "broadcast"},
    
    # Indian Sources (TIER 2)
    "thehindu.com": {"score": 80, "bias": "center-left", "tier": "tier2", "type": "national"},
    "hindustantimes.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "national"},
    "indianexpress.com": {"score": 80, "bias": "center", "tier": "tier2", "type": "national"},
    "indiatoday.in": {"score": 75, "bias": "center", "tier": "tier2", "type": "national"},
    "ndtv.com": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "broadcast"},
    "timesofindia.indiatimes.com": {"score": 70, "bias": "center", "tier": "tier2", "type": "national"},
    "news18.com": {"score": 70, "bias": "center-right", "tier": "tier2", "type": "broadcast"},
    "oneindia.com": {"score": 65, "bias": "center", "tier": "tier2", "type": "national"},
    "india.com": {"score": 65, "bias": "center", "tier": "tier2", "type": "national"},
    "rediff.com": {"score": 65, "bias": "center", "tier": "tier2", "type": "national"},
    
    # Australian Sources (TIER 2)
    "abc.net.au": {"score": 85, "bias": "center", "tier": "tier2", "type": "public"},
    "news.com.au": {"score": 70, "bias": "center-right", "tier": "tier2", "type": "national"},
    
    # Canadian Sources (TIER 2)
    "cbc.ca": {"score": 85, "bias": "center-left", "tier": "tier2", "type": "public"},
    "theglobeandmail.com": {"score": 80, "bias": "center", "tier": "tier2", "type": "national"},
    "thestar.com": {"score": 75, "bias": "center-left", "tier": "tier2", "type": "national"},
    
    # Business/Financial (TIER 2)
    "bloomberg.com": {"score": 85, "bias": "center", "tier": "tier2", "type": "business"},
    "forbes.com": {"score": 75, "bias": "center-right", "tier": "tier2", "type": "business"},
    "businessinsider.com": {"score": 70, "bias": "center", "tier": "tier2", "type": "business"},
    "cnbc.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "business"},
    "finance.yahoo.com": {"score": 70, "bias": "center", "tier": "tier2", "type": "business"},
    "livemint.com": {"score": 75, "bias": "center", "tier": "tier2", "type": "business"},
    
    # TIER 3: Regional & Tabloid News (40-69)
    "latimes.com": {"score": 75, "bias": "center-left", "tier": "tier3", "type": "regional"},
    "chicagotribune.com": {"score": 70, "bias": "center", "tier": "tier3", "type": "regional"},
    "sfchronicle.com": {"score": 70, "bias": "center-left", "tier": "tier3", "type": "regional"},
    "bostonglobe.com": {"score": 75, "bias": "center-left", "tier": "tier3", "type": "regional"},
    "newsweek.com": {"score": 65, "bias": "center", "tier": "tier3", "type": "magazine"},
    "time.com": {"score": 75, "bias": "center-left", "tier": "tier3", "type": "magazine"},
    "politico.com": {"score": 70, "bias": "center-left", "tier": "tier3", "type": "specialty"},
    "thehill.com": {"score": 70, "bias": "center", "tier": "tier3", "type": "specialty"},
    "axios.com": {"score": 75, "bias": "center", "tier": "tier3", "type": "digital"},
    "vox.com": {"score": 65, "bias": "left", "tier": "tier3", "type": "digital"},
    "buzzfeednews.com": {"score": 60, "bias": "center-left", "tier": "tier3", "type": "digital"},
    "huffpost.com": {"score": 55, "bias": "left", "tier": "tier3", "type": "digital"},
    "vice.com": {"score": 60, "bias": "left", "tier": "tier3", "type": "digital"},
    "foxnews.com": {"score": 60, "bias": "right", "tier": "tier3", "type": "broadcast"},
    "nypost.com": {"score": 50, "bias": "right", "tier": "tier3", "type": "tabloid"},
    "dailymail.co.uk": {"score": 45, "bias": "center-right", "tier": "tier3", "type": "tabloid"},
    "thesun.co.uk": {"score": 40, "bias": "center-right", "tier": "tier3", "type": "tabloid"},
    "mirror.co.uk": {"score": 40, "bias": "center-left", "tier": "tier3", "type": "tabloid"},
    
    # TIER 4: State Media & Unreliable (0-39)
    "rt.com": {"score": 20, "bias": "right", "tier": "tier4", "type": "state"},
    "sputniknews.com": {"score": 20, "bias": "right", "tier": "tier4", "type": "state"},
    "presstv.ir": {"score": 25, "bias": "left", "tier": "tier4", "type": "state"},
    "xinhuanet.com": {"score": 30, "bias": "left", "tier": "tier4", "type": "state"},
    "breitbart.com": {"score": 35, "bias": "far-right", "tier": "tier4", "type": "partisan"},
    "occupydemocrats.com": {"score": 30, "bias": "far-left", "tier": "tier4", "type": "partisan"},
    "naturalnews.com": {"score": 10, "bias": "far-right", "tier": "tier4", "type": "conspiracy"},
    "infowars.com": {"score": 10, "bias": "far-right", "tier": "tier4", "type": "conspiracy"},
    "beforeitsnews.com": {"score": 15, "bias": "mixed", "tier": "tier4", "type": "conspiracy"},
    
    # Known Fake News Sites (TIER 4 - Very Low Scores)
    "thepeoplesvoice.tv": {"score": 5, "bias": "far-right", "tier": "tier4", "type": "fake-news"},
    "newspunch.com": {"score": 5, "bias": "far-right", "tier": "tier4", "type": "fake-news"},
    "yournewswire.com": {"score": 5, "bias": "far-right", "tier": "tier4", "type": "fake-news"},
    
    # SATIRE SITES (Score 0 - Instant Detection)
    "theonion.com": {"score": 0, "bias": "satire", "tier": "satire", "type": "satire"},
    "babylonbee.com": {"score": 0, "bias": "satire", "tier": "satire", "type": "satire"},
    "thebeaverton.com": {"score": 0, "bias": "satire", "tier": "satire", "type": "satire"},
    "newsthump.com": {"score": 0, "bias": "satire", "tier": "satire", "type": "satire"},
    "clickhole.com": {"score": 0, "bias": "satire", "tier": "satire", "type": "satire"},
}

print(f"📊 Sources in database: {len(SOURCE_CREDIBILITY)}")


# ============================================================================
# SOURCE CREDIBILITY FUNCTIONS
# ============================================================================

def get_domain_from_url(url: str) -> str:
    """Extract domain from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
    except:
        return ""


def get_verdict_for_tier(source: Dict) -> str:
    """Get human-readable verdict for a known source"""
    tier = source["tier"]
    source_type = source["type"]
    
    if tier == "satire":
        return "🎭 SATIRE - Not Real News"
    elif tier == "tier1":
        return f"✅ Highly credible {source_type} source"
    elif tier == "tier2":
        return f"✅ Credible {source_type} source"
    elif tier == "tier3":
        return f"⚠️ Mixed credibility {source_type} source"
    else:  # tier4
        if source_type == "fake-news":
            return "❌ Known fake news site"
        elif source_type == "state":
            return f"⚠️ State-controlled media"
        elif source_type == "conspiracy":
            return "❌ Conspiracy/unreliable source"
        else:
            return f"❌ Low credibility {source_type} source"


def get_source_credibility(domain: str, url: str, has_corroboration: bool = False) -> Dict:
    """
    ENHANCED: Check source credibility with Phase 2 advanced unknown source detection
    
    Priority:
    1. Check if known source (database lookup)
    2. If unknown, run Phase 2 advanced checks (domain age, patterns, SSL)
    3. Apply corroboration bonus/penalty
    """
    
    # Check if it's a known source
    if domain in SOURCE_CREDIBILITY:
        source = SOURCE_CREDIBILITY[domain]
        
        # Instant satire detection
        if source["tier"] == "satire":
            print(f"🎭 SATIRE DETECTED: {domain}")
            return {
                "known_source": True,
                "credibility_score": 0,
                "bias": "satire",
                "tier": "satire",
                "type": "satire",
                "verdict": "🎭 SATIRE - This is not real news",
                "explanation": f"{domain} is a known satire/parody site. Content is fictional for comedic purposes."
            }
        
        # Known fake news site
        if source["type"] == "fake-news":
            print(f"❌ FAKE NEWS SITE DETECTED: {domain}")
        
        return {
            "known_source": True,
            "credibility_score": source["score"],
            "bias": source["bias"],
            "tier": source["tier"],
            "type": source["type"],
            "verdict": get_verdict_for_tier(source)
        }
    
    # Unknown source - run Phase 2 advanced checks
    print(f"⚠️ UNKNOWN SOURCE DETECTED: {domain}")
    advanced_check = advanced_unknown_source_check(domain, url)
    
    # Apply corroboration adjustment
    if has_corroboration:
        bonus = 25
        advanced_check["score"] = min(advanced_check["score"] + bonus, 60)
        advanced_check["verdict"] += f" (corroborated by {bonus} other sources)"
        print(f"   ✅ Has corroboration: +{bonus} points → {advanced_check['score']}/100")
    else:
        advanced_check["verdict"] += " (NOT corroborated - highly suspicious)"
        print(f"   ❌ No corroboration: No bonus")
    
    return {
        "known_source": False,
        "credibility_score": advanced_check["score"],
        "bias": "unknown",
        "tier": "unknown",
        "type": "unknown",
        "verdict": advanced_check["verdict"],
        "red_flags": advanced_check.get("red_flags", []),
        "phase2_penalty": advanced_check.get("penalty", 0)
    }


# ============================================================================
# CONTENT QUALITY ANALYSIS
# ============================================================================

def analyze_content_quality(article_text: str, headline: str, source_score: int = None) -> Dict:
    """
    Analyze content for red flags indicating misinformation
    
    Red flags:
    - ALL CAPS headlines
    - Excessive exclamation marks
    - Clickbait phrases
    - Emotional manipulation
    - Lack of sources/attribution
    """
    
    red_flags = []
    score = 100  # Start at 100, deduct for issues
    
    # Check 1: ALL CAPS headline
    if headline.isupper() and len(headline) > 20:
        red_flags.append("Headline is in ALL CAPS (sensationalism)")
        score -= 10
    
    # Check 2: Excessive exclamation marks
    exclamation_count = headline.count('!') + article_text[:500].count('!')
    if exclamation_count >= 5:
        red_flags.append(f"Excessive exclamation marks ({exclamation_count} found)")
        score -= 10
    
    # Check 3: Clickbait phrases
    clickbait_phrases = [
        "you won't believe", "shocking", "this one trick",
        "doctors hate", "what happened next", "the truth they",
        "they don't want you to know", "wake up", "exposed",
        "the mainstream media", "censored"
    ]
    text_lower = (headline + " " + article_text[:1000]).lower()
    found_clickbait = [phrase for phrase in clickbait_phrases if phrase in text_lower]
    if found_clickbait:
        red_flags.append(f"Clickbait phrases detected: {', '.join(found_clickbait[:3])}")
        score -= 15
    
    # Check 4: Emotional manipulation words
    emotional_words = ["outrage", "horrifying", "devastating", "apocalyptic", "catastrophe"]
    found_emotional = sum(1 for word in emotional_words if word in text_lower)
    if found_emotional >= 3:
        red_flags.append("Heavy use of emotional manipulation words")
        score -= 10
    
    # Check 5: Very short article (< 200 chars = likely low quality)
    if len(article_text) < 200:
        red_flags.append("Very short article (potential content farm)")
        score -= 15
    
    # Check 6: Lack of attributions/sources
    has_quotes = '"' in article_text or '"' in article_text
    has_according = 'according to' in text_lower or 'sources say' in text_lower
    if not has_quotes and not has_according and len(article_text) > 300:
        red_flags.append("No quotes or source attributions found")
        score -= 10
    
    # Add contradiction warning if source is fake but content looks good
    contradiction_warning = None
    if source_score is not None and source_score < 20 and score > 70:
        contradiction_warning = "⚠️ WARNING: Professional presentation does not equal truth. Fake news sites often mimic legitimate journalism to appear credible."
    
    return {
        "quality_score": max(score, 0),
        "red_flags": red_flags,
        "verdict": "Good quality" if score >= 70 else "Questionable quality" if score >= 40 else "Poor quality",
        "contradiction_warning": contradiction_warning
    }


# ============================================================================
# CROSS-REFERENCE SYSTEM
# ============================================================================

def classify_story_type(headline: str, article_text: str) -> str:
    """
    Classify story type to determine expected cross-reference coverage
    
    Types:
    - major: Major breaking news (expect 5+ sources)
    - exclusive: Investigation/exclusive (expect 0-2 sources)
    - local: Local news (expect 0-3 sources)
    - opinion: Opinion/editorial (expect 0-1 sources)
    - standard: Regular news (expect 2-5 sources)
    """
    
    text_lower = (headline + " " + article_text[:500]).lower()
    
    # Check for exclusive indicators
    exclusive_keywords = ["exclusive", "investigation", "reveals", "uncovered", "obtained by"]
    if any(keyword in text_lower for keyword in exclusive_keywords):
        return "exclusive"
    
    # Check for opinion indicators
    opinion_keywords = ["opinion", "editorial", "commentary", "analysis", "perspective", "viewpoint"]
    if any(keyword in text_lower for keyword in opinion_keywords):
        return "opinion"
    
    # Check for major breaking news indicators
    major_keywords = ["breaking", "hurricane", "earthquake", "attack", "explosion", 
                      "killed", "dead", "missing", "crash", "shooting", "war"]
    if any(keyword in text_lower for keyword in major_keywords):
        return "major"
    
    # Check for local news indicators
    local_keywords = ["local", "county", "mayor", "city council", "neighborhood", 
                      "community", "town", "village"]
    if any(keyword in text_lower for keyword in local_keywords):
        return "local"
    
    return "standard"


def get_cross_reference_score(sources_found: int, story_type: str) -> Dict:
    """
    Score based on number of corroborating sources and story type
    
    Different story types have different expectations:
    - major: Need lots of corroboration
    - exclusive: Don't expect corroboration
    - local: Low national coverage expected
    - opinion: No corroboration expected
    """
    
    # Define expectations by story type
    expectations = {
        "major": {
            "expected_min": 5,
            "score_0": 10,   # Very suspicious if no one else has it
            "score_1_2": 40,
            "score_3_4": 70,
            "score_5plus": 95
        },
        "exclusive": {
            "expected_min": 0,
            "score_0": 85,   # Expected for exclusive
            "score_1_2": 90,
            "score_3_4": 95,
            "score_5plus": 95
        },
        "local": {
            "expected_min": 1,
            "score_0": 50,   # Some local stories won't have national coverage
            "score_1_2": 80,
            "score_3_4": 90,
            "score_5plus": 95
        },
        "opinion": {
            "expected_min": 0,
            "score_0": 80,   # Opinions don't need corroboration
            "score_1_2": 85,
            "score_3_4": 90,
            "score_5plus": 90
        },
        "standard": {
            "expected_min": 2,
            "score_0": 20,   # Suspicious if no corroboration
            "score_1_2": 60,
            "score_3_4": 85,
            "score_5plus": 95
        }
    }
    
    exp = expectations.get(story_type, expectations["standard"])
    
    # Determine score based on sources found
    if sources_found == 0:
        score = exp["score_0"]
        verdict = "No corroborating sources found"
    elif sources_found <= 2:
        score = exp["score_1_2"]
        verdict = f"Limited corroboration ({sources_found} sources)"
    elif sources_found <= 4:
        score = exp["score_3_4"]
        verdict = f"Good corroboration ({sources_found} sources)"
    else:
        score = exp["score_5plus"]
        verdict = f"Strong corroboration ({sources_found}+ sources)"
    
    return {
        "score": score,
        "sources_found": sources_found,
        "story_type": story_type,
        "verdict": verdict
    }

# ============================================================================
# ASSERTIVE VERDICT GENERATION
# ============================================================================

def get_assertive_label_and_verdict(final_score: int, source_score: int, source_type: str, 
                                     content_score: int, cross_ref_score: int, 
                                     story_type: str) -> dict:
    """
    Generate ASSERTIVE labels and verdicts based on scores
    No more wishy-washy "mixed reliability" - tell it like it is!
    """
    
    # CRITICAL: Known fake news sites
    if source_type == "fake-news":
        return {
            "label": "FAKE NEWS",
            "verdict": "⚠️ DANGER: This is a KNOWN FAKE NEWS SITE. This source has been identified as deliberately spreading misinformation. DO NOT trust any content from this domain.",
            "warning_level": "critical",
            "should_share": False,
            "recommendation": "Cross-check this story with credible news sources like BBC, Reuters, or AP News before believing or sharing."
        }
    
    # CRITICAL: Very low source credibility (< 20)
    if source_score < 20:
        return {
            "label": "NOT CREDIBLE",
            "verdict": f"⚠️ WARNING: This source has EXTREMELY LOW credibility ({source_score}/100). Even with {'good' if content_score > 70 else 'poor'} content quality, the publisher is known to be unreliable. Treat any claims with extreme skepticism.",
            "warning_level": "critical",
            "should_share": False,
            "recommendation": "Verify this information with established news organizations before acting on it."
        }
    
    # SEVERE: Low credibility source (20-39)
    elif source_score < 40:
        return {
            "label": "LOW CREDIBILITY",
            "verdict": f"⚠️ CAUTION: This source has low credibility ({source_score}/100). Known issues with accuracy and bias. Content quality: {content_score}/100. Cross-check before trusting.",
            "warning_level": "high",
            "should_share": False,
            "recommendation": "Compare this story with reports from mainstream news sources."
        }
    
    # MODERATE: Questionable (40-49)
    elif final_score < 50:
        return {
            "label": "QUESTIONABLE",
            "verdict": f"⚠️ Be Skeptical: This story scores {final_score}/100. Source credibility is {source_score}/100. Verify key claims independently.",
            "warning_level": "medium",
            "should_share": False,
            "recommendation": "Look for corroboration from higher-quality sources."
        }
    
    # ACCEPTABLE: Probably credible (50-69)
    elif final_score < 70:
        return {
            "label": "Probably Credible",
            "verdict": f"✓ Likely Accurate: This story scores {final_score}/100. Source is {_get_source_description(source_score)}. Content appears {'well-sourced' if content_score > 70 else 'adequate'}.",
            "warning_level": "low",
            "should_share": True,
            "recommendation": "Generally reliable, but verify important claims."
        }
    
    # GOOD: Credible (70-89)
    elif final_score < 90:
        return {
            "label": "Credible",
            "verdict": f"✅ Trustworthy: This story scores {final_score}/100 from a {_get_source_description(source_score)} source. Content is {_get_quality_description(content_score)}.",
            "warning_level": "none",
            "should_share": True,
            "recommendation": "Reliable source. Safe to reference."
        }
    
    # EXCELLENT: Highly credible (90+)
    else:
        return {
            "label": "Highly Credible",
            "verdict": f"✅ VERIFIED: This story scores {final_score}/100. Published by a highly credible source ({source_score}/100) with excellent content quality ({content_score}/100).",
            "warning_level": "none",
            "should_share": True,
            "recommendation": "Top-tier journalism. Highly reliable."
        }


def _get_source_description(score: int) -> str:
    """Get human-readable source quality description"""
    if score >= 90:
        return "highly credible"
    elif score >= 70:
        return "credible"
    elif score >= 50:
        return "moderately reliable"
    elif score >= 40:
        return "low credibility"
    else:
        return "unreliable"


def _get_quality_description(score: int) -> str:
    """Get human-readable content quality description"""
    if score >= 90:
        return "excellent quality"
    elif score >= 70:
        return "good quality"
    elif score >= 50:
        return "adequate quality"
    else:
        return "poor quality"


# ============================================================================
# NEWS VERIFICATION (MAIN FUNCTION)
# ============================================================================

def extract_search_terms(headline: str, article_text: str) -> str:
    """
    Extract key search terms from headline and article
    Removes common words, focuses on entities and key phrases
    """
    
    # Start with headline
    text = headline
    
    # Add first sentence of article (usually has key info)
    if article_text:
        sentences = article_text.split('.')
        if sentences:
            text += " " + sentences[0]
    
    # Remove common words
    common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                    'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
                    'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they']
    
    words = text.lower().split()
    keywords = [word.strip('.,!?;:') for word in words if word.lower() not in common_words and len(word) > 3]
    
    # Take top 5-7 most relevant words
    search_query = ' '.join(keywords[:7])
    
    return search_query


def cross_reference_news(headline: str, article_text: str, source_score: int = None) -> Dict:
    """
    ENHANCED: Cross-reference story with other news sources
    
    Improvements:
    1. Story type classification (major/exclusive/local/opinion)
    2. Context-aware scoring
    3. Smart search term extraction
    4. Google News backup if NewsAPI fails
    5. URL encoding fix
    """
    
    if not NEWS_API_KEY:
        print("⚠️ No NewsAPI key - skipping cross-reference")
        return {
            "sources_found": 0,
            "corroborating_sources": [],
            "cross_ref_score": 50,
            "verdict": "Could not verify (no API key)"
        }
    
    # Step 1: Classify story type
    story_type = classify_story_type(headline, article_text)
    print(f"📰 Story type classified as: {story_type}")
    
    # Step 2: Extract smart search terms
    search_query = extract_search_terms(headline, article_text)
    print(f"🔍 Search query: {search_query}")
    
    # Step 3: Search with NewsAPI
    try:
        # URL encode the query properly (FIX for "0 sources found" bug)
        encoded_query = quote_plus(search_query)
        url = f"https://newsapi.org/v2/everything?q={encoded_query}&language=en&sortBy=relevancy&pageSize=10&apiKey={NEWS_API_KEY}"
        
        print(f"🌐 Querying NewsAPI...")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            
            if articles:
                # Extract unique sources
                unique_sources = set()
                corroborating = []
                
                for article in articles:
                    source_name = article.get("source", {}).get("name", "Unknown")
                    if source_name != "Unknown":
                        unique_sources.add(source_name)
                        corroborating.append({
                            "source": source_name,
                            "title": article.get("title", ""),
                            "url": article.get("url", "")
                        })
                
                sources_count = len(unique_sources)
                print(f"✅ Found {sources_count} unique sources via NewsAPI")
                
                # Get context-aware score
                score_data = get_cross_reference_score(sources_count, story_type)
                
                # Add contradiction warning
                contradiction_warning = None
                if source_score is not None and source_score < 20 and sources_count >= 3:
                    contradiction_warning = "⚠️ WARNING: Other sites may be repeating this story without verification. Strong corroboration doesn't validate content from known fake news sources."
                
                return {
                    "contradiction_warning": contradiction_warning,
                    "sources_found": sources_count,
                    "corroborating_sources": corroborating[:5],  # Top 5
                    "cross_ref_score": score_data["score"],
                    "story_type": story_type,
                    "verdict": score_data["verdict"]
                }
            else:
                print(f"⚠️ NewsAPI returned 0 results")
        
        elif response.status_code == 426:
            print(f"⚠️ NewsAPI rate limit hit (426)")
        else:
            print(f"⚠️ NewsAPI error: {response.status_code}")
    
    except Exception as e:
        print(f"❌ NewsAPI failed: {e}")
    
    # Step 4: Fallback to Google News RSS (free, no API key needed!)
    print(f"🔄 Falling back to Google News RSS...")
    try:
        import feedparser
        
        # Google News RSS search
        encoded_query = quote_plus(search_query)
        google_news_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        feed = feedparser.parse(google_news_url)
        
        if feed.entries:
            sources_count = min(len(feed.entries), 10)  # Cap at 10
            print(f"✅ Found {sources_count} results via Google News RSS")
            
            # Extract sources
            corroborating = []
            for entry in feed.entries[:5]:
                corroborating.append({
                    "source": entry.get("source", {}).get("title", "Google News"),
                "title": entry.get("title", ""),
                "url": entry.get("link", "")
            })
        
        # Get context-aware score
        score_data = get_cross_reference_score(sources_count, story_type)
        
        # Add contradiction warning
        contradiction_warning = None
        if source_score is not None and source_score < 20 and sources_count >= 3:
            contradiction_warning = "⚠️ WARNING: Other sites may be repeating this story without verification. Strong corroboration doesn't validate content from known fake news sources."
        
        return {
            "contradiction_warning": contradiction_warning,
            "sources_found": sources_count,
                "corroborating_sources": corroborating,
                "cross_ref_score": score_data["score"],
                "story_type": story_type,
                "verdict": score_data["verdict"] + " (via Google News)"
            }
    
    except Exception as e:
        print(f"❌ Google News RSS also failed: {e}")
    
    # Step 5: No sources found
    print(f"❌ Could not find any corroborating sources")
    score_data = get_cross_reference_score(0, story_type)
    
    return {
        "contradiction_warning": None,
        "sources_found": 0,
        "corroborating_sources": [],
        "cross_ref_score": score_data["score"],
        "story_type": story_type,
        "verdict": score_data["verdict"]
    }


# ============================================================================
# NEWS VERIFICATION (MAIN FUNCTION)
# ============================================================================

def verify_news(url: str) -> Dict:
    """
    COMPLETE NEWS VERIFICATION SYSTEM
    
    Three-pillar approach:
    1. Source Credibility (40% weight) - Who published it?
    2. Content Quality (35% weight) - Any red flags in the content?
    3. Cross-Reference (25% weight) - Do other sources report it?
    
    ENHANCED with:
    - 70+ news sources (from 50)
    - Phase 2 safeguards for unknown sources
    - Smart cross-reference system
    - Context-aware weighting
    - Satire detection
    - Fake news flagging
    """
    
    print(f"\n{'='*80}")
    print(f"🎯 VERIFYING NEWS ARTICLE")
    print(f"{'='*80}")
    print(f"URL: {url}\n")
    
    try:
        # Step 1: Fetch article
        print(f"📥 Fetching article...")
        from newspaper import Article
        
        article = Article(url)
        article.download()
        article.parse()
        
        headline = article.title
        article_text = article.text
        domain = get_domain_from_url(url)
        
        print(f"✅ Article fetched successfully")
        print(f"   Domain: {domain}")
        print(f"   Headline: {headline[:80]}...")
        print(f"   Text length: {len(article_text)} characters\n")
        
        # Step 2: Check source credibility
        print(f"🏛️ CHECKING SOURCE CREDIBILITY...")
        print(f"{'-'*80}")
        
        # We'll determine has_corroboration after cross-reference
        source_cred = get_source_credibility(domain, url, has_corroboration=False)
        
        # Instant satire detection
        if source_cred.get("tier") == "satire":
            print(f"\n{'='*80}")
            print(f"🎭 SATIRE DETECTED!")
            print(f"{'='*80}\n")
            return {
                "trust_score": 0,
                "label": "Satire",
                "verdict": "This is satire/parody, not real news",
                "source_credibility": 0,
                "content_quality": "N/A",
                "cross_reference": "N/A",
                "explanation": f"{domain} is a known satire site. This article is fictional humor.",
                "evidence": {
                    "source": "Known satire publication",
                    "content": "Satirical content",
                    "cross_ref": "Not applicable"
                }
            }
        
        print(f"   Known source: {source_cred['known_source']}")
        print(f"   Credibility score: {source_cred['credibility_score']}/100")
        print(f"   Verdict: {source_cred['verdict']}\n")
        
        # Step 3: Analyze content quality
        print(f"📝 ANALYZING CONTENT QUALITY...")
        print(f"{'-'*80}")
        
        content_analysis = analyze_content_quality(article_text, headline, source_cred["credibility_score"])
        
        print(f"   Quality score: {content_analysis['quality_score']}/100")
        if content_analysis['red_flags']:
            print(f"   Red flags found:")
            for flag in content_analysis['red_flags']:
                print(f"      ⚠️ {flag}")
        else:
            print(f"   ✅ No major red flags detected")
        print()
        
        # Step 4: Cross-reference with other sources
        print(f"🔍 CROSS-REFERENCING WITH OTHER SOURCES...")
        print(f"{'-'*80}")
        
        cross_ref = cross_reference_news(headline, article_text, source_cred["credibility_score"])
        
        print(f"   Sources found: {cross_ref['sources_found']}")
        print(f"   Cross-ref score: {cross_ref['cross_ref_score']}/100")
        print(f"   Verdict: {cross_ref['verdict']}\n")
        
        # Step 5: Re-evaluate source credibility with corroboration info
        # (For unknown sources, corroboration matters a lot!)
        if not source_cred['known_source']:
            has_corroboration = cross_ref['sources_found'] > 0
            source_cred = get_source_credibility(domain, url, has_corroboration=has_corroboration)
            print(f"   Re-evaluated unknown source with corroboration:")
            print(f"   Updated credibility score: {source_cred['credibility_score']}/100\n")
        
        # Step 6: Calculate weighted final score
        print(f"📊 CALCULATING FINAL TRUST SCORE...")
        print(f"{'-'*80}")
        
        # Dynamic weights based on story type
        story_type = cross_ref.get("story_type", "standard")
        
        if story_type == "major":
            # Major news needs strong corroboration
            weights = {"source": 0.35, "content": 0.35, "cross_ref": 0.30}
        elif story_type == "exclusive":
            # Exclusive stories - trust the source more
            weights = {"source": 0.60, "content": 0.25, "cross_ref": 0.15}
        elif story_type == "local":
            # Local news - source and content matter more
            weights = {"source": 0.50, "content": 0.40, "cross_ref": 0.10}
        elif story_type == "opinion":
            # Opinion - source matters most
            weights = {"source": 0.55, "content": 0.40, "cross_ref": 0.05}
        else:
            # Standard news
            weights = {"source": 0.40, "content": 0.35, "cross_ref": 0.25}
        
        print(f"   Story type: {story_type}")
        print(f"   Weights: Source {int(weights['source']*100)}%, Content {int(weights['content']*100)}%, Cross-ref {int(weights['cross_ref']*100)}%")
        
        final_score = (
            source_cred["credibility_score"] * weights["source"] +
            content_analysis["quality_score"] * weights["content"] +
            cross_ref["cross_ref_score"] * weights["cross_ref"]
        )
        
        final_score = round(final_score)
        
        # ⚠️ SAFETY CAP: Prevent fake/unreliable sites from scoring high
        original_score = final_score
        
        if source_cred["credibility_score"] < 20:
            final_score = min(final_score, 30)
            if original_score != final_score:
                print(f"   ⚠️ SAFETY CAP APPLIED: Source score {source_cred['credibility_score']}/100 too low")
                print(f"   📉 Score reduced from {original_score} to {final_score}")
        
        elif source_cred["credibility_score"] < 40:
            final_score = min(final_score, 50)
            if original_score != final_score:
                print(f"   ⚠️ LOW CREDIBILITY CAP: Source score {source_cred['credibility_score']}/100")
                print(f"   📉 Score reduced from {original_score} to {final_score}")
        
        print(f"\n   Source: {source_cred['credibility_score']}/100 × {weights['source']} = {source_cred['credibility_score'] * weights['source']:.1f}")
        print(f"   Content: {content_analysis['quality_score']}/100 × {weights['content']} = {content_analysis['quality_score'] * weights['content']:.1f}")
        print(f"   Cross-ref: {cross_ref['cross_ref_score']}/100 × {weights['cross_ref']} = {cross_ref['cross_ref_score'] * weights['cross_ref']:.1f}")
        print(f"\n   🎯 FINAL TRUST SCORE: {final_score}/100")
        
        # Step 7: Generate ASSERTIVE label and verdict
        verdict_data = get_assertive_label_and_verdict(
            final_score=final_score,
            source_score=source_cred["credibility_score"],
            source_type=source_cred.get("type", "unknown"),
            content_score=content_analysis["quality_score"],
            cross_ref_score=cross_ref["cross_ref_score"],
            story_type=story_type
        )
        
        label = verdict_data["label"]
        verdict = verdict_data["verdict"]
        warning_level = verdict_data["warning_level"]
        should_share = verdict_data["should_share"]
        recommendation = verdict_data["recommendation"]
        
        print(f"   📋 LABEL: {label}")
        print(f"   ⚠️  WARNING LEVEL: {warning_level}")
        print(f"   💡 RECOMMENDATION: {recommendation}")
        print(f"\n{'='*80}\n")
        
        # Build comprehensive result
        result = {
            "trust_score": final_score,
            "label": label,
            "verdict": verdict,
            "warning_level": warning_level,
            "should_share": should_share,
            "recommendation": recommendation,
            "source_credibility": source_cred["credibility_score"],
            "content_quality": content_analysis["quality_score"],
            "cross_reference": cross_ref["cross_ref_score"],
            "story_type": story_type,
            "weights_used": weights,
            "explanation": recommendation,
            "evidence": {
                "source": {
                    "domain": domain,
                    "known_source": source_cred["known_source"],
                    "score": source_cred["credibility_score"],
                    "verdict": source_cred["verdict"],
                    "phase2_checks": source_cred.get("red_flags", [])
                },
                
                "content": {
    "score": content_analysis["quality_score"],
    "red_flags": content_analysis["red_flags"],
    "verdict": content_analysis["verdict"],
    "contradiction_warning": content_analysis.get("contradiction_warning")
},
                "cross_reference": {
    "sources_found": cross_ref["sources_found"],
    "score": cross_ref["cross_ref_score"],
    "story_type": story_type,
    "corroborating_sources": cross_ref.get("corroborating_sources", [])[:3],
    "verdict": cross_ref["verdict"],
    "contradiction_warning": cross_ref.get("contradiction_warning")
}
            }
        }
        
        return result
    
    except Exception as e:
        print(f"❌ Error verifying news: {e}")
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"Could not verify article: {str(e)}",
            "error": str(e)
        }


# ============================================================================
# CELERY TASKS
# ============================================================================

# ============================================================================
# IMAGE/VIDEO/TEXT DETECTION - COMPLETE WORKING CODE
# Paste this to replace the 3 stub functions you just deleted
# ============================================================================

import httpx
import traceback
import base64
from typing import Dict, Optional

# API Keys (already defined at top of your file, but listed here for reference)
# AIORNOT_API_KEY = os.getenv("AIORNOT_API_KEY")
# WINSTON_API_KEY = os.getenv("WINSTON_API_KEY")
# HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
# SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER")
# SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET")

# Add these at the top of celery_worker.py with your other imports
SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER", "")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET", "")
AIORNOT_API_KEY = os.getenv("AIORNOT_API_KEY", "")
WINSTON_API_KEY = os.getenv("WINSTON_API_KEY", "")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")


# ============================================================================
# HELPER FUNCTIONS FOR IMAGE/VIDEO/TEXT
# ============================================================================

def amplify_confidence(confidence: float) -> float:
    """Amplify confidence scores to make them more decisive"""
    centered = confidence - 0.5
    amplified = centered * (abs(centered) ** 0.3) * 2.5
    result = 0.5 + amplified
    return max(0.0, min(1.0, result))


def get_detection_label(score: int) -> Dict:
    """Convert detection score to label with explanation"""
    if score >= 70:
        return {
            "label": "Likely Real",
            "explanation": "This content appears authentic based on AI detection analysis.",
            "confidence": "High"
        }
    elif score >= 50:
        return {
            "label": "Uncertain",
            "explanation": "Mixed signals detected. Manual verification recommended.",
            "confidence": "Medium"
        }
    elif score >= 30:
        return {
            "label": "Probably Fake",
            "explanation": "Signs of AI generation detected.",
            "confidence": "Medium-High"
        }
    else:
        return {
            "label": "Likely Fake",
            "explanation": "Strong indicators of AI generation detected.",
            "confidence": "High"
        }

def calculate_ensemble_score(results: list, media_type: str = "image") -> dict:
    """
    WEIGHTED ENSEMBLE ALGORITHM
    Gives better detectors more influence in final score
    
    Weights:
    - SightEngine: 40% (best for images)
    - AIorNOT: 35% (good backup)
    - Hugging Face: 25% (fallback only)
    """
    if not results:
        return {
            "weighted_confidence": 0.5,
            "trust_score": 50,
            "detectors_used": 0,
            "providers": []
        }
    
    # Define weights based on detector quality
    weights = {
        'SightEngine': 0.40,
        'AIorNOT': 0.35,
        'Hugging Face': 0.25,
        'RoBERTa (Backup)': 0.25
    }
    
    # Calculate weighted average
    total_weight = 0
    weighted_sum = 0
    providers_used = []
    
    for result in results:
        provider = result.get("provider", "Unknown")
        ai_confidence = result.get("ai_confidence", 0.5)
        weight = weights.get(provider, 1.0 / len(results))
        
        weighted_sum += ai_confidence * weight
        total_weight += weight
        providers_used.append(provider)
    
    # Normalize by total weight
    weighted_confidence = weighted_sum / total_weight if total_weight > 0 else 0.5
    
    # Apply amplification (uses existing function)
    amplified_confidence = amplify_confidence(weighted_confidence)
    
    # Convert to trust score (0-100)
    trust_score = int((1 - amplified_confidence) * 100)
    
    return {
        "weighted_confidence": round(weighted_confidence, 3),
        "amplified_confidence": round(amplified_confidence, 3),
        "trust_score": trust_score,
        "detectors_used": len(results),
        "providers": providers_used
    }

# ============================================================================
# SIGHTENGINE DETECTION (Primary for Images)
# ============================================================================

def detect_with_sightengine_url(image_url: str) -> Optional[Dict]:
    """SightEngine AI detection via URL"""
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        print("⚠️ SightEngine credentials not configured")
        return None
    
    try:
        print(f"👁️ Calling SightEngine...")
        
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
                ai_prob = data.get('type', {}).get('ai_generated', 0.5)
                
                print(f"✅ SightEngine: {int((1-ai_prob)*100)}% human")
                
                return {
                    "provider": "SightEngine",
                    "ai_confidence": ai_prob,
                    "verdict": "AI-generated" if ai_prob > 0.5 else "Real"
                }
            else:
                print(f"⚠️ SightEngine error: {response.status_code}")
                return None
                
    except Exception as e:
        print(f"⚠️ SightEngine error: {str(e)}")
        return None


def detect_with_sightengine_file(image_data: bytes, filename: str) -> Optional[Dict]:
    """SightEngine AI detection via file upload"""
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        return None
    
    try:
        print(f"👁️ Calling SightEngine (file)...")
        
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
                files={'media': (filename, file_obj, 'image/jpeg')}
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_prob = data.get('type', {}).get('ai_generated', 0.5)
                
                print(f"✅ SightEngine: {int((1-ai_prob)*100)}% human")
                
                return {
                    "provider": "SightEngine",
                    "ai_confidence": ai_prob,
                    "verdict": "AI-generated" if ai_prob > 0.5 else "Real"
                }
            else:
                return None
                
    except Exception as e:
        print(f"⚠️ SightEngine file error: {str(e)}")
        return None
@app.task(name='credisource.verify_content_file', bind=True)
def verify_content_file(self, job_id: str, file_base64: str, filename: str, content_type: str) -> Dict:
    """
    Handle file uploads (images/videos encoded as base64)
    Decodes base64 data and passes to appropriate detector
    """
    print(f"\n{'='*80}")
    print(f"📤 RECEIVED FILE UPLOAD")
    print(f"{'='*80}")
    print(f"Job ID: {job_id}")
    print(f"Filename: {filename}")
    print(f"Content Type: {content_type}")
    print(f"File Size: {len(file_base64)} bytes (base64)")
    print(f"{'='*80}\n")
    
    try:
        # Decode base64 to bytes
        file_data = base64.b64decode(file_base64)
        print(f"✅ Decoded {len(file_data)} bytes")
        
        # Route to appropriate handler
        if content_type == "image":
            return verify_image_file(file_data, filename)
        elif content_type == "video":
            return verify_video_file(file_data, filename)
        elif content_type == "text":
            # For text files, decode as string
            text_content = file_data.decode('utf-8')
            return verify_text_task(text_content)
        else:
            return {
                "trust_score": 0,
                "label": "Error",
                "verdict": f"Unsupported file type: {content_type}"
            }
    
    except Exception as e:
        print(f"❌ File processing error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"File processing failed: {str(e)}",
            "error": str(e)
        }


def verify_image_file(image_data: bytes, filename: str) -> Dict:
    """Image detection from uploaded file data"""
    print(f"📸 Processing uploaded image: {filename}")
    
    try:
        results = []
        
        # 1. SightEngine (file upload)
        sightengine_result = detect_with_sightengine_file(image_data, filename)
        if sightengine_result:
            results.append(sightengine_result)
        
        # 2. AIorNOT (file upload)
        aiornot_result = detect_with_aiornot(image_data, is_file=True, is_video=False)
        if aiornot_result:
            results.append(aiornot_result)
        
        # 3. Hugging Face (fallback)
        if not results:
            hf_result = detect_with_huggingface_image(image_data)
            if hf_result:
                results.append(hf_result)
        
        if not results:
            return {
                "trust_score": 50,
                "label": "Unavailable",
                "verdict": "AI detection services unavailable"
            }
        
        # Calculate WEIGHTED ensemble score
        ensemble = calculate_ensemble_score(results, media_type="image")
        trust_score = ensemble["trust_score"]
        
        label_info = get_detection_label(trust_score)
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "detectors_used": ensemble["detectors_used"],
            "providers": ensemble["providers"]
        }
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "detectors_used": len(results),
            "providers": [r["provider"] for r in results]
        }
        
    except Exception as e:
        print(f"❌ Image file verification error: {str(e)}")
        return {
            "trust_score": 50,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}"
        }


def verify_video_file(video_data: bytes, filename: str) -> Dict:
    """Video detection from uploaded file data"""
    print(f"🎥 Processing uploaded video: {filename}")
    
    try:
        # AIorNOT supports video file uploads
        aiornot_result = detect_with_aiornot(video_data, is_file=True, is_video=True)
        
        if not aiornot_result:
            return {
                "trust_score": 50,
                "label": "Unavailable",
                "verdict": "Video AI detection unavailable (AIorNOT required)"
            }
        
        ai_confidence = aiornot_result["ai_confidence"]
        trust_score = int((1 - ai_confidence) * 100)
        label_info = get_detection_label(trust_score)
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "provider": aiornot_result["provider"]
        }
        
    except Exception as e:
        print(f"❌ Video file verification error: {str(e)}")
        return {
            "trust_score": 50,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}"
        }

# ============================================================================
# AIORNOT DETECTION (Backup for Images/Videos)
# ============================================================================

def detect_with_aiornot(url_or_data, is_file: bool = False, is_video: bool = False) -> Optional[Dict]:
    """AIorNOT API detection"""
    if not AIORNOT_API_KEY:
        print("⚠️ No AIorNOT API key")
        return None
    
    try:
        content_type = "video" if is_video else "image"
        print(f"🔍 Calling AIorNOT ({content_type})...")
        
        with httpx.Client(timeout=60.0) as client:
            if is_file:
                import io
                file_obj = io.BytesIO(url_or_data) if isinstance(url_or_data, bytes) else url_or_data
                
                # Set correct filename and MIME type
                if is_video:
                    filename = "video.mp4"
                    mime_type = "video/mp4"
                else:
                    filename = "image.jpg"
                    mime_type = "image/jpeg"
                
                # Use v2 API with correct endpoint for each type
                if is_video:
                    endpoint = "https://api.aiornot.com/v2/video/sync"
                    file_field = "video"
                else:
                    endpoint = "https://api.aiornot.com/v2/image/sync"
                    file_field = "image"

                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"},
                    files={file_field: (filename, file_obj, mime_type)}
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
            
            if response.status_code != 200:
                print(f"⚠️ AIorNOT error: {response.status_code}")
                return None
            
            data = response.json()
            verdict = data.get("verdict", "unknown")
            
            ai_confidence = 0.5
            if verdict == "ai":
                ai_confidence = 0.9
            elif verdict == "human":
                ai_confidence = 0.1
            
            print(f"✅ AIorNOT: {verdict}")
            
            return {
                "provider": "AIorNOT",
                "ai_confidence": ai_confidence,
                "verdict": verdict
            }
            
    except Exception as e:
        print(f"⚠️ AIorNOT error: {str(e)}")
        return None


# ============================================================================
# HUGGING FACE DETECTION (Backup)
# ============================================================================

def detect_with_huggingface_image(image_data: bytes) -> Optional[Dict]:
    """Hugging Face image detection (backup)"""
    if not HUGGINGFACE_API_KEY:
        return None
    
    try:
        print(f"🤗 Calling Hugging Face...")
        
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api-inference.huggingface.co/models/Organika/sdxl-detector",
                headers={
                    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"inputs": image_b64}
            )
            
            if response.status_code == 503:
                print("⏳ Model loading...")
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/Organika/sdxl-detector",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": image_b64}
                )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            ai_confidence = 0.5
            
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    if result.get("label") in ["artificial", "AI", "LABEL_1"]:
                        ai_confidence = result.get("score", 0.5)
                        break
            
            print(f"✅ HF AI confidence: {int(ai_confidence*100)}%")
            
            return {
                "provider": "Hugging Face",
                "ai_confidence": ai_confidence,
                "verdict": "AI-generated" if ai_confidence > 0.5 else "Real"
            }
            
    except Exception as e:
        print(f"⚠️ Hugging Face error: {str(e)}")
        return None


# ============================================================================
# TEXT DETECTION FUNCTIONS
# ============================================================================

def detect_text_winston(text_content: str) -> Optional[Dict]:
    """Winston AI text detection (primary)"""
    if not WINSTON_API_KEY:
        return None
    
    try:
        print(f"🔍 Calling Winston AI...")
        
        # Skip Winston for very long text to conserve credits
        if len(text_content) > 2000:
            print(f"⚠️ Text too long ({len(text_content)} chars) - using backup")
            return None
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.gowinston.ai/v2/predict",
                headers={
                    "Authorization": f"Bearer {WINSTON_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "text": text_content[:10000],
                    "language": "en",
                    "sentences": True,
                    "version": "latest"
                }
            
            if response.status_code != 200:
                print(f"⚠️ Winston error: {response.status_code}")
                return None
            
            data = response.json()
            
            if "score" in data:
                human_score = data["score"]
                ai_confidence = (100 - human_score) / 100
                
                print(f"✅ Winston: {human_score}% human")
                
                return {
                    "provider": "Winston AI",
                    "ai_confidence": ai_confidence,
                    "verdict": "AI-generated" if ai_confidence > 0.5 else "Human-written"
                }
            
            return None
            
    except Exception as e:
        print(f"⚠️ Winston error: {str(e)}")
        return None


def detect_text_huggingface(text_content: str) -> Optional[Dict]:
    """Hugging Face text detection (backup)"""
    if not HUGGINGFACE_API_KEY:
        return None
    
    try:
        print(f"🤗 Calling RoBERTa (backup)...")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api-inference.huggingface.co/models/openai-community/roberta-large-openai-detector",
                headers={
                    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"inputs": text_content[:2000]}
            )
            
            if response.status_code == 503:
                import time
                time.sleep(10)
                response = client.post(
                    "https://api-inference.huggingface.co/models/openai-community/roberta-large-openai-detector",
                    headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
                    json={"inputs": text_content[:2000]}
                )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            ai_confidence = 0.5
            
            if isinstance(data, list) and len(data) > 0:
                results = data[0] if isinstance(data[0], list) else data
                for result in results:
                    if result.get("label") == "LABEL_1":
                        ai_confidence = result.get("score", 0.5)
                        break
            
            # Calibrate for false positives on formal text
            if ai_confidence > 0.85:
                ai_confidence = 0.5 + (ai_confidence - 0.85) * 0.3
            
            print(f"✅ RoBERTa: {int(ai_confidence*100)}% AI")
            
            return {
                "provider": "RoBERTa (Backup)",
                "ai_confidence": ai_confidence,
                "verdict": "AI-generated" if ai_confidence > 0.5 else "Human-written"
            }
            
    except Exception as e:
        print(f"⚠️ RoBERTa error: {str(e)}")
        return None


# ============================================================================
# MAIN DETECTION TASK FUNCTIONS
# ============================================================================

@app.task(bind=True)
def verify_image_task(self, image_url: str) -> Dict:
    """
    Complete image AI detection with ensemble approach
    Uses: SightEngine (primary), AIorNOT (backup), Hugging Face (fallback)
    """
    print(f"📸 Image verification started: {image_url}")
    
    try:
        # Download image
        print(f"📥 Downloading image...")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(image_url)
            if response.status_code != 200:
                return {
                    "trust_score": 50,
                    "label": "Error",
                    "verdict": f"Failed to download image: {response.status_code}"
                }
            image_data = response.content
        
        print(f"✅ Downloaded {len(image_data)} bytes")
        
        # Try detection methods
        results = []
        
        # 1. SightEngine (primary)
        sightengine_result = detect_with_sightengine_url(image_url)
        if sightengine_result:
            results.append(sightengine_result)
        
        # 2. AIorNOT (backup)
        aiornot_result = detect_with_aiornot(image_url, is_file=False)
        if aiornot_result:
            results.append(aiornot_result)
        
        # 3. Hugging Face (fallback)
        if not results:
            hf_result = detect_with_huggingface_image(image_data)
            if hf_result:
                results.append(hf_result)
        
        # If all failed
        if not results:
            return {
                "trust_score": 50,
                "label": "Unavailable",
                "verdict": "AI detection services unavailable"
            }
        
        # Calculate WEIGHTED ensemble score
        ensemble = calculate_ensemble_score(results, media_type="image")
        trust_score = ensemble["trust_score"]
        
        label_info = get_detection_label(trust_score)
        
        print(f"📊 Final score: {trust_score}/100 ({label_info['label']})")
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "detectors_used": ensemble["detectors_used"],
            "providers": ensemble["providers"]
        }
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "detectors_used": len(results),
            "providers": [r["provider"] for r in results]
        }
        
    except Exception as e:
        print(f"❌ Image verification error: {str(e)}")
        traceback.print_exc()
        return {
            "trust_score": 50,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}"
        }
def download_video_with_ytdlp(video_url: str):
    """
    Download video using yt-dlp
    Returns path to downloaded file, or None if failed
    """
    try:
        import yt_dlp
        import tempfile
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        output_path = temp_file.name
        temp_file.close()
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        return None
        
    except Exception as e:
        print(f"   yt-dlp error: {e}")
        return None


@app.task(bind=True)
def verify_video_task(self, video_url: str) -> Dict:
    """
    Video verification with RapidAPI fallback for blocked platforms
    
    Flow:
    1. Try yt-dlp first (works for TikTok, Reddit, Vimeo, Twitter)
    2. If yt-dlp fails, try RapidAPI (works for YouTube, Instagram, Facebook)
    3. Send downloaded file to AIorNOT for AI detection
    """
    
    print(f"\n{'='*80}")
    print(f"🎥 VIDEO VERIFICATION STARTED")
    print(f"{'='*80}")
    print(f"URL: {video_url}")
    print(f"")
    
    video_path = None
    download_method = None
    
    try:
        # STEP 1: Try yt-dlp first (fast, free, works for many platforms)
        print("📥 METHOD 1: Trying yt-dlp download...")
        video_path = download_video_with_ytdlp(video_url)
        
        if video_path and os.path.exists(video_path):
            print(f"✅ yt-dlp succeeded!")
            download_method = "yt-dlp"
        else:
            print("⚠️ yt-dlp failed or blocked")
            
            # STEP 2: Fallback to RapidAPI
            print("\n📥 METHOD 2: Trying RapidAPI download...")
            
            # Import the RapidAPI downloader
            import os
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from rapidapi_downloader import download_with_rapidapi_sync
            
            result = download_with_rapidapi_sync(video_url, platform="auto")
            
            if result.get("success"):
                video_path = result.get("video_path")
                download_method = f"RapidAPI ({result.get('platform')})"
                print(f"✅ RapidAPI succeeded!")
            else:
                print(f"❌ RapidAPI also failed: {result.get('error')}")
                
                # Both methods failed
                return {
                    "trust_score": 0,
                    "label": "Download Failed",
                    "verdict": f"Could not download video. Platform may be blocked or require authentication. Error: {result.get('error')}",
                    "error": "Both yt-dlp and RapidAPI failed"
                }
        
        # STEP 3: Verify the downloaded video file exists
        if not video_path or not os.path.exists(video_path):
            return {
                "trust_score": 0,
                "label": "Error",
                "verdict": "Video download failed",
                "error": "No video file available"
            }
        
        print(f"\n🔍 Analyzing downloaded video...")
        print(f"   Downloaded via: {download_method}")
        print(f"   File: {video_path}")
        print(f"   Size: {os.path.getsize(video_path)} bytes")
        
        # STEP 4: Send video FILE to AIorNOT for AI detection
        print(f"\n🤖 Calling AIorNOT API with video file...")
        
        # Read the video file
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        # Call AIorNOT with the file
        aiornot_result = detect_with_aiornot(video_data, is_file=True, is_video=True)
        
        if aiornot_result:
            ai_confidence = aiornot_result["ai_confidence"]
            trust_score = int((1 - ai_confidence) * 100)
            
            label_info = get_detection_label(trust_score)
            
            print(f"\n📊 FINAL TRUST SCORE: {trust_score}/100")
            print(f"   Label: {label_info['label']}")
            print(f"   Downloaded via: {download_method}")
            print(f"{'='*80}\n")
            
            return {
                "trust_score": trust_score,
                "label": label_info["label"],
                "verdict": label_info["explanation"],
                "confidence": label_info["confidence"],
                "provider": aiornot_result["provider"],
                "download_method": download_method
            }
        else:
            # AIorNOT failed
            print(f"⚠️ AIorNOT detection unavailable")
            return {
                "trust_score": 50,
                "label": "Detection Unavailable",
                "verdict": "Video downloaded successfully but AI detection service unavailable. Please try again later.",
                "download_method": download_method
            }
    
    except Exception as e:
        print(f"\n❌ VIDEO VERIFICATION ERROR")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")
        
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"Video verification failed: {str(e)}",
            "error": str(e)
        }
    
    finally:
        # Cleanup: Delete temporary video file
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                print(f"🗑️ Cleaned up temp file: {video_path}")
            except:
                pass


@app.task(bind=True)


@app.task(bind=True)
def verify_text_task(self, text: str) -> Dict:
    """
    Complete text AI detection
    Uses: Winston AI (primary), RoBERTa (backup)
    """
    print(f"📝 Text verification started (length: {len(text)} chars)")
    
    try:
        # Try Winston AI first
        winston_result = detect_text_winston(text)
        
        if not winston_result:
            # Fallback to Hugging Face
            winston_result = detect_text_huggingface(text)
        
        if not winston_result:
            return {
                "trust_score": 50,
                "label": "Unavailable",
                "verdict": "Text AI detection unavailable"
            }
        
        ai_confidence = winston_result["ai_confidence"]
        trust_score = int((1 - ai_confidence) * 100)
        
        label_info = get_detection_label(trust_score)
        
        print(f"📊 Final score: {trust_score}/100 ({label_info['label']})")
        
        return {
            "trust_score": trust_score,
            "label": label_info["label"],
            "verdict": label_info["explanation"],
            "confidence": label_info["confidence"],
            "provider": winston_result["provider"]
        }
        
    except Exception as e:
        print(f"❌ Text verification error: {str(e)}")
        traceback.print_exc()
        return {
            "trust_score": 50,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}"
        }

@app.task(bind=True)
def verify_news_task(self, url: str) -> Dict:
    """Process news article verification - FULLY IMPLEMENTED"""
    print(f"📰 News verification task started: {url}")
    
    try:
        result = verify_news(url)
        return result
    except Exception as e:
        print(f"❌ News verification failed: {e}")
        return {
            "trust_score": 0,
            "label": "Error",
            "verdict": f"Verification failed: {str(e)}",
            "error": str(e)
        }


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 CrediSource Celery Worker Starting")
    print("="*80)
    print(f"📊 News sources in database: {len(SOURCE_CREDIBILITY)}")
    print(f"🔧 Redis URL: {REDIS_URL}")
    print(f"🔑 NewsAPI: {'✅ Configured' if NEWS_API_KEY else '❌ Not configured'}")
    print(f"\n✅ Phase 2 Safeguards Active:")
    print(f"   • Domain age checking")
    print(f"   • Suspicious pattern detection")
    print(f"   • SSL certificate validation")
    print(f"\n🎯 Ready to process verification jobs!")
    print("="*80 + "\n")
    
    # Start worker
    app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=2'
    ])
