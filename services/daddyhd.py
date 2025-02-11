from urllib.parse import urlparse
from bs4 import BeautifulSoup
from . import BaseService
import requests
import re
import logging

class DaddyHD(BaseService):
    def __init__(self) -> None:
        super().__init__(
            SERVICE_NAME="DaddyHD",
            SERVICE_URL="https://thedaddy.to/24-7-channels.php",
        )
        # Set up logging
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

    def _get_data(self) -> dict:
        """
        Fetches and processes channel data from the service.
        Returns a list of channel dictionaries.
        """
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
                        "user-agent": self.USER_AGENT
                    }
                })
            
            self.logger.debug(f"Processed {len(channels_data)} channels")
            return channels_data
            
        except Exception as e:
            self.logger.error(f"Error in _get_data: {str(e)}")
            raise

    def _get_config_data(self) -> dict:
        """
        Fetches and processes configuration data from the embed URL.
        Returns a dictionary with endpoint and referer information.
        """
        try:
            EMBED_URL = "https://dlhd.sx/embed/stream-1.php"
            parsed_embed = urlparse(EMBED_URL)
            
            # Add headers to mimic a browser request
            headers = {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            response = requests.get(EMBED_URL, headers=headers)
            response.raise_for_status()  # Raise an error for bad status codes
            self.logger.debug(f"Initial response status: {response.status_code}")
            
            soup = BeautifulSoup(response.text, "html.parser")
            iframe = soup.find("iframe", {"id": "thatframe"})
            
            if not iframe or "src" not in iframe.attrs:
                raise ValueError("Could not find iframe source")
                
            iframe_url = iframe["src"]
            self.logger.debug(f"Found iframe URL: {iframe_url}")
            iframe_parsed = urlparse(iframe_url)
            
            # Add referer header for iframe request
            iframe_headers = headers.copy()
            iframe_headers["Referer"] = f"{parsed_embed.scheme}://{parsed_embed.netloc}/"
            
            iframe_response = requests.get(iframe_url, headers=iframe_headers)
            iframe_response.raise_for_status()
            iframe_source = iframe_response.text
            
            # Debug output for iframe source
            self.logger.debug("Iframe source content (first 500 chars):")
            self.logger.debug(iframe_source[:500])
            
            # Look for the source pattern
            iframe_pattern = r"source:'(https:\/\/[^\s']+)'"
            matches = re.findall(iframe_pattern, iframe_source)
            
            self.logger.debug(f"Found {len(matches)} source matches: {matches}")
            
            if not matches:
                # Try alternative patterns if the first one doesn't work
                alternative_patterns = [
                    r'source: "(https:\/\/[^\s"]+)"',
                    r"source: '(https:\/\/[^\s']+)'",
                    r'file: "(https:\/\/[^\s"]+)"',
                    r"file: '(https:\/\/[^\s']+)'"
                ]
                
                for pattern in alternative_patterns:
                    matches = re.findall(pattern, iframe_source)
                    if matches:
                        self.logger.debug(f"Found matches using alternative pattern: {pattern}")
                        break
                
                if not matches:
                    raise ValueError("No stream sources found")
            
            # Use the last match if multiple exist, or the first if only one exists
            config_endpoint = matches[-1].replace("1", "STREAM-ID")
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
