# Vision One Detections Export Tool

A Python script that efficiently retrieves detection events from Trend Micro's Vision One API using multi-threading and exports them to CSV format with advanced rate limiting and error handling.

## Features

- Multi-threaded detection retrieval for improved performance
- Configurable rate limiting (per second, minute, and hour)
- YAML-based configuration
- Automatic retry mechanism for failed API requests
- Comprehensive logging system
- Thread-safe CSV writing with proper ordering
- Support for large datasets with pagination
- Configurable request timeouts
- Automatic flattening of nested JSON data
- Progress tracking and status reporting

## Requirements

- Python 3.6 or higher
- Required packages:
  ```bash
  pip install requests pyyaml
  ```

## Configuration

The script uses a YAML configuration file (`config.yaml`) for all settings. Here's an example configuration:

```yaml
api_token: "YOUR_API_TOKEN"
api_endpoint: "https://api.xdr.trendmicro.com/v3.0/search/detections"
start_date: "2024-10-20T00:00:00Z"
end_date: "2024-10-31T23:59:59Z"
max_results: 1000000
results_per_call: 5000
query_filter: "productCode:PTP AND act:Block"
output_file: "detections.csv"
checkpoint_file: "checkpoint.json"
num_threads: 5
request_timeout: 60
rate_limit_per_second: 5
rate_limit_minute: 20
rate_limit_hour: 800
```

### Configuration Parameters

- `api_token`: Your Vision One API token
- `api_endpoint`: Vision One API endpoint URL
- `start_date`: Start date for detection retrieval (ISO 8601 format)
- `end_date`: End date for detection retrieval (ISO 8601 format)
- `max_results`: Maximum number of results to retrieve
- `results_per_call`: Number of results per API call
- `query_filter`: Vision One search query filter
- `output_file`: Output CSV filename
- `checkpoint_file`: File to store progress checkpoints
- `num_threads`: Number of concurrent threads
- `request_timeout`: API request timeout in seconds
- `rate_limit_per_second`: Maximum requests per second
- `rate_limit_minute`: Maximum requests per minute
- `rate_limit_hour`: Maximum requests per hour

## Threading Logic

The script implements a sophisticated multi-threading approach:

1. **Time-Based Partitioning**: 
   - The total time range is divided into equal intervals based on `num_threads`
   - Each thread is assigned a specific time interval to process

2. **Thread Pool Execution**:
   - Uses Python's `ThreadPoolExecutor` for managed thread execution
   - Threads are started with a small delay to prevent API overload
   - Each thread processes its assigned time interval independently

3. **Rate Limiting**:
   - Implements a thread-safe `RateLimiter` class
   - Manages request rates at second, minute, and hour levels
   - Uses a sliding window approach with deque data structure
   - Automatically pauses threads when limits are reached

4. **Thread-Safe Operations**:
   - CSV writing is protected by locks to prevent concurrent access
   - Counter updates are thread-safe using lock mechanisms
   - Field name tracking is synchronized across threads

5. **Error Handling**:
   - Automatic retry mechanism for failed requests
   - Comprehensive logging of thread-specific errors
   - Graceful shutdown on critical errors

## Output

The script generates a CSV file with the following characteristics:

- All fields from the Vision One API are included
- Nested JSON structures are flattened
- List fields are converted to comma-separated strings
- Results are properly ordered by event timestamp
- Thread-safe writing ensures data integrity

## Logging

The script provides comprehensive logging:

- Console output for general progress
- File logging for warnings and errors
- Thread-specific logging
- Detailed error tracking and debugging information

## Usage

1. Create a `config.yaml` file with your settings
2. Run the script:
```bash
python V1DetectionsToCSV.py
```

## Error Handling

The script includes robust error handling for:
- API authentication failures
- Rate limit violations
- Network timeouts
- Invalid configuration
- Data processing errors
- File I/O issues
- Thread synchronization problems

## Performance Considerations

- Adjust `num_threads` based on your API rate limits and system capabilities
- Monitor rate limiting logs to optimize request parameters
- Consider reducing `results_per_call` if processing large data sets
- Use the checkpoint file for resumable operations