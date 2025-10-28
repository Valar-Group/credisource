# celery_worker.py - Enhanced with Content Reasoning
# CrediSource - AI Content Verification Platform

import os
import re
from celery import Celery
from newspaper import Article
import httpx
from typing import Dict, List, Optional

# Initialize Celery
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app = Celery("credisource", broker=redis_url, backend=redis_url)

# API Keys
AIORNOT_API_KEY = os.getenv("AIORNOT_API_KEY")
WINSTON_API_KEY = os.getenv("WINSTON_API_KEY")
SIGHTENGINE_USER = os.getenv("SIGHTENGINE_USER", "1740276646")
SIGHTENGINE_SECRET = os.getenv("SIGHTENGINE_SECRET", "tBPjvP7aR8DajbWT2t2bgu2QJeP6FmvS")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "9bffad84ca1c4fd6b4f167c5a74a0cb7")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# ============================================================================
# SOURCE CREDIBILITY DATABASE (YOUR IP!)
# ============================================================================

SOURCE_CREDIBILITY = {
    # Tier 1: Highly Credible (90-100)
    "reuters.com": {"score": 98, "tier": "tier1", "bias": "center", "type": "wire_service"},
    "apnews.com": {"score": 98, "tier": "tier1", "bias": "center", "type": "wire_service"},
    "bbc.co.uk": {"score": 95, "tier": "tier1", "bias": "center", "type": "established_news"},
    "bbc.com": {"score": 95, "tier": "tier1", "bias": "center", "type": "established_news"},
    "npr.org": {"score": 92, "tier": "tier1", "bias": "center-left", "type": "established_news"},
    "economist.com": {"score": 92, "tier": "tier1", "bias": "center", "type": "established_news"},
    "theguardian.com": {"score": 90, "tier": "tier1", "bias": "center-left", "type": "established_news"},
    
    # Tier 2: Generally Credible (70-89)
    "nytimes.com": {"score": 88, "tier": "tier2", "bias": "center-left", "type": "established_news"},
    "washingtonpost.com": {"score": 88, "tier": "tier2", "bias": "center-left", "type": "established_news"},
    "wsj.com": {"score": 87, "tier": "tier2", "bias": "center-right", "type": "established_news"},
    "cnn.com": {"score": 82, "tier": "tier2", "bias": "center-left", "type": "cable_news"},
    "foxnews.com": {"score": 75, "tier": "tier2", "bias": "right", "type": "cable_news"},
    "msnbc.com": {"score": 75, "tier": "tier2", "bias": "left", "type": "cable_news"},
    "bloomberg.com": {"score": 85, "tier": "tier2", "bias": "center", "type": "business_news"},
    
    # Tier 3: Mixed Reliability (40-69)
    "dailymail.co.uk": {"score": 55, "tier": "tier3", "bias": "right", "type": "tabloid"},
    "nypost.com": {"score": 60, "tier": "tier3", "bias": "right", "type": "tabloid"},
    "thesun.co.uk": {"score": 50, "tier": "tier3", "bias": "right", "type": "tabloid"},
    "buzzfeed.com": {"score": 65, "tier": "tier3", "bias": "center-left", "type": "mixed_content"},
    
    # Tier 4: Low Credibility (0-39)
    "infowars.com": {"score": 10, "tier": "tier4", "bias": "extreme-right", "type": "conspiracy"},
    "naturalnews.com": {"score": 15, "tier": "tier4", "bias": "extreme-right", "type": "conspiracy"},
    "breitbart.com": {"score": 35, "tier": "tier4", "bias": "extreme-right", "type": "partisan"},
}

# ============================================================================
# CONTENT ANALYSIS RED FLAGS
# ============================================================================

CONTENT_RED_FLAGS = {
    "gossip_language": {
        "patterns": [
            r"\bsources?\s+(?:say|claim|reveal|told)\b",
            r"\binsiders?\s+(?:claim|say|reveal)\b",
            r"\ballegedly\b",
            r"\breportedly\b",
            r"\brumored\b",
            r"\bwhispers\b",
        ],
        "penalty": 5,
        "label": "gossip/unverified sources"
    },
    "sensational_language": {
        "patterns": [
            r"\bshocking\b",
            r"\bexplosive\b",
            r"\bbombshell\b",
            r"\bstunning\b",
            r"\bslams?\b",
            r"\bblasts?\b",
            r"\b(?:forces?|threatens?)\b",
            r"\bdevastating\b",
        ],
        "penalty": 3,
        "label": "sensational language"
    },
    "speculation": {
        "patterns": [
            r"\b(?:could|might|may)\s+have\b",
            r"\bappears?\s+to\b",
            r"\bseems?\s+to\b",
            r"\bpossibly\b",
            r"\bpotentially\b",
        ],
        "penalty": 2,
        "label": "speculative claims"
    },
    "clickbait": {
        "patterns": [
            r"\byou\s+won'?t\s+believe\b",
            r"\bwhat\s+happens?\s+next\b",
            r"\bshock(?:ing)?\b.*\b(?:revelation|truth)\b",
            r"\bthe\s+truth\s+about\b",
        ],
        "penalty": 8,
        "label": "clickbait phrasing"
    }
}

def analyze_content_quality(text: str, title: str = "") -> Dict:
    """
    Analyze article content for red flags
    Returns quality score and detailed reasoning
    """
    combined_text = f"{title} {text}".lower()
    
    red_flags_found = []
    total_penalty = 0
    flag_details = []
    
    for category, config in CONTENT_RED_FLAGS.items():
        matches = []
        for pattern in config["patterns"]:
            found = re.findall(pattern, combined_text, re.IGNORECASE)
            matches.extend(found)
        
        if matches:
            count = len(matches)
            penalty = config["penalty"] * min(count, 3)  # Cap at 3 occurrences
            total_penalty += penalty
            
            red_flags_found.append(config["label"])
            flag_details.append({
                "category": category,
                "label": config["label"],
                "count": count,
                "penalty": penalty,
                "examples": matches[:2]  # Show first 2 examples
            })
    
    # Calculate quality score (100 - penalties)
    quality_score = max(30, 100 - total_penalty)  # Minimum 30
    
    # Generate reasoning
    if red_flags_found:
        reasoning = f"Content contains: {', '.join(red_flags_found)}. "
        if total_penalty > 15:
            reasoning += "Multiple quality issues detected."
        elif total_penalty > 8:
            reasoning += "Some reliability concerns."
    else:
        reasoning = "Content appears factual with standard journalistic language."
    
    return {
        "quality_score": quality_score,
        "red_flags": red_flags_found,
        "penalty": total_penalty,
        "reasoning": reasoning,
        "details": flag_details
    }

# ============================================================================
# IMAGE SELECTION & FILTERING
# ============================================================================

def filter_article_images(images: List[str], max_images: int = 3) -> List[str]:
    """
    Filter out logos, icons, headers - keep actual article images
    """
    # Patterns to skip
    skip_patterns = [
        'logo', 'icon', 'header', 'footer', 'banner',
        'facebook', 'twitter', 'linkedin', 'instagram',
        'social', 'share', 'sitelog', 'avatar',
        'ads', 'advertisement', 'promo'
    ]
    
    # Filter images
    article_images = []
    for img in images:
        img_lower = img.lower()
        
        # Skip if matches any pattern
        if any(pattern in img_lower for pattern in skip_patterns):
            continue
        
        # Skip if tiny (likely icon)
        if any(size in img_lower for size in ['16x16', '32x32', '48x48', '64x64']):
            continue
        
        # Skip SVG files (usually logos)
        if img_lower.endswith('.svg'):
            continue
        
        article_images.append(img)
    
    # Return first N images
    return article_images[:max_images]

# ============================================================================
# IMAGE AI DETECTION (SightEngine)
# ============================================================================

async def check_image_ai_sightengine(image_url: str) -> Dict:
    """Check if image is AI-generated using SightEngine"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.sightengine.com/1.0/check.json",
                params={
                    "models": "genai",
                    "api_user": SIGHTENGINE_USER,
                    "api_secret": SIGHTENGINE_SECRET,
                    "url": image_url
                }
            )
            
            print(f"👁️ SightEngine response: {response.json()}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    ai_score = data.get("type", {}).get("ai_generated", 0)
                    human_score = int((1 - ai_score) * 100)
                    
                    print(f"✅ SightEngine: {human_score}% human ({int(ai_score * 100)}% AI)")
                    
                    return {
                        "provider": "SightEngine",
                        "ai_probability": ai_score,
                        "human_probability": 1 - ai_score,
                        "verdict": "AI-generated" if ai_score > 0.5 else "Likely human",
                        "confidence": abs(ai_score - 0.5) * 2
                    }
            
            print(f"⚠️ SightEngine error: {response.status_code}")
            print(f"⚠️ Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ SightEngine exception: {e}")
        return None

# ============================================================================
# CROSS-REFERENCE CHECKING
# ============================================================================

async def cross_reference_story(title: str, domain: str) -> Dict:
    """Cross-reference story with News API"""
    if not NEWS_API_KEY:
        return {
            "checked": False,
            "corroboration_score": 50,
            "verdict": "Cross-reference unavailable",
            "num_sources": 0
        }
    
    try:
        # Use first 100 chars of title
        query = title[:100]
        
        print(f"🔍 Cross-referencing story...")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "apiKey": NEWS_API_KEY,
                    "pageSize": 20,
                    "sortBy": "relevancy"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])
                
                # Count unique sources (excluding original domain)
                unique_sources = set()
                for article in articles:
                    source_name = article.get("source", {}).get("name", "")
                    article_domain = article.get("url", "")
                    
                    # Skip same domain
                    if domain not in article_domain:
                        unique_sources.add(source_name)
                
                num_sources = len(unique_sources)
                
                # Score based on corroboration
                if num_sources >= 5:
                    score = 95
                    verdict = "Widely corroborated"
                elif num_sources >= 3:
                    score = 80
                    verdict = "Multiple sources confirm"
                elif num_sources >= 1:
                    score = 60
                    verdict = "Some corroboration"
                else:
                    score = 10
                    verdict = "No corroborating sources found"
                
                return {
                    "checked": True,
                    "corroboration_score": score,
                    "verdict": verdict,
                    "num_sources": num_sources,
                    "reasoning": f"Found {num_sources} independent sources reporting similar story"
                }
        
        return {
            "checked": True,
            "corroboration_score": 10,
            "verdict": "Cross-reference failed",
            "num_sources": 0,
            "reasoning": "Unable to verify with external sources"
        }
        
    except Exception as e:
        print(f"❌ Cross-reference error: {e}")
        return {
            "checked": False,
            "corroboration_score": 50,
            "verdict": "Cross-reference unavailable",
            "num_sources": 0,
            "reasoning": "Cross-reference service unavailable"
        }

# ============================================================================
# NEWS VERIFICATION (MAIN FUNCTION)
# ============================================================================

async def verify_news_article(url: str) -> Dict:
    """
    Verify news article credibility
    Multi-factor: Source (50%) + Content Quality (30%) + Cross-ref (20%)
    """
    print(f"\n🗞️ Starting news verification for: {url}")
    print("=" * 60)
    
    try:
        # Extract article
        print(f"📰 Extracting article from: {url}")
        article = Article(url)
        article.download()
        article.parse()
        
        domain = article.source_url.replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        
        print(f"✅ Extracted: {len(article.text)} chars, {len(article.images)} images")
        
        # 1. Check source credibility (50% weight)
        print(f"🔍 Checking source credibility: {domain}")
        source_info = SOURCE_CREDIBILITY.get(domain, {
            "score": 50,
            "tier": "unknown",
            "bias": "unknown",
            "type": "unknown"
        })
        
        source_score = source_info["score"]
        is_known = domain in SOURCE_CREDIBILITY
        
        if is_known:
            print(f"✅ Found in database: {source_score}/100 ({source_info['tier']})")
            source_reasoning = f"{domain} is a {source_info['tier']} source ({source_info['type']}) with {source_info['bias']} bias"
        else:
            print(f"⚠️ Unknown source: {domain} (defaulting to 50/100)")
            source_reasoning = f"Unknown source. No credibility data available for {domain}"
        
        # 2. Analyze content quality (30% weight)
        print(f"📝 Analyzing content quality...")
        content_analysis = analyze_content_quality(article.text, article.title)
        content_score = content_analysis["quality_score"]
        content_reasoning = content_analysis["reasoning"]
        
        print(f"📊 Content quality: {content_score}/100")
        if content_analysis["red_flags"]:
            print(f"🚩 Red flags: {', '.join(content_analysis['red_flags'])}")
        
        # 3. Check images (included in content quality)
        filtered_images = filter_article_images(list(article.images))
        print(f"🖼️ Checking {len(filtered_images)} article images (filtered from {len(article.images)})")
        
        image_results = []
        image_scores = []
        
        for img_url in filtered_images[:3]:  # Max 3 images
            print(f"👁️ Calling SightEngine (URL)...")
            result = await check_image_ai_sightengine(img_url)
            if result:
                image_results.append({
                    "url": img_url,
                    "provider": result["provider"],
                    "verdict": result["verdict"],
                    "ai_probability": result["ai_probability"],
                    "human_probability": result["human_probability"]
                })
                # Convert to score (human probability = good)
                img_score = int(result["human_probability"] * 100)
                image_scores.append(img_score)
        
        # Average image score
        avg_image_score = int(sum(image_scores) / len(image_scores)) if image_scores else 85
        
        # Combine content text + images
        combined_content_score = int(content_score * 0.6 + avg_image_score * 0.4)
        
        # 4. Cross-reference (20% weight) - OPTIONAL
        cross_ref = await cross_reference_story(article.title, domain)
        cross_ref_score = cross_ref["corroboration_score"]
        
        # ==================================================================
        # SMART WEIGHTING: If cross-ref finds nothing, redistribute weight
        # ==================================================================
        if cross_ref["num_sources"] == 0:
            print("⚠️ Cross-reference found no sources - redistributing weight")
            # Redistribute 20% weight proportionally
            source_weight = 62.5  # 50 + (20 * 0.625)
            content_weight = 37.5  # 30 + (20 * 0.375)
            cross_ref_weight = 0
            
            final_score = int(
                (source_score * source_weight / 100) +
                (combined_content_score * content_weight / 100)
            )
        else:
            # Normal weighting
            source_weight = 50
            content_weight = 30
            cross_ref_weight = 20
            
            final_score = int(
                (source_score * 0.50) +
                (combined_content_score * 0.30) +
                (cross_ref_score * 0.20)
            )
        
        # Generate final explanation
        tier_explanations = {
            "tier1": "a highly credible, well-established news source",
            "tier2": "a generally credible news source",
            "tier3": "a mixed-reliability source (tabloid or partisan)",
            "tier4": "a low-credibility source",
            "unknown": "an unknown source with no credibility data"
        }
        
        tier_desc = tier_explanations.get(source_info["tier"], "an unknown source")
        
        explanation_parts = [
            f"This article is from {tier_desc}."
        ]
        
        # Add content quality explanation
        if content_analysis["red_flags"]:
            explanation_parts.append(f"Content analysis found: {', '.join(content_analysis['red_flags'])}.")
        else:
            explanation_parts.append("Content appears factual with standard journalistic language.")
        
        # Add cross-ref explanation
        if cross_ref["num_sources"] > 0:
            explanation_parts.append(f"Story corroborated by {cross_ref['num_sources']} independent sources.")
        elif cross_ref["checked"]:
            explanation_parts.append("No independent corroboration found.")
        
        final_explanation = " ".join(explanation_parts)
        
        # Determine label
        if final_score >= 80:
            label = "Highly Credible"
            confidence = "High"
            action = "This article appears trustworthy."
        elif final_score >= 60:
            label = "Probably Credible"
            confidence = "Moderate-High"
            action = "This article is likely credible, but verify key claims."
        elif final_score >= 40:
            label = "Mixed Reliability"
            confidence = "Moderate"
            action = "Approach with caution. Verify claims from other sources."
        else:
            label = "Low Credibility"
            confidence = "Low"
            action = "Be skeptical. Seek confirmation from credible sources."
        
        print("=" * 60)
        print(f"📊 Final News Trust Score: {final_score}/100")
        
        return {
            "trust_score": {
                "score": final_score,
                "label": label,
                "explanation": final_explanation,
                "confidence": confidence,
                "recommended_action": action,
                "scoring_factors": [
                    {
                        "factor": "Source Credibility",
                        "score": source_score,
                        "weight": f"{source_weight}%",
                        "reasoning": source_reasoning
                    },
                    {
                        "factor": "Content Quality",
                        "score": combined_content_score,
                        "weight": f"{content_weight}%",
                        "reasoning": f"{content_reasoning} Images: {avg_image_score}% authentic."
                    },
                    {
                        "factor": "Cross-Reference",
                        "score": cross_ref_score,
                        "weight": f"{cross_ref_weight}%",
                        "reasoning": cross_ref.get("reasoning", cross_ref["verdict"])
                    }
                ],
                "methodology": "Multi-factor weighted ensemble with content analysis"
            },
            "article": {
                "title": article.title,
                "domain": domain,
                "author": ", ".join(article.authors) if article.authors else None,
                "date": article.publish_date.isoformat() if article.publish_date else None,
                "word_count": len(article.text.split())
            },
            "source_credibility": {
                "known_source": is_known,
                "credibility_score": source_score,
                "bias": source_info.get("bias", "unknown"),
                "tier": source_info.get("tier", "unknown"),
                "type": source_info.get("type", "unknown"),
                "verdict": tier_desc
            },
            "content_analysis": {
                "quality_score": content_score,
                "red_flags": content_analysis["red_flags"],
                "penalty": content_analysis["penalty"],
                "details": content_analysis["details"],
                "images_checked": len(image_results),
                "image_ai_detection": image_results
            },
            "cross_reference": cross_ref,
            "metadata": {
                "provider": "CrediSource News Engine",
                "content_type": "news",
                "version": "2.0-with-reasoning"
            }
        }
        
    except Exception as e:
        print(f"❌ News verification error: {e}")
        
        # Handle specific errors
        if "401" in str(e) or "403" in str(e):
            return {
                "error": f"Access denied: {domain} blocks automated access. This is common with Reuters and other sites with strict bot detection.",
                "trust_score": {
                    "score": 0,
                    "label": "Error - Access Denied"
                },
                "recommendation": "Try accessing the article directly in your browser, or test with a different news source."
            }
        
        return {
            "error": f"Failed to verify article: {str(e)}",
            "trust_score": {
                "score": 0,
                "label": "Error"
            }
        }

# ============================================================================
# CELERY TASK
# ============================================================================

@app.task(bind=True, name="credisource.verify_content")
def verify_content(self, job_id: str, content: str, content_type: str):
    """
    Main Celery task for content verification
    
    Args:
        job_id: Unique job identifier
        content: URL for news/images/videos, or text content for text verification
        content_type: "news", "image", "video", or "text"
    """
    import asyncio
    
    print(f"🔍 Processing job {job_id} for content (type: {content_type})")
    
    if content_type == "news":
        # Content is a URL
        url = content
        print(f"📰 News URL: {url}")
        result = asyncio.run(verify_news_article(url))
        print(f"✅ Completed job {job_id}: Score {result.get('trust_score', {}).get('score', 0)}")
        return result
    
    elif content_type == "text":
        # Content is text to verify
        text = content
        print(f"📝 Text content: {len(text)} characters")
        # TODO: Implement text AI detection (Winston AI / Hugging Face)
        return {"error": "Text verification not yet updated with reasoning"}
    
    elif content_type == "image":
        # Content is image URL
        url = content
        print(f"🖼️ Image URL: {url}")
        # TODO: Implement image AI detection with reasoning
        return {"error": "Image verification not yet updated with reasoning"}
    
    elif content_type == "video":
        # Content is video URL
        url = content
        print(f"🎥 Video URL: {url}")
        # TODO: Implement video AI detection with reasoning
        return {"error": "Video verification not yet updated with reasoning"}
    
    else:
        return {"error": f"Unknown content type: {content_type}"}

if __name__ == "__main__":
    # For testing
    import asyncio
    
    test_url = "https://www.bbc.co.uk/news/articles/c1m3zm9jnl1o"
    result = asyncio.run(verify_news_article(test_url))
    
    import json
    print(json.dumps(result, indent=2))
