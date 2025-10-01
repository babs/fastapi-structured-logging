# fastapi-structured-logging Example

This example demonstrates how to integrate structured logging into a FastAPI application using the `fastapi-structured-logging` library. It showcases:

- Setting up structured logging with JSON output
- Adding access log middleware for request logging
- Custom exception handling with structured error logging
- Basic FastAPI endpoints with contextual logging

## Prerequisites

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

1. Create a virtual environment:

    ```bash
    uv venv
    ```

2. Install dependencies:

    ```bash
    uv pip install -r requirements.txt
    ```

3. Install OpenTelemetry auto-instrumentation:

    ```bash
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -
    ```

## Integration

```python
from fastapi import FastAPI

import fastapi_structured_logging

# Set output to text if stdout is a tty, structured json if not
fastapi_structured_logging.setup_logging()

logger = fastapi_structured_logging.get_logger()

app = FastAPI()

app.add_middleware(fastapi_structured_logging.AccessLogMiddleware)

```

## Running the Example

Run the FastAPI application with OpenTelemetry instrumentation:

```bash
uv run opentelemetry-instrument uvicorn example1:app
```

The server will start on `http://0.0.0.0:8000`.

## Testing the Example

- Visit `http://localhost:8000/` for the root endpoint
- Visit `http://localhost:8000/hello?who=World` for the hello endpoint
- Try invalid requests to see validation error logging

## Expected Output

When running, you'll see structured JSON logs for:

- HTTP requests (via middleware)
- Endpoint-specific messages
- Error handling

Example log output (formatted for readability):

### Application log

```json
{
    "context_info1": "value1",
    "context_info2": "value2",
    "trace_id": "4c2c057a18cfff3a0709e2c04454a60d",
    "span_id": "25d9ce4aab9e8ad9",
    "method": "GET",
    "client_ip": "127.0.0.1",
    "path": "/hello",
    "user_agent": "curl/8.5.0",
    "remote_host": "127.0.0.1",
    "query_params": "who=a",
    "logger": "example1",
    "level": "info",
    "timestamp": "2025-10-01T06:16:28.707054Z",
    "message": "log line message"
}
```

### Access log

```json
{
    "status_code": 200,
    "process_time_ms": 0.985861,
    "content_length": 21,
    "trace_id": "4c2c057a18cfff3a0709e2c04454a60d",
    "span_id": "25d9ce4aab9e8ad9",
    "method": "GET",
    "client_ip": "127.0.0.1",
    "path": "/hello",
    "user_agent": "curl/8.5.0",
    "remote_host": "127.0.0.1",
    "query_params": "who=a",
    "logger": "access_log",
    "level": "info",
    "timestamp": "2025-10-01T06:16:28.707480Z",
    "message": "Access"
}
```
