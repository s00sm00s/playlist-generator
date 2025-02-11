from urllib.parse import urlparse
from bs4 import BeautifulSoup
from . import BaseService
import requests
import re
import logging
import json

class DaddyHD(BaseService):
    def __init__(self) -> None:
        super().__init__(
            SERVICE_NAME="DaddyHD",
            SERVICE_URL="https://thedaddy.to/24-7-channels.php",
        )
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        # Enhanced browser-like headers
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Cache-Control": "max-age=0",
        }

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
            
            self.logger.debug(f"Processed {len(channels_data)} channels")
            return channels_data
            
        except Exception as e:
            self.logger.error(f"Error in _get_data: {str(e)}")
            raise

    def _get_config_data(self) -> dict:
        try:
            EMBED_URL = "https://dlhd.sx/embed/stream-1.php"
            parsed_embed = urlparse(EMBED_URL)
            
            # First request to get the initial page
            headers = self.default_headers.copy()
            headers["Host"] = parsed_embed.netloc
            response = self.session.get(EMBED_URL, headers=headers)
            response.raise_for_status()
            
            self.logger.debug(f"Initial response status: {response.status_code}")
            
            soup = BeautifulSoup(response.text, "html.parser")
            iframe = soup.find("iframe", {"id": "thatframe"})
            
            if not iframe or "src" not in iframe.attrs:
                raise ValueError("Could not find iframe source")
                
            iframe_url = iframe["src"]
            self.logger.debug(f"Found iframe URL: {iframe_url}")
            iframe_parsed = urlparse(iframe_url)
            
            # Update headers for the iframe request
            headers = self.default_headers.copy()
            headers.update({
                "Host": iframe_parsed.netloc,
                "Referer": f"{parsed_embed.scheme}://{parsed_embed.netloc}/",
                "Origin": f"{parsed_embed.scheme}://{parsed_embed.netloc}",
            })
            
            # Make the iframe request
            iframe_response = self.session.get(
                iframe_url,
                headers=headers,
                allow_redirects=True
            )
            iframe_response.raise_for_status()
            
            # Try to find the stream source using multiple methods
            iframe_source = iframe_response.text
            self.logger.debug(f"Iframe response length: {len(iframe_source)}")
            
            # Look for source in various formats
            patterns = [
                r'source:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'file:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'src:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'url:\s*["\']?(https?://[^"\'\s]+)["\']?',
                r'(?:source|file|src|url):\s*["\']?(https?://[^"\'\s]+)["\']?'
            ]
            
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, iframe_source, re.IGNORECASE)
                if found:
                    matches.extend(found)
                    self.logger.debug(f"Found matches with pattern {pattern}: {found}")
            
            if not matches:
                # Try to find any URLs that look like stream sources
                stream_pattern = r'https?://[^"\'\s]+(?:\.m3u8|\.mp4|/stream/|/live/)[^"\'\s]*'
                matches = re.findall(stream_pattern, iframe_source)
                
            if not matches:
                # Look for potential API endpoints that might return stream URLs
                api_pattern = r'https?://[^"\'\s]+(?:api|stream|player|embed)[^"\'\s]*'
                api_urls = re.findall(api_pattern, iframe_source)
                
                if api_urls:
                    self.logger.debug(f"Found potential API URLs: {api_urls}")
                    # Try to fetch from each API endpoint
                    for api_url in api_urls:
                        try:
                            headers["Referer"] = iframe_url
                            api_response = self.session.get(api_url, headers=headers)
                            if api_response.headers.get('content-type', '').startswith('application/json'):
                                data = api_response.json()
                                # Look for stream URLs in the JSON response
                                json_str = json.dumps(data)
                                stream_urls = re.findall(stream_pattern, json_str)
                                if stream_urls:
                                    matches.extend(stream_urls)
                        except Exception as e:
                            self.logger.debug(f"Failed to fetch API URL {api_url}: {str(e)}")
            
            if not matches:
                raise ValueError("No stream sources found")
            
            # Use the most likely stream URL (prefer m3u8 or mp4 URLs)
            matches = [m for m in matches if m.strip()]  # Remove empty matches
            preferred_matches = [m for m in matches if '.m3u8' in m or '.mp4' in m]
            config_endpoint = (preferred_matches or matches)[-1].replace("1", "STREAM-ID")
            
            self.logger.debug(f"Selected config endpoint: {config_endpoint}")
            
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
