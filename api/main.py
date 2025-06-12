import os
import asyncio
import re # Added for parsing Gemini mock response
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, HTTPException, Request # Keeping Request for potential future use
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential
from fastapi.responses import JSONResponse


# Import your Gemini service (mock implementation included below)
# This mock simulates Gemini's response for testing purposes.
# In a real scenario, you would replace this with actual Gemini API calls.
try:
    from gemini_service import get_gemini_most_relevant_post
except ImportError:
    # Fallback mock for testing if gemini_service.py is not available
    def get_gemini_most_relevant_post(posts: Dict, prompt: str) -> str:
        """
        Mock implementation of Gemini service.
        It tries to find a number followed by 'LYD' in the latest post text.
        """
        print(f"Mock Gemini called with prompt: {prompt} and posts: {posts}")
        # Iterate through posts to find a potential rate
        for url, data in posts.items():
            if data and data.get("post_text"):
                # Simple regex to find a pattern like "X.XX LYD"
                match = re.search(r'(\d+\.\d{2})\s*LYD', data["post_text"])
                if match:
                    return f"{match.group(1)} LYD"
        return "N/A LYD (Mock)" # Default if no rate found in mock posts

app = FastAPI(
    title="Facebook Currency Exchange Scraper",
    description="API for scraping Facebook pages to extract currency exchange rates",
    version="1.1.0"
)

# Enable CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins, adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variable to store the latest exchange rate information
# This acts as a simple in-memory cache for the latest scraped data.
latest_exchange_info = {
    "rate": "N/A",
    "timestamp": "Never scraped yet",
    "source_url": "No URL scraped yet.",
    "error": "No scrape performed yet. Send a POST request to /scrape."
}

# --- Pydantic Models for API Request/Response Validation ---

class StartUrl(BaseModel):
    """Defines the structure for a URL in the request."""
    url: HttpUrl

class ScrapeRequest(BaseModel):
    """Defines the structure for the /scrape endpoint's request body."""
    start_urls: List[StartUrl]

class ScrapeResult(BaseModel):
    """Defines the structure for a single scrape result."""
    url: str
    title: Optional[str] = None
    latest_post_text: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None

class ScrapeResponse(BaseModel):
    """Defines the overall structure for the /scrape endpoint's response."""
    results: List[ScrapeResult]
    gemini_selected_post: str # The extracted rate from Gemini

# --- Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# --- Scraping Logic ---

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def scrape_page(url: str, page) -> ScrapeResult:
    """
    Scrapes a single Facebook page for its title, latest post text, and timestamp.
    Uses Playwright for browser automation.
    """
    result = ScrapeResult(url=url)
    
    try:
        # Navigate to the URL and wait for network activity to settle
        await page.goto(url, wait_until="networkidle", timeout=20000)
        result.title = await page.title()
        
        # Wait for the main content area (e.g., div with role="article") to be present
        # This is crucial for dynamic content loading on Facebook
        await page.wait_for_selector('div[role="article"]', timeout=10000)
        
        # Get all elements that represent posts
        posts = await page.query_selector_all('div[role="article"]')
        if posts:
            # Assume the first 'article' role div is the most recent or relevant
            first_post = posts[0]
            result.latest_post_text = await first_post.inner_text()
            
            # Extract timestamp from abbr (data-utime) or time tags
            time_element = await first_post.query_selector('abbr[data-utime], time')
            if time_element:
                utime = await time_element.get_attribute('data-utime')
                if utime:
                    # Convert Unix timestamp to ISO format for consistency
                    result.timestamp = datetime.fromtimestamp(int(utime)).isoformat()
                else:
                    # Fallback to inner text if data-utime is not present
                    result.timestamp = await time_element.inner_text()
        else:
            result.error = "No posts found on page."

    except PlaywrightTimeoutError:
        result.error = "Timeout loading page or finding content. Page might be too slow or structure changed."
    except Exception as e:
        result.error = f"Error during scraping: {str(e)}"
    
    return result

# --- API Endpoints ---

@app.get("/health")
async def health_check():
    """Endpoint for health checks."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/", response_class=HTMLResponse)
async def get_exchange_rate_html():
    """
    Displays the latest scraped currency exchange rate on a basic, styled HTML page.
    The data displayed here is updated when a POST request is successfully made to the /scrape endpoint.
    """
    current_rate = latest_exchange_info.get("rate", "N/A")
    last_updated = latest_exchange_info.get("timestamp", "Never scraped yet")
    source_url = latest_exchange_info.get("source_url", "#") # Default to # if no URL
    scrape_error = latest_exchange_info.get("error", "")

    # Basic HTML structure with Tailwind CSS for styling
   
