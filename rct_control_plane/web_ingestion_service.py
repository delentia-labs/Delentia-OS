"""
Web Ingestion & Scraping Subsystem (Delentia OS MCP Module)
Fetches live web content, strips HTML noise, and extracts structured page context.
"""

import re
import urllib.request
from typing import Dict, Any, Optional
from html.parser import HTMLParser


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.title = ""
        self.in_title = False
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() in ["script", "style", "noscript", "svg", "header", "footer", "nav"]:
            self.in_script = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
        elif tag.lower() in ["script", "style", "noscript", "svg", "header", "footer", "nav"]:
            self.in_script = False

    def handle_data(self, d):
        if self.in_title:
            self.title += d.strip() + " "
        elif not self.in_script and not self.in_style:
            text = d.strip()
            if text:
                self.fed.append(text)

    def get_text(self) -> str:
        return " ".join(self.fed)


def extract_first_url(text: str) -> Optional[str]:
    """Extracts the first HTTP/HTTPS URL from user prompt."""
    url_pattern = r"(https?://[^\s\"'<>]+)"
    match = re.search(url_pattern, text)
    if match:
        return match.group(1).rstrip(".,;!?:")
    return None


def fetch_and_scrape_url(url: str, max_chars: int = 3500) -> Dict[str, Any]:
    """Fetches live web page content and extracts clean readable text."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 DelentiaOS/2.2.6"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw_data = resp.read()
            
            # Decode HTML
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()
            
            try:
                html_text = raw_data.decode(encoding, errors="replace")
            except Exception:
                html_text = raw_data.decode("utf-8", errors="replace")

            extractor = HTMLTextExtractor()
            extractor.feed(html_text)
            clean_text = extractor.get_text()

            # Clean multiple spaces
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            title = extractor.title.strip() or url

            truncated = clean_text[:max_chars]
            return {
                "success": True,
                "url": url,
                "title": title,
                "content_preview": truncated,
                "total_length": len(clean_text)
            }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }
