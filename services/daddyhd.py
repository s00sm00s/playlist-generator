from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests
import re
import logging
import time
import random

class DaddyHD:
    def __init__(self) -> None:
        self.SERVICE_NAME = "DaddyHD"
        self.SERVICE_URL = "https://thedaddy.to/24-7-channels.php"
        
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

    def _extract_m3u8_url(self, stream_url):
        """Extract the m3u8 URL from the stream page"""
        try:
            response = self._make_request(stream_url)
            if response.status_code != 200:
                raise ValueError(f"Failed to load stream page: {stream_url}")

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract channelKey from the script
            script_tags = soup.find_all("script")
            channel_key = None
            for script in script_tags:
                if "channelKey" in script.text:
                    match = re.search(r'var\s+channelKey\s*=\s*"([^"]+)"', script.text)
                    if match:
                        channel_key = match.group(1)
                        break

            if not channel_key:
                raise ValueError("Channel key not found on the page.")

            # Get server key via AJAX request
            server_lookup_url = f"https://thedaddy.to/server_lookup.php?channel_id={channel_key}"
            server_response = self._make_request(server_lookup_url)
            server_data = server_response.json()

            if "server_key" not in server_data:
                raise ValueError("No server key found in server_lookup.php response.")

            server_key = server_data["server_key"]

            # Construct the final m3u8 URL
            if server_key == "top1/cdn":
                m3u8_url = f"https://top1.iosplayer.ru/top1/cdn/{channel_key}/mono.m3u8"
            else:
                m3u8_url = f"https://{server_key}new.iosplayer.ru/{server_key}/{channel_key}/mono.m3u8"

            self.logger.debug(f"Extracted m3u8 URL: {m3u8_url}")
            return m3u8_url

        except Exception as e:
            self.logger.error(f"Error extracting m3u8 URL: {str(e)}")
            return None

    def _get_data(self) -> list:
        try:
            main_page_url = self.SERVICE_URL
            headers = self.default_headers.copy()
            headers.update({
                "Referer": "https://thedaddy.to/",
                "Origin": "https://thedaddy.to",
                "Sec-Fetch-Site": "same-origin",
            })

            response = self._make_request(main_page_url, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")

            channels_data = []
            channel_links = soup.select("div.grid-item a[href^='/stream/stream-']")
            
            self.logger.debug(f"Found {len(channel_links)} channel links on the page.")

            for link in channel_links:
                channel_name = link.get_text(strip=True)
                channel_url = urljoin(main_page_url, link["href"])
                
                self.logger.debug(f"Processing channel: {channel_name}, URL: {channel_url}")

                m3u8_url = self._extract_m3u8_url(channel_url)
                if not m3u8_url:
                    self.logger.warning(f"Skipping {channel_name} due to missing m3u8 URL")
                    continue

                channels_data.append({
                    "name": channel_name,
                    "logo": "",
                    "group": "DaddyHD",
                    "stream-url": m3u8_url,
                    "headers": {
                        "referer": "https://thedaddy.to/",
                        "user-agent": self.default_headers["User-Agent"]
                    }
                })
            
            return channels_data

        except Exception as e:
            self.logger.error(f"Error in _get_data: {str(e)}")
            return []

    def update(self):
        """Update the playlist by fetching new channel data."""
        try:
            channels = self._get_data()
            self.logger.info(f"Successfully retrieved {len(channels)} channels.")
            return channels
        except Exception as e:
            self.logger.error(f"Update failed: {str(e)}")
            return []
