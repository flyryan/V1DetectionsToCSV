"""
Trend Micro Vision One Detection Retrieval Script
---------------------------------------------
This script retrieves detection events from Vision One API and exports them to CSV.

Requirements:
- Python 3.6+
- requests library (pip install requests)

Usage:
1. Set your API token in the configuration section
2. Adjust other parameters as needed (time range, max results, etc.)
3. Run the script: python PTReventsPull.py
"""

import csv
import json
import sys
import requests
from datetime import datetime, timedelta

# =============================================================================
# Configuration Section - Modify these values as needed
# =============================================================================

# API Configuration
API_TOKEN = 'YOUR_API_KEY'  # Vision One API token
API_ENDPOINT = 'https://api.xdr.trendmicro.com/v3.0/search/detections'

# Search Parameters - Choose ONE of the following options:
# Option 1: Search by number of days
DAYS_TO_SEARCH = None  # Number of days of history to search (set to None if using date range)

# Option 2: Search by date range (format: "MM-DD-YYYY" in quotes or None)
START_DATE = "10-01-2024"    # Start date (set to None if using DAYS_TO_SEARCH) Format: MM-DD-YYYY
END_DATE = "10-31-2024"      # End date (set to None if using DAYS_TO_SEARCH) Format: MM-DD-YYYY

# Other Parameters
MAX_RESULTS = 20000 # Maximum number of results to retrieve (set to None for unlimited, but be cautious as this may return a large number of results)
RESULTS_PER_CALL = 5000  # Number of results per API call (max 5000)

# Filter Configuration
QUERY_FILTER = "productCode:PTP AND act:Block"  # Vision One search query

# Output Configuration
OUTPUT_FILE = 'detections.csv'

def validate_config():
    """Validate configuration parameters before running."""
    if not API_TOKEN or API_TOKEN == 'your_token_here':
        sys.exit("Error: Please configure your API token")
    if RESULTS_PER_CALL > 5000:
        sys.exit("Error: RESULTS_PER_CALL cannot exceed 5000")

def validate_date_format(date_str):
    """Validate date string format (MM-DD-YYYY)."""
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, '%m-%d-%Y')
    except ValueError:
        sys.exit(f"Error: Invalid date format. Use MM-DD-YYYY format")

def format_date(date_value):
    """
    Convert date value to proper string format.
    Handles both None and numeric date inputs (e.g. 10-01-2024).
    """
    if date_value is None:
        return None
    
    if isinstance(date_value, str):
        return f'"{date_value}"'
        
    # Handle numeric format (e.g. 10-01-2024)
    try:
        month = str(date_value).split('-')[0].zfill(2)
        day = str(date_value).split('-')[1].zfill(2)
        year = str(date_value).split('-')[2]
        return f'"{month}-{day}-{year}"'
    except (IndexError, AttributeError):
        sys.exit("Error: Invalid date format. Use MM-DD-YYYY format")

def get_time_range():
    """Calculate the time range for the search based on configuration."""
    if DAYS_TO_SEARCH and (START_DATE or END_DATE):
        sys.exit("Error: Use either DAYS_TO_SEARCH or date range (START_DATE/END_DATE), not both")
    
    if DAYS_TO_SEARCH:
        if DAYS_TO_SEARCH <= 0:
            sys.exit("Error: DAYS_TO_SEARCH must be greater than 0")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=DAYS_TO_SEARCH)
    else:
        if not START_DATE or not END_DATE:
            sys.exit("Error: Both START_DATE and END_DATE must be specified when using date range")
        
        start_date = validate_date_format(START_DATE)
        end_date = validate_date_format(END_DATE)
        
        if end_date < start_date:
            sys.exit("Error: END_DATE cannot be earlier than START_DATE")

    return {
        'start': start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'end': end_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    }

def get_detections(query_params, headers):
    """Retrieve detections from the Vision One API."""
    try:
        response = requests.get(API_ENDPOINT, headers=headers, params=query_params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        sys.exit(f"API Request Error: {str(e)}")

def main():
    """Main execution function."""
    # Validate configuration
    validate_config()

    # Initialize search parameters
    time_range = get_time_range()
    query_params = {
        'startDateTime': time_range['start'],
        'endDateTime': time_range['end'],
        'top': RESULTS_PER_CALL,
        'mode': 'detection'
    }

    headers = {
        'Authorization': f'Bearer {API_TOKEN}',
        'TMV1-Query': QUERY_FILTER
    }

    # Initialize collection variables
    all_items = []
    total_fetched = 0

    print("Starting detection retrieval...")
    
    # Fetch data in batches
    while True:
        # Adjust batch size if next pull would exceed MAX_RESULTS
        if MAX_RESULTS and (total_fetched + RESULTS_PER_CALL) > MAX_RESULTS:
            remaining = MAX_RESULTS - total_fetched
            query_params['top'] = remaining

        data = get_detections(query_params, headers)
        items = data.get('items', [])
        batch_size = len(items)
        all_items.extend(items)
        total_fetched += batch_size
        
        print(f"Retrieved {batch_size} detections (Total: {total_fetched})")
        
        # Check stopping conditions
        if MAX_RESULTS and total_fetched >= MAX_RESULTS:
            print("Maximum result limit reached")
            break
        if batch_size < query_params['top']:
            break
        
        next_link = data.get('nextLink')
        if not next_link:
            break
        
        query_params['skipToken'] = next_link.split('skipToken=')[-1]

    # Prepare and write CSV
    try:
        all_fields = set()
        for item in all_items:
            all_fields.update(item.keys())

        print(f"\nWriting {len(all_items)} detections to {OUTPUT_FILE}...")
        
        with open(OUTPUT_FILE, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(all_fields))
            writer.writeheader()
            for item in all_items:
                writer.writerow(item)
        
        print(f"Export completed successfully to {OUTPUT_FILE}")
        
    except IOError as e:
        sys.exit(f"Error writing to CSV: {str(e)}")

if __name__ == "__main__":
    main()