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
        
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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
        }

    def _make_request(self, url, headers=None, retries=3, delay=1):
        """Make a request with retry logic and random delays"""
        if headers is None:
            headers = self.default_headers.copy()
        
        headers["Host"] = urlparse(url).netloc
        
        for i in range(retries):
            try:
                if i > 0:
                    time.sleep(delay + random.random())
                
                response = self.session.get(url, headers=headers, timeout=10)
                self.logger.debug(f"Request to {url} returned status {response.status_code}")
                self.logger.debug(f"Response headers: {dict(response.headers)}")
                
                return response
                
            except requests.exceptions.RequestException as e:
                if i == retries - 1:
                    raise
                self.logger.debug(f"Request failed (attempt {i+1}/{retries}): {str(e)}")
        
        raise requests.exceptions.RequestException(f"Failed after {retries} retries")

    def _get_config_data(self) -> dict:
        try:
            stream_url = "https://thedaddy.to/stream-1.php"
            headers = self.default_headers.copy()
            headers.update({
                "Referer": "https://thedaddy.to/24-7-channels.php",
                "Origin": "https://thedaddy.to",
                "Sec-Fetch-Site": "same-origin",
            })
            
            response = self._make_request(stream_url, headers=headers)
            self.logger.debug(f"Stream page content: {response.text[:500]}")  # Log first 500 chars
            
            # Updated regex pattern to specifically match .m3u8 URLs
            m3u8_pattern = r'https?://[^\s"\']+\.m3u8'
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for <video> or <source> elements
            video_element = soup.find('video')
            if video_element and video_element.get('src') and '.m3u8' in video_element['src']:
                self.logger.debug(f"Found video source: {video_element['src']}")
                stream_url = video_element['src']
            else:
                source_element = soup.find('source')
                if source_element and source_element.get('src') and '.m3u8' in source_element['src']:
                    self.logger.debug(f"Found source element: {source_element['src']}")
                    stream_url = source_element['src']
                else:
                    # Search for .m3u8 links in the page content
                    matches = re.findall(m3u8_pattern, response.text, re.IGNORECASE)
                    if matches:
                        self.logger.debug(f"Found m3u8 URL: {matches[0]}")
                        stream_url = matches[0]
                    else:
                        # If no direct .m3u8 link found, check if there's an iframe to parse
                        iframe = soup.find('iframe')
                        if iframe and iframe.get('src'):
                            iframe_url = urljoin(stream_url, iframe['src'])
                            self.logger.debug(f"Found iframe URL: {iframe_url}")

                            iframe_response = self._make_request(iframe_url, headers=headers)
                            iframe_source = iframe_response.text
                            
                            matches = re.findall(m3u8_pattern, iframe_source, re.IGNORECASE)
                            if matches:
                                self.logger.debug(f"Found m3u8 URL in iframe: {matches[0]}")
                                stream_url = matches[0]
            
            if not stream_url or not stream_url.endswith(".m3u8"):
                raise ValueError("Could not find valid .m3u8 stream source")
            
            # Clean up the stream URL
            stream_url = stream_url.strip().strip('"\'')
            base_url = stream_url.replace("1", "STREAM-ID")
            
            config = {
                "endpoint": base_url,
                "referer": "https://thedaddy.to/"
            }
            
            self.logger.debug(f"Final config: {config}")
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
