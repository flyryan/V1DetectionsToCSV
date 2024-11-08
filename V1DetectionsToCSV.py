"""
Trend Micro Vision One Detection Retrieval Script
---------------------------------------------
This script retrieves detection events from Vision One API and exports them to CSV.
"""

import csv
import json
import sys
import requests
from datetime import datetime, timedelta
import threading
import queue
import os
import urllib.parse
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor
import yaml
import concurrent.futures 

# Configure logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

file_handler = logging.FileHandler('vision_one_detections.log')
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

@dataclass
class Config:
    """Configuration class for the application."""
    api_token: str
    api_endpoint: str
    start_date: str
    end_date: str
    max_results: int
    results_per_call: int
    query_filter: str
    output_file: str
    checkpoint_file: str
    num_threads: int
    request_timeout: int
    rate_limit_per_second: int
    rate_limit_minute: int
    rate_limit_hour: int

    @classmethod
    def from_yaml(cls, file_path: str) -> 'Config':
        """Load configuration from YAML file."""
        with open(file_path, 'r') as f:
            config_data = yaml.safe_load(f)
        return cls(**config_data)

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        return cls(
            api_token=os.getenv('VISION_ONE_API_TOKEN'),
            api_endpoint=os.getenv('VISION_ONE_API_ENDPOINT'),
            start_date=os.getenv('START_DATE'),
            end_date=os.getenv('END_DATE'),
            max_results=int(os.getenv('MAX_RESULTS', 1000000)),
            results_per_call=int(os.getenv('RESULTS_PER_CALL', 5000)),
            query_filter=os.getenv('QUERY_FILTER'),
            output_file=os.getenv('OUTPUT_FILE', 'detections.csv'),
            checkpoint_file=os.getenv('CHECKPOINT_FILE', 'checkpoint.json'),
            num_threads=int(os.getenv('NUM_THREADS', 3))
        )

import time
from collections import deque

class RateLimiter:
    def __init__(self, minute_limit, hour_limit):
        self.minute_limit = minute_limit
        self.hour_limit = hour_limit
        self.minute_requests = deque()
        self.hour_requests = deque()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            current_time = time.time()
            
            # Remove timestamps older than 60 seconds for minute limit
            while self.minute_requests and current_time - self.minute_requests[0] > 60:
                self.minute_requests.popleft()
            
            # Remove timestamps older than 3600 seconds for hour limit
            while self.hour_requests and current_time - self.hour_requests[0] > 3600:
                self.hour_requests.popleft()
            
            # Calculate wait time if limits are reached
            wait_time = 0
            if len(self.minute_requests) >= self.minute_limit:
                wait_time = max(wait_time, 60 - (current_time - self.minute_requests[0]))
            if len(self.hour_requests) >= self.hour_limit:
                wait_time = max(wait_time, 3600 - (current_time - self.hour_requests[0]))
            
            if wait_time > 0:
                time.sleep(wait_time)
                current_time = time.time()
                # Clean up after waiting
                while self.minute_requests and current_time - self.minute_requests[0] > 60:
                    self.minute_requests.popleft()
                while self.hour_requests and current_time - self.hour_requests[0] > 3600:
                    self.hour_requests.popleft()
            
            # Record the new request
            self.minute_requests.append(current_time)
            self.hour_requests.append(current_time)

class VisionOneAPI:
    """Handle Vision One API interactions."""
    
    LIST_FIELDS = {'endpointIp', 'interestedIp', 'act', 'dst', 'src'}

    def __init__(self, config: Config):
        self.config = config
        self.session = self._create_session()
        self.rate_limiter = RateLimiter(config.rate_limit_minute, config.rate_limit_hour)

    def _create_session(self) -> requests.Session:
        """Create and configure requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            'Authorization': f'Bearer {self.config.api_token}',
            'TMV1-Query': self.config.query_filter
        })
        return session

    def get_detections(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make API request with rate limiting and proper error handling."""
        self.rate_limiter.wait()
        try:
            response = self.session.get(
                self.config.api_endpoint,
                params=params,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API Request Error: {str(e)}", exc_info=True)
            raise

class DetectionProcessor:
    """Process and store detection data."""

    def __init__(self, config: Config, api: VisionOneAPI):
        self.config = config
        self.api = api
        self.total_detections = 0
        self.max_detections_reached = False
        self.request_count = 0
        self.counter_lock = threading.Lock()
        self.output_lock = threading.Lock()
        self.fieldnames = set()  # Track all field names

    @staticmethod
    def flatten_dict(item: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten dictionary and convert lists to strings."""
        flattened = {}
        for key, value in item.items():
            if value is None:
                flattened[key] = ''
            elif key in VisionOneAPI.LIST_FIELDS and isinstance(value, list):
                flattened[key] = ','.join(str(x) for x in value if x is not None)
            else:
                flattened[key] = value
        return flattened

    def _update_fieldnames(self, items: List[Dict[str, Any]]) -> None:
        """Update the set of known field names."""
        for item in items:
            self.fieldnames.update(item.keys())

    def _write_to_csv(self, items: List[Dict[str, Any]]) -> None:
        """Write detection items to CSV file in order based on 'eventTimeDT'."""
        if not items:
            return

        # Sort incoming items by 'eventTimeDT'
        items.sort(key=lambda x: x.get('eventTimeDT'))

        with self.output_lock:
            file_exists = os.path.exists(self.config.output_file)
            
            if file_exists:
                # Read existing data
                with open(self.config.output_file, 'r', newline='') as original:
                    reader = csv.DictReader(original)
                    existing_rows = list(reader)
                
                # Merge existing rows with new items
                merged_rows = []
                i, j = 0, 0
                while i < len(existing_rows) and j < len(items):
                    existing_time = existing_rows[i].get('eventTimeDT')
                    new_time = items[j].get('eventTimeDT')
                    if existing_time <= new_time:
                        merged_rows.append(existing_rows[i])
                        i += 1
                    else:
                        merged_rows.append(items[j])
                        j += 1
                # Append any remaining rows
                merged_rows.extend(existing_rows[i:])
                merged_rows.extend(items[j:])
                
                # Write merged data to temporary file
                temp_file = f"{self.config.output_file}.tmp"
                with open(temp_file, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames or sorted(merged_rows[0].keys()), extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(merged_rows)
            else:
                # Initialize fieldnames
                self.fieldnames = sorted(items[0].keys())
                # Write new items to temporary file
                temp_file = f"{self.config.output_file}.tmp"
                with open(temp_file, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(items)

            # Replace original file with temporary file
            os.replace(temp_file, self.config.output_file)

    def debug_data_structure(self, data: Dict[str, Any], label: str = "Data Structure") -> None:
        """Print detailed information about the data structure."""
        logger.info(f"\n=== {label} ===")
        logger.info(f"Type: {type(data)}")
        
        if isinstance(data, dict):
            logger.info("Keys:")
            for key in sorted(data.keys()):
                value = data[key]
                value_type = type(value)
                sample = str(value)[:100] + '...' if len(str(value)) > 100 else str(value)
                logger.info(f"  {key}: (Type: {value_type}) = {sample}")
        elif isinstance(data, list):
            logger.info(f"List length: {len(data)}")
            if data:
                logger.info("First item structure:")
                self.debug_data_structure(data[0], "First Item")

    def process_detections(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a batch of detections."""
        with self.counter_lock:
            self.request_count += 1
            current_request = self.request_count

        try:
            logger.info(f"Thread {threading.current_thread().name} - Making API request #{current_request}")
            data = self.api.get_detections(params)
            items = data.get('items', [])
            
            if items:
                flattened_items = [self.flatten_dict(item) for item in items]
                self._write_to_csv(flattened_items)

                with self.counter_lock:
                    self.total_detections += len(items)
                    logger.info(f"Thread {threading.current_thread().name} - Request #{current_request} completed. Total detections: {self.total_detections}")
                    if self.config.max_results and self.total_detections >= self.config.max_results:
                        self.max_detections_reached = True
                        return None

            return self._get_next_params(data, params)
        except Exception as e:
            logger.error(f"Error processing detections: {str(e)}", exc_info=True)
            raise

    def _get_next_params(self, data: Dict[str, Any], current_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get parameters for the next API request."""
        next_link = data.get('nextLink', '')
        if next_link and not self.max_detections_reached:
            parsed_url = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            next_skip_token = query_params.get('skipToken', [''])[0]
            if next_skip_token:
                new_params = current_params.copy()
                new_params['skipToken'] = next_skip_token
                return new_params
        return None

def main():
    """Main execution function."""
    try:
        config = Config.from_yaml('config.yaml') if os.path.exists('config.yaml') else Config.from_env()
        
        if not config.api_endpoint:
            config.api_endpoint = 'https://api.xdr.trendmicro.com/v3.0/search/detections'
        
        if not config.api_token:
            raise ValueError("API token is required")

        api = VisionOneAPI(config)
        processor = DetectionProcessor(config, api)

        # Calculate the list of time intervals
        start_datetime = datetime.strptime(config.start_date, "%Y-%m-%dT%H:%M:%SZ")
        end_datetime = datetime.strptime(config.end_date, "%Y-%m-%dT%H:%M:%SZ")
        total_seconds = int((end_datetime - start_datetime).total_seconds())
        interval_seconds = total_seconds // config.num_threads

        intervals = []
        for i in range(config.num_threads):
            interval_start = start_datetime + timedelta(seconds=i * interval_seconds)
            interval_end = interval_start + timedelta(seconds=interval_seconds)
            if interval_end > end_datetime or i == config.num_threads - 1:
                interval_end = end_datetime
            intervals.append((interval_start.isoformat(), interval_end.isoformat()))

        # Function to process detections for a given time interval
        def process_interval(interval_start, interval_end):
            params = {
                'startDateTime': interval_start,
                'endDateTime': interval_end,
                'top': config.results_per_call,
                'mode': 'detection'
            }
            while not processor.max_detections_reached:
                next_params = processor.process_detections(params)
                if next_params is None:
                    break
                params = next_params

        # Create a thread pool
        with ThreadPoolExecutor(max_workers=config.num_threads) as executor:
            futures = []
            for i, interval in enumerate(intervals):
                futures.append(executor.submit(process_interval, interval[0], interval[1]))
                time.sleep(3)  # Add a 1-second delay between starting threads
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Thread encountered an error: {str(e)}")

        logger.info(f"Detection retrieval completed. Total detections: {processor.total_detections}")

    except Exception as e:
        logger.error("Fatal error in main execution", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()