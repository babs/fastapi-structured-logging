# fastapi-structured-logging

fastapi-structured-logging is a lightweight Python module that provides structured logging utilities and a configurable FastAPI access logging middleware. It configures `structlog` for JSON or console output, enriches log events with OpenTelemetry trace and span identifiers, and exposes an `AccessLogMiddleware` that can record request method, path, query parameters, client IP, user agent, status codes, processing time and more.

The middleware supports filtering, trusted-proxy handling, custom fields and messages, and integrates cleanly with existing Python logging to produce consistent, machine-readable access logs for observability and tracing.

## Usage

```python
from fastapi import FastAPI

import fastapi_structured_logging

# Set output to text if stdout is a tty, structured json if not
fastapi_structured_logging.setup_logging()

logger = fastapi_structured_logging.get_logger()

app = FastAPI()

app.add_middleware(fastapi_structured_logging.AccessLogMiddleware)

```

## Configuration Options

The library provides extensive configuration options to customize logging and access logging behavior.

### setup_logging() Options

- `json_logs` (Optional[bool]): Forces JSON output if True, console output if False. Defaults to JSON if stdout is not a tty (e.g., in containers or files). Example: `setup_logging(json_logs=True)` for always JSON logs.
- `log_level` (str): Sets the logging level (e.g., "DEBUG", "INFO", "WARNING"). Defaults to "INFO". Example: `setup_logging(log_level="DEBUG")` to enable debug logging.

### AccessLogMiddleware Options

The middleware can be configured via an `AccessLogConfig` object passed to the middleware constructor. Example:

```python
from fastapi_structured_logging import AccessLogConfig

config = AccessLogConfig(
    log_level="info",
    include_user_agent=False,
    exclude_paths={"/health"},
    custom_fields={"app_version": "1.0.0"}
)
app.add_middleware(fastapi_structured_logging.AccessLogMiddleware, config=config)
```

Key options include:

- `enabled` (bool): Enables or disables access logging. Default: True.
- `log_level` (str): Log level for access logs ("debug", "info", etc.). Default: "info".
- `include_*` flags: Control which fields are logged, such as `include_method` (request method), `include_path` (request path), `include_query_params` (query parameters), `include_client_ip` (client IP), `include_user_agent` (user agent string), `include_forwarded_headers` (proxy headers), `include_status_code` (response status), `include_process_time` (processing time in ms), `include_content_length` (response content length), `include_referer` (referer header). All default to True except `include_referer` (False).
- `exclude_*` sets: Filter out logs for specific paths (`exclude_paths`), methods (`exclude_methods`), status codes (`exclude_status_codes`), or paths only if status is 200 or 404 (`exclude_paths_if_ok_or_missing`).
- `min_process_time` / `max_process_time` (Optional[float]): Only log requests with processing time within these bounds (in seconds).
- `custom_message` (str): Custom log message. Default: "Access".
- `custom_fields` (Dict[str, Any]): Additional fields to include in every log entry. Example: `{"app_version": "1.0.0"}`.
- `logger_name` (str): Name of the logger to use. Default: "access_log".
- `trusted_proxy` (List[str]): List of CIDR ranges for trusted proxies to extract real client IP. Example: `["10.0.0.0/8", "192.168.0.0/16"]`.

## Convenience functions

- `setup_logging()` initialize `structlog` to use line logging if stdout is a tty or JSONL if not (file, container output etc...)

- `get_logger()` return a `structlog` logger

- `json_serializer()` for fast serialization in `orjson`

    ```python

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
        logger.error("validation exception", validation_error=json_serializer(exc.errors()))
        content = {"status_code": 10422, "message": exc_str, "data": None}
        return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    ```

## Setup dev env

```bash
uv venv
uv pip install -r requirements-dev.txt
pre-commit install
```

## Test

```bash
. venv/bin/activate
uv pip install -e .[full]
pytest --cov-report html --cov-report term --cov-report xml:cov.xml
```

## Build

```bash
echo x.y.z > VERSION
uv pip install -r requirements-release.txt
uv run python -m build -s -w
```
