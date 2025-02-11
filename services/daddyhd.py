from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from . import BaseService
import requests
import re
import logging
import time
import random

class DaddyHD(BaseService):
    def __init__(self) -> None:
        super().__init__(
            SERVICE_NAME="DaddyHD",
            SERVICE_URL="https://thedaddy.to/24-7-channels.php",
        )
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
        # More realistic browser headers
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1",
        }

    def _make_request(self, url, headers=None, retries=3, delay=1):
        """Make a request with retry logic and random delays"""
        if headers is None:
            headers = self.default_headers.copy()
        
        headers["Host"] = urlparse(url).netloc
        
        for i in range(retries):
            try:
                # Add a random delay between requests
                if i > 0:
                    time.sleep(delay + random.random())
                
                response = self.session.get(url, headers=headers, timeout=10)
                self.logger.debug(f"Request to {url} returned status {response.status_code}")
                
                # Handle potential cloudflare or other protection
                if response.status_code == 403:
                    if i < retries - 1:  # If we have retries left
                        self.logger.debug(f"Got 403, retrying with modified headers...")
                        # Modify headers slightly for next attempt
                        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                        continue
                
                return response
                
            except requests.exceptions.RequestException as e:
                if i == retries - 1:  # If this was our last retry
                    raise
                self.logger.debug(f"Request failed (attempt {i+1}/{retries}): {str(e)}")
        
        raise requests.exceptions.RequestException(f"Failed after {retries} retries")

    def _get_config_data(self) -> dict:
        try:
            # Initial request to the main site to get cookies
            main_url = "https://thedaddy.to/"
            self._make_request(main_url)
            
            # Now try the embed URL
            embed_url = "https://dlhd.sx/embed/stream-1.php"
            parsed_embed = urlparse(embed_url)
            
            # Add referrer from main site
            headers = self.default_headers.copy()
            headers.update({
                "Referer": main_url,
                "Origin": "https://thedaddy.to",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "iframe",
            })
            
            response = self._make_request(embed_url, headers=headers)
            
            if response.status_code == 301 or response.status_code == 302:
                # Handle redirect manually if needed
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    embed_url = urljoin(embed_url, redirect_url)
                    response = self._make_request(embed_url, headers=headers)
            
            soup = BeautifulSoup(response.text, "html.parser")
            iframe = soup.find("iframe", {"id": "thatframe"})
            
            if not iframe or "src" not in iframe.attrs:
                raise ValueError("Could not find iframe source")
                
            iframe_url = iframe["src"]
            self.logger.debug(f"Found iframe URL: {iframe_url}")
            iframe_parsed = urlparse(iframe_url)
            
            # Update headers for the iframe request
            headers.update({
                "Referer": embed_url,
                "Origin": f"{parsed_embed.scheme}://{parsed_embed.netloc}",
                "Sec-Fetch-Site": "cross-site",
            })
            
            iframe_response = self._make_request(iframe_url, headers=headers)
            iframe_source = iframe_response.text
            
            # Look for source in various formats
            patterns = [
                r'source:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'file:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'src:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r"source:'([^']+)'",
                r'source: "([^"]+)"',
            ]
            
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, iframe_source, re.IGNORECASE)
                if found:
                    matches.extend(found)
                    self.logger.debug(f"Found matches with pattern {pattern}: {found}")
            
            if not matches:
                raise ValueError("No stream sources found")
            
            config_endpoint = matches[-1].replace("1", "STREAM-ID")
            
            config = {
                "endpoint": config_endpoint,
                "referer": f"{iframe_parsed.scheme}://{iframe_parsed.netloc}/"
            }
            
            return config
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error in _get_config_data: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Error in _get_config_data: {str(e)}")
            raise

    def _get_data(self) -> dict:
        try:
            soup = BeautifulSoup(self._get_src(), "html.parser")
            config_data = self._get_config_data()
            channels_data = []
            
            channels_divs = soup.select("div.grid-item")
            self.logger.debug(f"Found {len(channels_divs)} channel divs")
            
            for channel_div in channels_divs:
                channel_slug = channel_div.select_one("a").get("href").strip()
                FIRST_INDEX = channel_slug.find("stream-") + len("stream-")
                LAST_INDEX = channel_slug.find(".php")
                channel_id = channel_slug[FIRST_INDEX:LAST_INDEX]
                channel_name = channel_div.text.strip()
                
                if "18+" in channel_name:
                    continue
                    
                channels_data.append({
                    "name": channel_name,
                    "logo": "",
                    "group": "DaddyHD",
                    "stream-url": config_data.get("endpoint").replace("STREAM-ID", channel_id),
                    "headers": {
                        "referer": config_data.get("referer"),
                        "user-agent": self.default_headers["User-Agent"]
                    }
                })
            
            return channels_data
            
        except Exception as e:
            self.logger.error(f"Error in _get_data: {str(e)}")
            raise
