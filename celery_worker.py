"""
CrediSource Celery Worker - IMPROVED VERSION
- Top 50+ news sources database
- Smart cross-reference with story type detection
- Better search term extraction
- Google News backup
- Context-aware scoring
"""

import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from celery import Celery"""
CrediSource Celery Worker - IMPROVED VERSION
- Top 50+ news sources database
- Smart cross-reference with story type detection
- Better search term extraction
- Google News backup
- Context-aware scoring
"""

import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from celery import Celery
import httpx
import requests
from newspaper import Article
import feedparser

# Environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SIGHTENGINE_USER = os.getenv("SIGHTENGINE_USER")
SIGHTENGINE_SECRET = os.getenv("SIGHTENGINE_SECRET")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Initialize Celery
app = Celery('credisource', broker=REDIS_URL, backend=REDIS_URL)

# ============================================================================
# TOP 50+ NEWS SOURCES DATABASE
# ============================================================================

SOURCE_CREDIBILITY = {
    
    # TIER 1: HIGHEST CREDIBILITY (90-100)
    "reuters.com": {
        "score": 98,
        "tier": "tier1",
        "bias": "center",
        "type": "wire_service"
    },
    "apnews.com": {
        "score": 97,
        "tier": "tier1",
        "bias": "center",
        "type": "wire_service"
    },
    "bbc.com": {
        "score": 95,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    "bbc.co.uk": {
        "score": 95,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    "cbc.ca": {
        "score": 92,
        "tier": "tier1",
        "bias": "center-left",
        "type": "public_broadcaster"
    },
    "abc.net.au": {
        "score": 90,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    
    # TIER 2: HIGH CREDIBILITY (70-89)
    "nytimes.com": {
        "score": 87,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "washingtonpost.com": {
        "score": 85,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "wsj.com": {
        "score": 86,
        "tier": "tier2",
        "bias": "center-right",
        "type": "financial_news"
    },
    "usatoday.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "cnn.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-left",
        "type": "cable_news"
    },
    "cbsnews.com": {
        "score": 80,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "nbcnews.com": {
        "score": 79,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "abcnews.go.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center",
        "type": "broadcast_news"
    },
    "cnbc.com": {
        "score": 76,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "theguardian.com": {
        "score": 82,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "independent.co.uk": {
        "score": 73,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "telegraph.co.uk": {
        "score": 74,
        "tier": "tier2",
        "bias": "center-right",
        "type": "established_news"
    },
    "news.sky.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-right",
        "type": "broadcast_news"
    },
    "sky.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-right",
        "type": "broadcast_news"
    },
    "news.com.au": {
        "score": 70,
        "tier": "tier2",
        "bias": "center-right",
        "type": "tabloid_news"
    },
    "aljazeera.com": {
        "score": 74,
        "tier": "tier2",
        "bias": "center",
        "type": "international_news"
    },
    "thehindu.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "hindustantimes.com": {
        "score": 72,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "indianexpress.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "indiatoday.in": {
        "score": 70,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "ndtv.com": {
        "score": 73,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "bloomberg.com": {
        "score": 88,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "forbes.com": {
        "score": 76,
        "tier": "tier2",
        "bias": "center-right",
        "type": "business_news"
    },
    "businessinsider.com": {
        "score": 71,
        "tier": "tier2",
        "bias": "center",
        "type": "business_news"
    },
    "finance.yahoo.com": {
        "score": 70,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "livemint.com": {
        "score": 72,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    
    # TIER 3: MIXED RELIABILITY (40-69)
    "foxnews.com": {
        "score": 62,
        "tier": "tier3",
        "bias": "right",
        "type": "partisan_news"
    },
    "newsweek.com": {
        "score": 65,
        "tier": "tier3",
        "bias": "center-left",
        "type": "news_magazine"
    },
    "politico.com": {
        "score": 68,
        "tier": "tier3",
        "bias": "center-left",
        "type": "political_news"
    },
    "nypost.com": {
        "score": 52,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "dailymail.co.uk": {
        "score": 55,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "thesun.co.uk": {
        "score": 48,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "mirror.co.uk": {
        "score": 50,
        "tier": "tier3",
        "bias": "left",
        "type": "tabloid"
    },
    "buzzfeed.com": {
        "score": 58,
        "tier": "tier3",
        "bias": "center-left",
        "type": "digital_news"
    },
    "people.com": {
        "score": 45,
        "tier": "tier3",
        "bias": "center",
        "type": "entertainment"
    },
    "indiatimes.com": {
        "score": 58,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "news18.com": {
        "score": 60,
        "tier": "tier3",
        "bias": "center-right",
        "type": "news_portal"
    },
    "oneindia.com": {
        "score": 55,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "india.com": {
        "score": 52,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "rediff.com": {
        "score": 54,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "substack.com": {
        "score": 60,
        "tier": "tier3",
        "bias": "varies",
        "type": "platform"
    },
    
    # TIER 4: LOW CREDIBILITY (0-39)
    "rt.com": {
        "score": 25,
        "tier": "tier4",
        "bias": "extreme-right",
        "type": "state_propaganda"
    },
    "drudgereport.com": {
        "score": 38,
        "tier": "tier4",
        "bias": "right",
        "type": "aggregator"
    },
    
    # AGGREGATORS (Special handling)
    "news.yahoo.com": {
        "score": 65,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
    "msn.com": {
        "score": 65,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
    "news.google.com": {
        "score": 70,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
}

# ============================================================================
# RED FLAG PATTERNS
# ============================================================================

RED_FLAG_PATTERNS = {
    "gossip": {
        "patterns": [
            r"sources? (?:say|claim|tell|told)",
            r"insiders? (?:say|claim|reveal)",
            r"according to (?:sources?|insiders?)",
            r"rumor(?:s|ed)?",
            r"allegedly",
            r"unconfirmed",
        ],
        "penalty": 15,
        "label": "gossip/unverified sources"
    },
    "sensational": {
        "patterns": [
            r"shocking",
            r"explosive",
            r"bombshell",
            r"jaw-dropping",
            r"stunning",
            r"unbelievable",
        ],
        "penalty": 6,
        "label": "sensational language"
    },
    "speculation": {
        "patterns": [
            r"may have",
            r"could be",
            r"might be",
            r"possibly",
            r"potentially",
            r"speculation",
        ],
        "penalty": 4,
        "label": "speculative claims"
    },
    "clickbait": {
        "patterns": [
            r"you (?:won't believe|need to see)",
            r"what happens next",
            r"will shock you",
            r"the truth about",
        ],
        "penalty": 10,
        "label": "clickbait"
    },
    "anonymous": {
        "patterns": [
            r"anonymous (?:official|source)",
            r"undisclosed source",
            r"we have learned",
            r"exclusive report",
        ],
        "penalty": 8,
        "label": "vague attribution"
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Remove www.
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def get_source_credibility(domain: str, has_corroboration: bool = False) -> Dict:
    """
    Check source credibility from database
    IMPROVED: Penalize unknown sources without corroboration
    """
    
    if domain in SOURCE_CREDIBILITY:
        source = SOURCE_CREDIBILITY[domain]
        
        verdict = f"a {source['tier']} source ({source['type']}) with {source['bias']} bias"
        if source['tier'] == 'tier1':
            verdict = "a highly credible, well-established news source"
        
        return {
            "known_source": True,
            "credibility_score": source["score"],
            "bias": source["bias"],
            "tier": source["tier"],
            "type": source["type"],
            "verdict": verdict
        }
    
    # CRITICAL: Unknown source without corroboration is suspicious!
    if has_corroboration:
        score = 60
        verdict = "an unknown source (corroborated by other sources)"
    else:
        score = 35  # Harsh penalty!
        verdict = "an unknown source (NOT corroborated - highly suspicious)"
    
    return {
        "known_source": False,
        "credibility_score": score,
        "bias": "unknown",
        "tier": "unknown",
        "type": "unknown",
        "verdict": verdict
    }


def analyze_content_quality(text: str, images: List[str]) -> Dict:
    """Analyze content for red flags and check images"""
    
    red_flags = []
    total_penalty = 0
    details = []
    
    text_lower = text.lower()
    
    # Check each red flag pattern
    for flag_type, config in RED_FLAG_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower):
                red_flags.append(config["label"])
                total_penalty += config["penalty"]
                details.append(f"Found {config['label']}: matched pattern '{pattern}'")
                break  # Only count once per flag type
    
    # Check images for AI generation
    image_scores = []
    if images and SIGHTENGINE_USER and SIGHTENGINE_SECRET:
        for img_url in images[:3]:  # Max 3 images
            try:
                response = requests.get(
                    'https://api.sightengine.com/1.0/check.json',
                    params={
                        'url': img_url,
                        'models': 'genai',
                        'api_user': SIGHTENGINE_USER,
                        'api_secret': SIGHTENGINE_SECRET
                    },
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'type' in data and 'ai_generated' in data['type']:
                        ai_prob = data['type']['ai_generated']
                        human_prob = 100 - ai_prob
                        image_scores.append(human_prob)
                        details.append(f"Image analysis: {human_prob:.0f}% authentic")
            except:
                pass
    
    # Calculate quality score
    base_score = 100
    content_score = max(0, base_score - total_penalty)
    
    # Average in image scores if available
    if image_scores:
        avg_image_score = sum(image_scores) / len(image_scores)
        content_score = (content_score + avg_image_score) / 2
    
    reasoning = f"Content appears {'factual with standard journalistic language' if content_score >= 80 else 'to have quality issues'}."
    if red_flags:
        reasoning += f" Content contains: {', '.join(set(red_flags))}."
    if image_scores:
        reasoning += f" Images: {int(sum(image_scores)/len(image_scores))}% authentic."
    
    return {
        "quality_score": int(content_score),
        "red_flags": list(set(red_flags)),
        "penalty": total_penalty,
        "details": details,
        "reasoning": reasoning
    }


def extract_search_terms(title: str, content: str) -> str:
    """
    Extract key search terms for cross-reference
    IMPROVED: Smart extraction instead of full title
    """
    
    text = f"{title} {content[:500]}"
    important_terms = []
    
    # Extract capitalized words (likely proper nouns)
    words = text.split()
    for word in words:
        # Skip common words
        if word.lower() in ['the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'live', 'news']:
            continue
        
        # If starts with capital and >3 chars, it's likely important
        if word and word[0].isupper() and len(word) > 3:
            clean_word = word.strip('.,;:!?"\'')
            if clean_word and clean_word.lower() not in ['live', 'news', 'report', 'says', 'video']:
                important_terms.append(clean_word)
    
    # Remove duplicates, keep top 5
    unique_terms = list(dict.fromkeys(important_terms))[:5]
    search_query = ' '.join(unique_terms)
    
    return search_query if search_query else title[:100]


def classify_story_type(content: str, title: str) -> str:
    """
    Classify story type for context-aware scoring
    """
    
    text = (title + " " + content).lower()
    
    # Major breaking news signals
    major_signals = [
        "president", "prime minister", "election", "resign",
        "earthquake", "hurricane", "attack", "explosion",
        "crash", "disaster", "stock market crash"
    ]
    if any(signal in text for signal in major_signals):
        return "major_breaking"
    
    # Exclusive/investigative signals
    exclusive_signals = [
        "exclusive", "investigation", "obtained documents",
        "uncovered", "reveals for the first time", "whistleblower"
    ]
    if any(signal in text for signal in exclusive_signals):
        return "investigative_exclusive"
    
    # Local news signals
    local_signals = [
        "city council", "local", "town", "community",
        "school board", "county", "neighborhood"
    ]
    if any(signal in text for signal in local_signals):
        return "local_news"
    
    # Opinion signals
    opinion_signals = [
        "opinion", "editorial", "commentary", "op-ed",
        "i believe", "i think", "my view"
    ]
    if any(signal in text for signal in opinion_signals):
        return "opinion"
    
    return "standard"


def cross_reference_via_newsapi(search_query: str, domain: str) -> Dict:
    """Cross-reference using NewsAPI"""
    
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": search_query,
            "apiKey": NEWS_API_KEY,
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": 20,
            "from": (datetime.now() - timedelta(days=7)).isoformat(),
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ NewsAPI HTTP {response.status_code}: {response.text[:200]}")
            return {"sources_found": 0, "score": 10, "sources": []}
        
        data = response.json()
        
        if data.get("status") == "error":
            print(f"❌ NewsAPI error: {data.get('message')}")
            print(f"   Code: {data.get('code')}")
            return {"sources_found": 0, "score": 10, "sources": []}
        
        articles = data.get("articles", [])
        print(f"   NewsAPI returned {len(articles)} articles")
        
        # Filter out same domain
        base_domain = domain.split('.')[-2] if '.' in domain else domain
        unique_sources = set()
        
        for article in articles:
            article_domain = article.get("source", {}).get("name", "")
            article_url = article.get("url", "")
            
            if base_domain.lower() not in article_url.lower():
                unique_sources.add(article_domain)
        
        num_sources = len(unique_sources)
        
        # Score based on number
        if num_sources >= 5:
            score = 95
        elif num_sources >= 3:
            score = 85
        elif num_sources >= 2:
            score = 70
        elif num_sources == 1:
            score = 50
        else:
            score = 10
        
        return {
            "sources_found": num_sources,
            "score": score,
            "sources": list(unique_sources)[:10]
        }
        
    except Exception as e:
        print(f"❌ NewsAPI exception: {str(e)}")
        return {"sources_found": 0, "score": 10, "sources": []}


def cross_reference_via_google_news(search_query: str) -> Dict:
    """
    Backup cross-reference using Google News RSS
    FREE, no API key needed!
    """
    
    try:
        # URL encode the search query
        encoded_query = quote_plus(search_query)
        
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        unique_sources = set()
        for entry in feed.entries[:20]:
            source = entry.get('source', {}).get('title', '')
            if source:
                unique_sources.add(source)
        
        num_sources = len(unique_sources)
        
        return {
            "sources_found": num_sources,
            "score": min(num_sources * 20, 100),
            "sources": list(unique_sources)
        }
        
    except Exception as e:
        print(f"❌ Google News error: {str(e)}")
        return {"sources_found": 0, "score": 10, "sources": []}


def smart_cross_reference(title: str, content: str, domain: str, source_tier: str) -> Dict:
    """
    SMART cross-reference with story type detection and context-aware scoring
    """
    
    # Classify story type
    story_type = classify_story_type(content, title)
    
    # Extract smart search terms
    search_query = extract_search_terms(title, content)
    
    print(f"🔍 Cross-reference:")
    print(f"   Story type: {story_type}")
    print(f"   Search: '{search_query}'")
    
    # Try NewsAPI first
    result = cross_reference_via_newsapi(search_query, domain)
    
    # If no results, try Google News backup
    if result["sources_found"] == 0:
        print("⚠️ NewsAPI found nothing, trying Google News...")
        result = cross_reference_via_google_news(search_query)
    
    num_sources = result["sources_found"]
    print(f"   Found: {num_sources} sources")
    if result.get("sources"):
        print(f"   Sources: {', '.join(result['sources'][:5])}")
    
    # Score based on story type
    if story_type == "major_breaking":
        # Major news MUST be corroborated
        if num_sources >= 5:
            score = 95
            reasoning = f"Major news story corroborated by {num_sources} independent sources"
        elif num_sources >= 3:
            score = 85
            reasoning = f"Major news story corroborated by {num_sources} sources"
        elif num_sources >= 1:
            score = 50
            reasoning = f"Major news with limited corroboration ({num_sources} source)"
        else:
            score = 15
            reasoning = "⚠️ Major news claim with NO corroboration - highly suspicious!"
        weight = "30%"
        
    elif story_type == "investigative_exclusive":
        # Exclusives don't need corroboration - trust the source
        if source_tier == "tier1":
            score = 90
            reasoning = "Exclusive investigation by tier1 source"
        elif source_tier == "tier2":
            score = 75
            reasoning = "Exclusive investigation by tier2 source"
        elif source_tier == "tier3":
            score = 45
            reasoning = "Exclusive claim by tier3 source"
        else:
            score = 25
            reasoning = "Exclusive claim by unknown source"
        weight = "15%"
        
    elif story_type == "local_news":
        # Local news won't have national coverage
        if source_tier in ["tier1", "tier2"]:
            score = 80
            reasoning = "Local story from credible source (corroboration not expected)"
        elif source_tier == "tier3":
            score = 60
            reasoning = "Local story from known source"
        else:
            score = 50
            reasoning = "Local story from unknown source"
        weight = "10%"
        
    elif story_type == "opinion":
        # Opinions don't need corroboration
        if source_tier in ["tier1", "tier2"]:
            score = 85
            reasoning = "Opinion piece from credible outlet (subjective content)"
        elif source_tier == "tier3":
            score = 60
            reasoning = "Opinion piece from known outlet"
        else:
            score = 50
            reasoning = "Opinion piece from unknown source"
        weight = "5%"
        
    else:  # standard
        # Standard news - moderate corroboration expectation
        if num_sources >= 3:
            score = 85
            reasoning = f"Story corroborated by {num_sources} independent sources"
        elif num_sources >= 1:
            score = 65
            reasoning = f"Story corroborated by {num_sources} other source"
        else:
            if source_tier in ["tier1", "tier2"]:
                score = 55
                reasoning = "No corroboration found, but source is credible"
            elif source_tier == "tier3":
                score = 35
                reasoning = "No corroboration from lower-tier source"
            else:
                score = 20
                reasoning = "No corroboration from unknown source"
        weight = "25%"
    
    return {
        "score": score,
        "weight": weight,
        "reasoning": reasoning,
        "story_type": story_type,
        "sources_found": num_sources,
        "sources": result.get("sources", [])
    }


def calculate_final_score(source_cred: Dict, content_qual: Dict, cross_ref: Dict) -> Dict:
    """
    Calculate final weighted score with dynamic weights based on story type
    """
    
    story_type = cross_ref.get("story_type", "standard")
    
    # Dynamic weights based on story type
    if story_type == "major_breaking":
        weights = {"source": 0.35, "content": 0.35, "cross_ref": 0.30}
    elif story_type == "investigative_exclusive":
        weights = {"source": 0.60, "content": 0.25, "cross_ref": 0.15}
    elif story_type == "local_news":
        weights = {"source": 0.50, "content": 0.40, "cross_ref": 0.10}
    elif story_type == "opinion":
        weights = {"source": 0.55, "content": 0.40, "cross_ref": 0.05}
    else:  # standard
        weights = {"source": 0.40, "content": 0.35, "cross_ref": 0.25}
    
    final = (
        source_cred["credibility_score"] * weights["source"] +
        content_qual["quality_score"] * weights["content"] +
        cross_ref["score"] * weights["cross_ref"]
    )
    
    score = round(final)
    
    # Determine label
    if score >= 90:
        label = "Highly Credible"
    elif score >= 70:
        label = "Credible"
    elif score >= 50:
        label = "Probably Credible"
    elif score >= 30:
        label = "Mixed Reliability"
    else:
        label = "Low Credibility"
    
    # Generate explanation
    explanation = f"This article is from {source_cred['verdict']}."
    if content_qual['red_flags']:
        explanation += f" Content quality issues detected: {', '.join(content_qual['red_flags'])}."
    if cross_ref['sources_found'] > 0:
        explanation += f" Story is corroborated by {cross_ref['sources_found']} independent sources."
    elif story_type in ["investigative_exclusive", "local_news", "opinion"]:
        explanation += f" As a {story_type.replace('_', ' ')}, corroboration is not expected."
    else:
        explanation += " No independent corroboration found."
    
    return {
        "score": score,
        "label": label,
        "explanation": explanation,
        "confidence": "High" if source_cred["known_source"] else "Moderate",
        "recommended_action": "Trust with caution and verify key claims" if score >= 50 else "Verify from multiple trusted sources before sharing",
        "methodology": f"Multi-factor weighted ensemble (Source: {weights['source']*100:.0f}%, Content: {weights['content']*100:.0f}%, Cross-ref: {weights['cross_ref']*100:.0f}%)",
        "scoring_factors": [
            {
                "factor": "Source Credibility",
                "score": source_cred["credibility_score"],
                "weight": f"{weights['source']*100:.0f}%",
                "reasoning": f"{source_cred['verdict']}"
            },
            {
                "factor": "Content Quality",
                "score": content_qual["quality_score"],
                "weight": f"{weights['content']*100:.0f}%",
                "reasoning": content_qual["reasoning"]
            },
            {
                "factor": "Cross-Reference",
                "score": cross_ref["score"],
                "weight": f"{weights['cross_ref']*100:.0f}%",
                "reasoning": cross_ref["reasoning"]
            }
        ]
    }


# ============================================================================
# CELERY TASK
# ============================================================================

@app.task(bind=True, name='credisource.verify_content')
def verify_news_article(self, job_id: str, url: str, content_type: str) -> Dict:
    """
    Main verification task
    Registered as 'credisource.verify_content' for compatibility with main.py
    Args:
        job_id: Job identifier
        url: URL to verify
        content_type: Type of content (news, image, video, text)
    """
    
    print(f"\n{'='*60}")
    print(f"🔍 VERIFYING: {url}")
    print(f"📋 Job ID: {job_id}")
    print(f"📌 Content Type: {content_type}")
    print(f"{'='*60}\n")
    
    # Only handle news for now
    if content_type != 'news':
        print(f"⚠️ Content type '{content_type}' not supported in new system yet")
        return {
            "error": f"Content type '{content_type}' not implemented",
            "trust_score": {
                "score": 0,
                "label": "Unsupported",
                "explanation": "Only 'news' content type is currently supported"
            }
        }
    
    try:
        # Extract article
        article = Article(url)
        article.download()
        article.parse()
        
        domain = extract_domain(url)
        word_count = len(article.text.split())
        article_images = article.images if hasattr(article, 'images') else []
        
        print(f"📰 Title: {article.title}")
        print(f"🌐 Domain: {domain}")
        print(f"📝 Word count: {word_count}\n")
        
        # 1. Check source credibility (we'll update after cross-ref)
        print("1️⃣ CHECKING SOURCE CREDIBILITY...")
        source_cred_initial = get_source_credibility(domain, False)
        print(f"   Score: {source_cred_initial['credibility_score']}/100")
        print(f"   Tier: {source_cred_initial['tier']}")
        print(f"   Assessment: {source_cred_initial['verdict']}\n")
        
        # 2. Analyze content quality
        print("2️⃣ ANALYZING CONTENT QUALITY...")
        content_analysis = analyze_content_quality(article.text, list(article_images)[:3])
        print(f"   Score: {content_analysis['quality_score']}/100")
        print(f"   Red flags: {len(content_analysis['red_flags'])}")
        if content_analysis['red_flags']:
            for flag in content_analysis['red_flags']:
                print(f"      🚩 {flag}")
        print()
        
        # 3. Cross-reference (smart)
        print("3️⃣ CROSS-REFERENCING STORY...")
        cross_ref = smart_cross_reference(
            article.title,
            article.text,
            domain,
            source_cred_initial['tier']
        )
        print()
        
        # Update source credibility with corroboration info
        has_corroboration = cross_ref['sources_found'] > 0
        source_cred = get_source_credibility(domain, has_corroboration)
        
        # 4. Calculate final score
        print("4️⃣ CALCULATING FINAL SCORE...")
        trust_score = calculate_final_score(source_cred, content_analysis, cross_ref)
        print(f"   Final Score: {trust_score['score']}/100")
        print(f"   Label: {trust_score['label']}")
        print(f"   Story Type: {cross_ref['story_type']}\n")
        
        # Build result
        result = {
            "trust_score": trust_score,
            "source_credibility": {
                "domain": domain,
                "tier": source_cred["tier"],
                "bias": source_cred["bias"],
                "type": source_cred["type"],
                "verdict": source_cred["verdict"]
            },
            "content_analysis": {
                "red_flags": content_analysis["red_flags"],
                "details": content_analysis["details"]
            },
            "cross_reference": {
                "sources_found": cross_ref["sources_found"],
                "sources": cross_ref.get("sources", [])[:5],
                "story_type": cross_ref["story_type"]
            },
            "article": {
                "title": article.title,
                "author": article.authors[0] if article.authors else "Unknown",
                "domain": domain,
                "word_count": word_count
            }
        }
        
        print("✅ Verification complete!\n")
        return result
        
    except Exception as e:
        print(f"❌ Error: {str(e)}\n")
        return {
            "error": str(e),
            "trust_score": {
                "score": 0,
                "label": "Error",
                "explanation": f"Failed to verify article: {str(e)}"
            }
        }


if __name__ == "__main__":
    print("Celery worker ready!")
    print(f"Sources in database: {len(SOURCE_CREDIBILITY)}")
    print("Ready to verify news articles! 🚀")
import httpx
import requests
from newspaper import Article
import feedparser

# Environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SIGHTENGINE_USER = os.getenv("SIGHTENGINE_USER")
SIGHTENGINE_SECRET = os.getenv("SIGHTENGINE_SECRET")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Initialize Celery
app = Celery('credisource', broker=REDIS_URL, backend=REDIS_URL)

# ============================================================================
# TOP 50+ NEWS SOURCES DATABASE
# ============================================================================

SOURCE_CREDIBILITY = {
    
    # TIER 1: HIGHEST CREDIBILITY (90-100)
    "reuters.com": {
        "score": 98,
        "tier": "tier1",
        "bias": "center",
        "type": "wire_service"
    },
    "apnews.com": {
        "score": 97,
        "tier": "tier1",
        "bias": "center",
        "type": "wire_service"
    },
    "bbc.com": {
        "score": 95,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    "bbc.co.uk": {
        "score": 95,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    "cbc.ca": {
        "score": 92,
        "tier": "tier1",
        "bias": "center-left",
        "type": "public_broadcaster"
    },
    "abc.net.au": {
        "score": 90,
        "tier": "tier1",
        "bias": "center",
        "type": "public_broadcaster"
    },
    
    # TIER 2: HIGH CREDIBILITY (70-89)
    "nytimes.com": {
        "score": 87,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "washingtonpost.com": {
        "score": 85,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "wsj.com": {
        "score": 86,
        "tier": "tier2",
        "bias": "center-right",
        "type": "financial_news"
    },
    "usatoday.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "cnn.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-left",
        "type": "cable_news"
    },
    "cbsnews.com": {
        "score": 80,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "nbcnews.com": {
        "score": 79,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "abcnews.go.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center",
        "type": "broadcast_news"
    },
    "cnbc.com": {
        "score": 76,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "theguardian.com": {
        "score": 82,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "independent.co.uk": {
        "score": 73,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "telegraph.co.uk": {
        "score": 74,
        "tier": "tier2",
        "bias": "center-right",
        "type": "established_news"
    },
    "news.sky.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-right",
        "type": "broadcast_news"
    },
    "sky.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-right",
        "type": "broadcast_news"
    },
    "news.com.au": {
        "score": 70,
        "tier": "tier2",
        "bias": "center-right",
        "type": "tabloid_news"
    },
    "aljazeera.com": {
        "score": 74,
        "tier": "tier2",
        "bias": "center",
        "type": "international_news"
    },
    "thehindu.com": {
        "score": 78,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "hindustantimes.com": {
        "score": 72,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "indianexpress.com": {
        "score": 75,
        "tier": "tier2",
        "bias": "center-left",
        "type": "established_news"
    },
    "indiatoday.in": {
        "score": 70,
        "tier": "tier2",
        "bias": "center",
        "type": "established_news"
    },
    "ndtv.com": {
        "score": 73,
        "tier": "tier2",
        "bias": "center-left",
        "type": "broadcast_news"
    },
    "bloomberg.com": {
        "score": 88,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "forbes.com": {
        "score": 76,
        "tier": "tier2",
        "bias": "center-right",
        "type": "business_news"
    },
    "businessinsider.com": {
        "score": 71,
        "tier": "tier2",
        "bias": "center",
        "type": "business_news"
    },
    "finance.yahoo.com": {
        "score": 70,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    "livemint.com": {
        "score": 72,
        "tier": "tier2",
        "bias": "center",
        "type": "financial_news"
    },
    
    # TIER 3: MIXED RELIABILITY (40-69)
    "foxnews.com": {
        "score": 62,
        "tier": "tier3",
        "bias": "right",
        "type": "partisan_news"
    },
    "newsweek.com": {
        "score": 65,
        "tier": "tier3",
        "bias": "center-left",
        "type": "news_magazine"
    },
    "politico.com": {
        "score": 68,
        "tier": "tier3",
        "bias": "center-left",
        "type": "political_news"
    },
    "nypost.com": {
        "score": 52,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "dailymail.co.uk": {
        "score": 55,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "thesun.co.uk": {
        "score": 48,
        "tier": "tier3",
        "bias": "right",
        "type": "tabloid"
    },
    "mirror.co.uk": {
        "score": 50,
        "tier": "tier3",
        "bias": "left",
        "type": "tabloid"
    },
    "buzzfeed.com": {
        "score": 58,
        "tier": "tier3",
        "bias": "center-left",
        "type": "digital_news"
    },
    "people.com": {
        "score": 45,
        "tier": "tier3",
        "bias": "center",
        "type": "entertainment"
    },
    "indiatimes.com": {
        "score": 58,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "news18.com": {
        "score": 60,
        "tier": "tier3",
        "bias": "center-right",
        "type": "news_portal"
    },
    "oneindia.com": {
        "score": 55,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "india.com": {
        "score": 52,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "rediff.com": {
        "score": 54,
        "tier": "tier3",
        "bias": "center",
        "type": "news_portal"
    },
    "substack.com": {
        "score": 60,
        "tier": "tier3",
        "bias": "varies",
        "type": "platform"
    },
    
    # TIER 4: LOW CREDIBILITY (0-39)
    "rt.com": {
        "score": 25,
        "tier": "tier4",
        "bias": "extreme-right",
        "type": "state_propaganda"
    },
    "drudgereport.com": {
        "score": 38,
        "tier": "tier4",
        "bias": "right",
        "type": "aggregator"
    },
    
    # AGGREGATORS (Special handling)
    "news.yahoo.com": {
        "score": 65,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
    "msn.com": {
        "score": 65,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
    "news.google.com": {
        "score": 70,
        "tier": "aggregator",
        "bias": "varies",
        "type": "aggregator"
    },
}

# ============================================================================
# RED FLAG PATTERNS
# ============================================================================

RED_FLAG_PATTERNS = {
    "gossip": {
        "patterns": [
            r"sources? (?:say|claim|tell|told)",
            r"insiders? (?:say|claim|reveal)",
            r"according to (?:sources?|insiders?)",
            r"rumor(?:s|ed)?",
            r"allegedly",
            r"unconfirmed",
        ],
        "penalty": 15,
        "label": "gossip/unverified sources"
    },
    "sensational": {
        "patterns": [
            r"shocking",
            r"explosive",
            r"bombshell",
            r"jaw-dropping",
            r"stunning",
            r"unbelievable",
        ],
        "penalty": 6,
        "label": "sensational language"
    },
    "speculation": {
        "patterns": [
            r"may have",
            r"could be",
            r"might be",
            r"possibly",
            r"potentially",
            r"speculation",
        ],
        "penalty": 4,
        "label": "speculative claims"
    },
    "clickbait": {
        "patterns": [
            r"you (?:won't believe|need to see)",
            r"what happens next",
            r"will shock you",
            r"the truth about",
        ],
        "penalty": 10,
        "label": "clickbait"
    },
    "anonymous": {
        "patterns": [
            r"anonymous (?:official|source)",
            r"undisclosed source",
            r"we have learned",
            r"exclusive report",
        ],
        "penalty": 8,
        "label": "vague attribution"
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Remove www.
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def get_source_credibility(domain: str, has_corroboration: bool = False) -> Dict:
    """
    Check source credibility from database
    IMPROVED: Penalize unknown sources without corroboration
    """
    
    if domain in SOURCE_CREDIBILITY:
        source = SOURCE_CREDIBILITY[domain]
        
        verdict = f"a {source['tier']} source ({source['type']}) with {source['bias']} bias"
        if source['tier'] == 'tier1':
            verdict = "a highly credible, well-established news source"
        
        return {
            "known_source": True,
            "credibility_score": source["score"],
            "bias": source["bias"],
            "tier": source["tier"],
            "type": source["type"],
            "verdict": verdict
        }
    
    # CRITICAL: Unknown source without corroboration is suspicious!
    if has_corroboration:
        score = 60
        verdict = "an unknown source (corroborated by other sources)"
    else:
        score = 35  # Harsh penalty!
        verdict = "an unknown source (NOT corroborated - highly suspicious)"
    
    return {
        "known_source": False,
        "credibility_score": score,
        "bias": "unknown",
        "tier": "unknown",
        "type": "unknown",
        "verdict": verdict
    }


def analyze_content_quality(text: str, images: List[str]) -> Dict:
    """Analyze content for red flags and check images"""
    
    red_flags = []
    total_penalty = 0
    details = []
    
    text_lower = text.lower()
    
    # Check each red flag pattern
    for flag_type, config in RED_FLAG_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower):
                red_flags.append(config["label"])
                total_penalty += config["penalty"]
                details.append(f"Found {config['label']}: matched pattern '{pattern}'")
                break  # Only count once per flag type
    
    # Check images for AI generation
    image_scores = []
    if images and SIGHTENGINE_USER and SIGHTENGINE_SECRET:
        for img_url in images[:3]:  # Max 3 images
            try:
                response = requests.get(
                    'https://api.sightengine.com/1.0/check.json',
                    params={
                        'url': img_url,
                        'models': 'genai',
                        'api_user': SIGHTENGINE_USER,
                        'api_secret': SIGHTENGINE_SECRET
                    },
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'type' in data and 'ai_generated' in data['type']:
                        ai_prob = data['type']['ai_generated']
                        human_prob = 100 - ai_prob
                        image_scores.append(human_prob)
                        details.append(f"Image analysis: {human_prob:.0f}% authentic")
            except:
                pass
    
    # Calculate quality score
    base_score = 100
    content_score = max(0, base_score - total_penalty)
    
    # Average in image scores if available
    if image_scores:
        avg_image_score = sum(image_scores) / len(image_scores)
        content_score = (content_score + avg_image_score) / 2
    
    reasoning = f"Content appears {'factual with standard journalistic language' if content_score >= 80 else 'to have quality issues'}."
    if red_flags:
        reasoning += f" Content contains: {', '.join(set(red_flags))}."
    if image_scores:
        reasoning += f" Images: {int(sum(image_scores)/len(image_scores))}% authentic."
    
    return {
        "quality_score": int(content_score),
        "red_flags": list(set(red_flags)),
        "penalty": total_penalty,
        "details": details,
        "reasoning": reasoning
    }


def extract_search_terms(title: str, content: str) -> str:
    """
    Extract key search terms for cross-reference
    IMPROVED: Smart extraction instead of full title
    """
    
    text = f"{title} {content[:500]}"
    important_terms = []
    
    # Extract capitalized words (likely proper nouns)
    words = text.split()
    for word in words:
        # Skip common words
        if word.lower() in ['the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'live', 'news']:
            continue
        
        # If starts with capital and >3 chars, it's likely important
        if word and word[0].isupper() and len(word) > 3:
            clean_word = word.strip('.,;:!?"\'')
            if clean_word and clean_word.lower() not in ['live', 'news', 'report', 'says', 'video']:
                important_terms.append(clean_word)
    
    # Remove duplicates, keep top 5
    unique_terms = list(dict.fromkeys(important_terms))[:5]
    search_query = ' '.join(unique_terms)
    
    return search_query if search_query else title[:100]


def classify_story_type(content: str, title: str) -> str:
    """
    Classify story type for context-aware scoring
    """
    
    text = (title + " " + content).lower()
    
    # Major breaking news signals
    major_signals = [
        "president", "prime minister", "election", "resign",
        "earthquake", "hurricane", "attack", "explosion",
        "crash", "disaster", "stock market crash"
    ]
    if any(signal in text for signal in major_signals):
        return "major_breaking"
    
    # Exclusive/investigative signals
    exclusive_signals = [
        "exclusive", "investigation", "obtained documents",
        "uncovered", "reveals for the first time", "whistleblower"
    ]
    if any(signal in text for signal in exclusive_signals):
        return "investigative_exclusive"
    
    # Local news signals
    local_signals = [
        "city council", "local", "town", "community",
        "school board", "county", "neighborhood"
    ]
    if any(signal in text for signal in local_signals):
        return "local_news"
    
    # Opinion signals
    opinion_signals = [
        "opinion", "editorial", "commentary", "op-ed",
        "i believe", "i think", "my view"
    ]
    if any(signal in text for signal in opinion_signals):
        return "opinion"
    
    return "standard"


def cross_reference_via_newsapi(search_query: str, domain: str) -> Dict:
    """Cross-reference using NewsAPI"""
    
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": search_query,
            "apiKey": NEWS_API_KEY,
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": 20,
            "from": (datetime.now() - timedelta(days=7)).isoformat(),
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ NewsAPI error: {response.status_code}")
            return {"sources_found": 0, "score": 10, "sources": []}
        
        data = response.json()
        
        if data.get("status") == "error":
            print(f"❌ NewsAPI error: {data.get('message')}")
            return {"sources_found": 0, "score": 10, "sources": []}
        
        articles = data.get("articles", [])
        
        # Filter out same domain
        base_domain = domain.split('.')[-2] if '.' in domain else domain
        unique_sources = set()
        
        for article in articles:
            article_domain = article.get("source", {}).get("name", "")
            article_url = article.get("url", "")
            
            if base_domain.lower() not in article_url.lower():
                unique_sources.add(article_domain)
        
        num_sources = len(unique_sources)
        
        # Score based on number
        if num_sources >= 5:
            score = 95
        elif num_sources >= 3:
            score = 85
        elif num_sources >= 2:
            score = 70
        elif num_sources == 1:
            score = 50
        else:
            score = 10
        
        return {
            "sources_found": num_sources,
            "score": score,
            "sources": list(unique_sources)[:10]
        }
        
    except Exception as e:
        print(f"❌ NewsAPI exception: {str(e)}")
        return {"sources_found": 0, "score": 10, "sources": []}


def cross_reference_via_google_news(search_query: str) -> Dict:
    """
    Backup cross-reference using Google News RSS
    FREE, no API key needed!
    """
    
    try:
        url = f"https://news.google.com/rss/search?q={search_query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        unique_sources = set()
        for entry in feed.entries[:20]:
            source = entry.get('source', {}).get('title', '')
            if source:
                unique_sources.add(source)
        
        num_sources = len(unique_sources)
        
        return {
            "sources_found": num_sources,
            "score": min(num_sources * 20, 100),
            "sources": list(unique_sources)
        }
        
    except Exception as e:
        print(f"❌ Google News error: {str(e)}")
        return {"sources_found": 0, "score": 10, "sources": []}


def smart_cross_reference(title: str, content: str, domain: str, source_tier: str) -> Dict:
    """
    SMART cross-reference with story type detection and context-aware scoring
    """
    
    # Classify story type
    story_type = classify_story_type(content, title)
    
    # Extract smart search terms
    search_query = extract_search_terms(title, content)
    
    print(f"🔍 Cross-reference:")
    print(f"   Story type: {story_type}")
    print(f"   Search: '{search_query}'")
    
    # Try NewsAPI first
    result = cross_reference_via_newsapi(search_query, domain)
    
    # If no results, try Google News backup
    if result["sources_found"] == 0:
        print("⚠️ NewsAPI found nothing, trying Google News...")
        result = cross_reference_via_google_news(search_query)
    
    num_sources = result["sources_found"]
    print(f"   Found: {num_sources} sources")
    if result.get("sources"):
        print(f"   Sources: {', '.join(result['sources'][:5])}")
    
    # Score based on story type
    if story_type == "major_breaking":
        # Major news MUST be corroborated
        if num_sources >= 5:
            score = 95
            reasoning = f"Major news story corroborated by {num_sources} independent sources"
        elif num_sources >= 3:
            score = 85
            reasoning = f"Major news story corroborated by {num_sources} sources"
        elif num_sources >= 1:
            score = 50
            reasoning = f"Major news with limited corroboration ({num_sources} source)"
        else:
            score = 15
            reasoning = "⚠️ Major news claim with NO corroboration - highly suspicious!"
        weight = "30%"
        
    elif story_type == "investigative_exclusive":
        # Exclusives don't need corroboration - trust the source
        if source_tier == "tier1":
            score = 90
            reasoning = "Exclusive investigation by tier1 source"
        elif source_tier == "tier2":
            score = 75
            reasoning = "Exclusive investigation by tier2 source"
        elif source_tier == "tier3":
            score = 45
            reasoning = "Exclusive claim by tier3 source"
        else:
            score = 25
            reasoning = "Exclusive claim by unknown source"
        weight = "15%"
        
    elif story_type == "local_news":
        # Local news won't have national coverage
        if source_tier in ["tier1", "tier2"]:
            score = 80
            reasoning = "Local story from credible source (corroboration not expected)"
        elif source_tier == "tier3":
            score = 60
            reasoning = "Local story from known source"
        else:
            score = 50
            reasoning = "Local story from unknown source"
        weight = "10%"
        
    elif story_type == "opinion":
        # Opinions don't need corroboration
        if source_tier in ["tier1", "tier2"]:
            score = 85
            reasoning = "Opinion piece from credible outlet (subjective content)"
        elif source_tier == "tier3":
            score = 60
            reasoning = "Opinion piece from known outlet"
        else:
            score = 50
            reasoning = "Opinion piece from unknown source"
        weight = "5%"
        
    else:  # standard
        # Standard news - moderate corroboration expectation
        if num_sources >= 3:
            score = 85
            reasoning = f"Story corroborated by {num_sources} independent sources"
        elif num_sources >= 1:
            score = 65
            reasoning = f"Story corroborated by {num_sources} other source"
        else:
            if source_tier in ["tier1", "tier2"]:
                score = 55
                reasoning = "No corroboration found, but source is credible"
            elif source_tier == "tier3":
                score = 35
                reasoning = "No corroboration from lower-tier source"
            else:
                score = 20
                reasoning = "No corroboration from unknown source"
        weight = "25%"
    
    return {
        "score": score,
        "weight": weight,
        "reasoning": reasoning,
        "story_type": story_type,
        "sources_found": num_sources,
        "sources": result.get("sources", [])
    }


def calculate_final_score(source_cred: Dict, content_qual: Dict, cross_ref: Dict) -> Dict:
    """
    Calculate final weighted score with dynamic weights based on story type
    """
    
    story_type = cross_ref.get("story_type", "standard")
    
    # Dynamic weights based on story type
    if story_type == "major_breaking":
        weights = {"source": 0.35, "content": 0.35, "cross_ref": 0.30}
    elif story_type == "investigative_exclusive":
        weights = {"source": 0.60, "content": 0.25, "cross_ref": 0.15}
    elif story_type == "local_news":
        weights = {"source": 0.50, "content": 0.40, "cross_ref": 0.10}
    elif story_type == "opinion":
        weights = {"source": 0.55, "content": 0.40, "cross_ref": 0.05}
    else:  # standard
        weights = {"source": 0.40, "content": 0.35, "cross_ref": 0.25}
    
    final = (
        source_cred["credibility_score"] * weights["source"] +
        content_qual["quality_score"] * weights["content"] +
        cross_ref["score"] * weights["cross_ref"]
    )
    
    score = round(final)
    
    # Determine label
    if score >= 90:
        label = "Highly Credible"
    elif score >= 70:
        label = "Credible"
    elif score >= 50:
        label = "Probably Credible"
    elif score >= 30:
        label = "Mixed Reliability"
    else:
        label = "Low Credibility"
    
    # Generate explanation
    explanation = f"This article is from {source_cred['verdict']}."
    if content_qual['red_flags']:
        explanation += f" Content quality issues detected: {', '.join(content_qual['red_flags'])}."
    if cross_ref['sources_found'] > 0:
        explanation += f" Story is corroborated by {cross_ref['sources_found']} independent sources."
    elif story_type in ["investigative_exclusive", "local_news", "opinion"]:
        explanation += f" As a {story_type.replace('_', ' ')}, corroboration is not expected."
    else:
        explanation += " No independent corroboration found."
    
    return {
        "score": score,
        "label": label,
        "explanation": explanation,
        "confidence": "High" if source_cred["known_source"] else "Moderate",
        "recommended_action": "Trust with caution and verify key claims" if score >= 50 else "Verify from multiple trusted sources before sharing",
        "methodology": f"Multi-factor weighted ensemble (Source: {weights['source']*100:.0f}%, Content: {weights['content']*100:.0f}%, Cross-ref: {weights['cross_ref']*100:.0f}%)",
        "scoring_factors": [
            {
                "factor": "Source Credibility",
                "score": source_cred["credibility_score"],
                "weight": f"{weights['source']*100:.0f}%",
                "reasoning": f"{source_cred['verdict']}"
            },
            {
                "factor": "Content Quality",
                "score": content_qual["quality_score"],
                "weight": f"{weights['content']*100:.0f}%",
                "reasoning": content_qual["reasoning"]
            },
            {
                "factor": "Cross-Reference",
                "score": cross_ref["score"],
                "weight": f"{weights['cross_ref']*100:.0f}%",
                "reasoning": cross_ref["reasoning"]
            }
        ]
    }


# ============================================================================
# CELERY TASK
# ============================================================================

@app.task(bind=True, name='credisource.verify_content')
def verify_news_article(self, job_id: str, url: str, content_type: str) -> Dict:
    """
    Main verification task
    Registered as 'credisource.verify_content' for compatibility with main.py
    Args:
        job_id: Job identifier
        url: URL to verify
        content_type: Type of content (news, image, video, text)
    """
    
    print(f"\n{'='*60}")
    print(f"🔍 VERIFYING: {url}")
    print(f"📋 Job ID: {job_id}")
    print(f"📌 Content Type: {content_type}")
    print(f"{'='*60}\n")
    
    # Only handle news for now
    if content_type != 'news':
        print(f"⚠️ Content type '{content_type}' not supported in new system yet")
        return {
            "error": f"Content type '{content_type}' not implemented",
            "trust_score": {
                "score": 0,
                "label": "Unsupported",
                "explanation": "Only 'news' content type is currently supported"
            }
        }
    
    try:
        # Extract article
        article = Article(url)
        article.download()
        article.parse()
        
        domain = extract_domain(url)
        word_count = len(article.text.split())
        article_images = article.images if hasattr(article, 'images') else []
        
        print(f"📰 Title: {article.title}")
        print(f"🌐 Domain: {domain}")
        print(f"📝 Word count: {word_count}\n")
        
        # 1. Check source credibility (we'll update after cross-ref)
        print("1️⃣ CHECKING SOURCE CREDIBILITY...")
        source_cred_initial = get_source_credibility(domain, False)
        print(f"   Score: {source_cred_initial['credibility_score']}/100")
        print(f"   Tier: {source_cred_initial['tier']}")
        print(f"   Assessment: {source_cred_initial['verdict']}\n")
        
        # 2. Analyze content quality
        print("2️⃣ ANALYZING CONTENT QUALITY...")
        content_analysis = analyze_content_quality(article.text, list(article_images)[:3])
        print(f"   Score: {content_analysis['quality_score']}/100")
        print(f"   Red flags: {len(content_analysis['red_flags'])}")
        if content_analysis['red_flags']:
            for flag in content_analysis['red_flags']:
                print(f"      🚩 {flag}")
        print()
        
        # 3. Cross-reference (smart)
        print("3️⃣ CROSS-REFERENCING STORY...")
        cross_ref = smart_cross_reference(
            article.title,
            article.text,
            domain,
            source_cred_initial['tier']
        )
        print()
        
        # Update source credibility with corroboration info
        has_corroboration = cross_ref['sources_found'] > 0
        source_cred = get_source_credibility(domain, has_corroboration)
        
        # 4. Calculate final score
        print("4️⃣ CALCULATING FINAL SCORE...")
        trust_score = calculate_final_score(source_cred, content_analysis, cross_ref)
        print(f"   Final Score: {trust_score['score']}/100")
        print(f"   Label: {trust_score['label']}")
        print(f"   Story Type: {cross_ref['story_type']}\n")
        
        # Build result
        result = {
            "trust_score": trust_score,
            "source_credibility": {
                "domain": domain,
                "tier": source_cred["tier"],
                "bias": source_cred["bias"],
                "type": source_cred["type"],
                "verdict": source_cred["verdict"]
            },
            "content_analysis": {
                "red_flags": content_analysis["red_flags"],
                "details": content_analysis["details"]
            },
            "cross_reference": {
                "sources_found": cross_ref["sources_found"],
                "sources": cross_ref.get("sources", [])[:5],
                "story_type": cross_ref["story_type"]
            },
            "article": {
                "title": article.title,
                "author": article.authors[0] if article.authors else "Unknown",
                "domain": domain,
                "word_count": word_count
            }
        }
        
        print("✅ Verification complete!\n")
        return result
        
    except Exception as e:
        print(f"❌ Error: {str(e)}\n")
        return {
            "error": str(e),
            "trust_score": {
                "score": 0,
                "label": "Error",
                "explanation": f"Failed to verify article: {str(e)}"
            }
        }


if __name__ == "__main__":
    print("Celery worker ready!")
    print(f"Sources in database: {len(SOURCE_CREDIBILITY)}")
    print("Ready to verify news articles! 🚀")
