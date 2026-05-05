"""
Web Crawler for doit RAG Chatbot
Crawls website pages, extracts clean content, and saves to JSON.
"""

import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

# ============================================================================
# CONFIGURATION
# ============================================================================
START_URL = "https://en.wikipedia.org"  # <- CHANGE THIS TO YOUR WEBSITE URL
REQUEST_TIMEOUT = 10  # seconds
RATE_LIMIT_DELAY = 0.5  # seconds between requests
MIN_TEXT_LENGTH = 100  # minimum characters of clean text to save
MAX_PAGES = 50  # maximum number of pages to crawl
OUTPUT_FILE = "pages.json"

# File extensions to skip
SKIP_EXTENSIONS = {'.pdf', '.jpg', '.png', '.zip', '.mp4', '.gif', '.svg'}

# Tags to remove (nav, footer, header, script, style, aside, ads)
REMOVE_TAGS = {
    'nav', 'footer', 'header', 'script', 'style', 'aside',
    'noscript', 'meta', 'link', 'form'
}

# Additional selectors for advertisement content
AD_SELECTORS = [
    '[class*="ad"]', '[class*="advertisement"]', '[class*="banner"]',
    '[id*="ad"]', '[id*="advertisement"]', '[id*="banner"]'
]

# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def get_domain(url):
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_same_domain(url, start_url):
    """Check if URL is on the same domain as START_URL."""
    return get_domain(url) == get_domain(start_url)


def should_skip_url(url):
    """Check if URL should be skipped based on file extension."""
    parsed = urlparse(url.lower())
    path = parsed.path
    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def normalize_url(url):
    """Remove fragments from URL for consistency."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{'?' + parsed.query if parsed.query else ''}"


def fetch_page(url, session):
    """Fetch a page with error handling."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = session.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return None


def clean_html(html_content):
    """Remove unwanted tags and extract clean text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove unwanted tags
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # Remove ad-related elements
    for selector in AD_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()
    
    # Get clean text
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    clean_text = '\n'.join(lines)
    
    return clean_text


def extract_title(html_content):
    """Extract page title."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Try title tag first
    title_tag = soup.find('title')
    if title_tag:
        return title_tag.get_text(strip=True)
    
    # Fall back to og:title meta tag
    og_title = soup.find('meta', property='og:title')
    if og_title:
        return og_title.get('content', '')
    
    return ''


def extract_headings(html_content):
    """Extract all h1, h2, h3 headings."""
    soup = BeautifulSoup(html_content, 'html.parser')
    headings = []
    
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        text = tag.get_text(strip=True)
        if text:
            headings.append(text)
    
    return headings


def get_utc_timestamp():
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def crawl_website():
    """Main crawl function."""
    
    print(f"Starting crawl from: {START_URL}\n")
    
    visited_urls = set()
    urls_to_crawl = [normalize_url(START_URL)]
    results = []
    failed_count = 0
    success_count = 0
    
    session = requests.Session()
    start_domain = get_domain(START_URL)
    
    try:
        while urls_to_crawl:
            # Stop if we reached MAX_PAGES
            if len(results) >= MAX_PAGES:
                print(f"\nReached MAX_PAGES limit ({MAX_PAGES}). Stopping crawl.")
                break

            url = urls_to_crawl.pop(0)
            
            # Skip if already visited
            if url in visited_urls:
                continue
            
            visited_urls.add(url)
            
            # Skip external links
            if not is_same_domain(url, START_URL):
                continue
            
            # Skip file extensions
            if should_skip_url(url):
                print(f"[x] Skipped (file type): {url}")
                continue
            
            # Be polite - rate limit
            time.sleep(RATE_LIMIT_DELAY)
            
            # Fetch page
            html_content = fetch_page(url, session)
            
            if not html_content:
                print(f"[x] Failed to fetch: {url}")
                failed_count += 1
                continue
            
            # Extract content
            clean_text = clean_html(html_content)
            
            # Extract new links from this page BEFORE checking text length
            soup = BeautifulSoup(html_content, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Convert relative URLs to absolute
                absolute_url = urljoin(url, href)
                normalized = normalize_url(absolute_url)
                
                # Only add if same domain and not visited
                if (is_same_domain(normalized, START_URL) and 
                    normalized not in visited_urls and 
                    not should_skip_url(normalized)):
                    if normalized not in urls_to_crawl:
                        urls_to_crawl.append(normalized)

            # Skip if text is too short
            if len(clean_text) < MIN_TEXT_LENGTH:
                print(f"[x] Skipped (insufficient content): {url}")
                continue
            
            # Extract metadata
            title = extract_title(html_content)
            headings = extract_headings(html_content)
            
            # Add to results
            page_data = {
                'url': url,
                'title': title,
                'text': clean_text,
                'headings': headings,
                'crawled_at': get_utc_timestamp()
            }
            results.append(page_data)
            
            print(f"[v] {url} ({len(results)}/{MAX_PAGES})")
            success_count += 1

    except KeyboardInterrupt:
        print("\n\nCrawl interrupted by user! Saving progress...")
    finally:
        # Save results no matter what (completed, limit reached, or interrupted)
        if len(results) > 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"CRAWL COMPLETE / STOPPED")
        print(f"{'='*60}")
        print(f"[v] Pages crawled successfully: {success_count}")
        print(f"[x] Pages failed: {failed_count}")
        print(f"Total pages saved: {len(results)}")
        if len(results) > 0:
            print(f"Results saved to: {OUTPUT_FILE}")
        else:
            print("No pages were saved. The file was not created.")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    crawl_website()
