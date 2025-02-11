from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from . import BaseService
import requests
import re
import logging
import time
import random
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

    def _extract_stream_url(self, stream_page_url):
        """Extracts the m3u8 URL from an individual stream page"""
        response = self._make_request(stream_page_url)
        if response.status_code != 200:
            raise ValueError(f"Failed to load stream page: {stream_page_url}")

        # Extract channelKey using regex
        channel_key_match = re.search(r'var\s+channelKey\s*=\s*"([^"]+)"', response.text)
        if not channel_key_match:
            raise ValueError(f"channelKey not found in {stream_page_url}")
        channel_key = channel_key_match.group(1)
        self.logger.debug(f"Extracted channelKey: {channel_key}")

        # Fetch the server key
        server_lookup_url = f"https://thedaddy.to/server_lookup.php?channel_id={channel_key}"
        server_response = self._make_request(server_lookup_url)

        # Parse JSON response
        server_data = json.loads(server_response.text)
        server_key = server_data.get("server_key")
        if not server_key:
            raise ValueError(f"server_key not found for channel {channel_key}")
        self.logger.debug(f"Extracted server_key: {server_key}")

        # Construct the m3u8 URL
        if server_key == "top1/cdn":
            stream_url = f"https://top1.iosplayer.ru/top1/cdn/{channel_key}/mono.m3u8"
        else:
            stream_url = f"https://{server_key}new.iosplayer.ru/{server_key}/{channel_key}/mono.m3u8"

        self.logger.debug(f"Final .m3u8 URL: {stream_url}")
        return stream_url

    def _get_data(self) -> dict:
        """Fetches the list of channels and their stream URLs"""
        try:
            response = self._make_request(self.SERVICE_URL)
            soup = BeautifulSoup(response.text, "html.parser")

            channels_data = []
            channel_links = [a["href"] for a in soup.find_all("a", href=True) if "stream-" in a["href"]]

            self.logger.debug(f"Found {len(channel_links)} stream links")

            for link in channel_links:
                stream_page_url = urljoin(self.SERVICE_URL, link)

                # Extract channel ID
                match = re.search(r"stream-(\d+)\.php", link)
                if not match:
                    continue
                channel_id = match.group(1)

                # Fetch the actual .m3u8 URL
                try:
                    stream_url = self._extract_stream_url(stream_page_url)
                except Exception as e:
                    self.logger.error(f"Skipping channel {channel_id}: {str(e)}")
                    continue

                # Extract channel name
                channel_name = link.replace("stream-", "").replace(".php", "").strip()
                channels_data.append({
                    "name": channel_name,
                    "logo": "",
                    "group": "DaddyHD",
                    "stream-url": stream_url,
                    "headers": {
                        "referer": "https://thedaddy.to/",
                        "user-agent": self.default_headers["User-Agent"]
                    }
                })

            return channels_data

        except Exception as e:
            self.logger.error(f"Error in _get_data: {str(e)}")
            raise
