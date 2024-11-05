# Vision One Detections Export Tool

A Python script that retrieves detection events from Trend Micro's Vision One API and exports them to CSV format.

## Features

- Retrieve detection events from Vision One API
- Filter results using Vision One query syntax
- Export results to CSV format
- Support for time-based queries:
  - Search by number of days in the past
  - Search by specific date range
- Configurable result limits and batch sizes
- Progress tracking during retrieval

## Requirements

- Python 3.6 or higher
- `requests` library

## Installation

1. Download the script `V1DetectionsToCSV.py` directly from the repository.
2. Install required dependencies:
```bash
pip install requests
```

## Configuration

Edit the following variables in `V1DetectionsToCSV.py`:

```python
# API Configuration
API_TOKEN = 'YOUR_API_TOKEN'  # Your Vision One API token

# Search Parameters (Choose one option)
DAYS_TO_SEARCH = 30  # Number of days to search
# OR
START_DATE = "MM-DD-YYYY"  # Start date
END_DATE = "MM-DD-YYYY"    # End date

# Other Parameters
MAX_RESULTS = 20000        # Maximum results to retrieve
RESULTS_PER_CALL = 5000    # Results per API call
QUERY_FILTER = "productCode:PTP AND act:Block"  # Vision One search query
OUTPUT_FILE = 'detections.csv'  # Output filename
```

Alternatively, you can pass these variables via command-line arguments.

Example:
```bash
python V1DetectionsToCSV.py --api_token YOUR_API_TOKEN --days_to_search 30 --max_results 20000 --results_per_call 5000 --query_filter "productCode:PTP AND act:Block" --output_file detections.csv
```

## Usage

1. Configure your API token and search parameters
2. Run the script:
```bash
python V1DetectionsToCSV.py
```

## Output

The script generates a CSV file containing all retrieved detections. The CSV includes all fields returned by the Vision One API for each detection.

## Error Handling

The script includes error handling for:
- Invalid API tokens
- Invalid date formats
- API request errors
- File writing errors
- Configuration validation