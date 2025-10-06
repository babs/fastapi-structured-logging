import ipaddress
import logging
import sys
import time
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Union

import orjson
import structlog
from fastapi import Request
from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from structlog.contextvars import bind_contextvars
from structlog.contextvars import clear_contextvars

try:
    from opentelemetry import trace  # pyright: ignore[reportMissingImports]
    from opentelemetry.sdk.trace import TracerProvider  # pyright: ignore[reportMissingImports]

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


get_logger = structlog.get_logger


def _add_trace_info(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    if OTEL_AVAILABLE:
        span = trace.get_current_span()

        # Initialize tracing if no valid span context exists
        if not span or not span.get_span_context().is_valid:
            if not hasattr(trace, "_TRACER_PROVIDER") or trace._TRACER_PROVIDER is None:
                trace.set_tracer_provider(TracerProvider())
            span = trace.get_current_span()

        # Add trace info if we have a valid span
        if span and span.get_span_context().is_valid:
            context = span.get_span_context()
            event_dict["trace_id"] = format(context.trace_id, "032x")
            event_dict["span_id"] = format(context.span_id, "016x")

    return event_dict


def _drop_color_message_key(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict


def _rename_event_to_message(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def json_serializer(obj: Any, default=None) -> str:
    return orjson.dumps(obj, default=default).decode("utf-8")


def setup_logging(json_logs: Optional[bool] = None, log_level: str = "INFO"):
    if json_logs is None:
        json_logs = not sys.stdout.isatty()

    shared_processors = [
        _add_trace_info,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        _drop_color_message_key,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if json_logs:
        shared_processors.append(_rename_event_to_message)
        shared_processors.append(structlog.processors.format_exc_info)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if json_logs:
        log_renderer = structlog.processors.JSONRenderer(serializer=json_serializer)
    else:
        log_renderer = structlog.dev.ConsoleRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, log_renderer],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
    # Adjust Uvicorn loggers to propagate to root logger properly.
    for log_name in ["uvicorn", "uvicorn.error"]:
        logging.getLogger(log_name).handlers.clear()
        logging.getLogger(log_name).propagate = False
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False


@dataclass
class AccessLogConfig:
    """Configuration for access logging middleware."""

    enabled: bool = True
    log_level: str = "info"  # debug, info, warning, error

    # Fields to include in logs
    include_method: bool = True
    include_path: bool = True
    include_query_params: bool = True
    include_client_ip: bool = True
    include_user_agent: bool = True
    include_forwarded_headers: bool = True
    include_status_code: bool = True
    include_process_time: bool = True
    include_content_length: bool = True
    include_referer: bool = False

    # Filtering options
    exclude_paths_if_ok_or_missing: Set[str] = field(
        default_factory=lambda: {
            "/healthz",
            "/livez",
            "/readyz",
            "/metrics",
        }
    )
    exclude_paths: Set[str] = field(default_factory=lambda: {"/favicon.ico"})
    exclude_methods: Set[str] = field(default_factory=set)
    exclude_status_codes: Set[int] = field(default_factory=set)
    min_process_time: Optional[float] = None  # Only log requests taking longer than this
    max_process_time: Optional[float] = None  # Only log requests taking less than this

    # Custom message format
    custom_message: str = "Access"

    # Additional custom fields
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    # Logger name
    logger_name: str = "access_log"

    # Trusted proxy CIDR ranges
    trusted_proxy: List[str] = field(default_factory=list)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for configurable access logging."""

    def __init__(self, app: ASGIApp, config: Optional[AccessLogConfig] = None):
        super().__init__(app)
        self.config: AccessLogConfig = config or AccessLogConfig()
        self.logger = structlog.get_logger(self.config.logger_name)
        try:
            self._cache_trusted_proxy_networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = [
                ipaddress.ip_network(cidr) for cidr in self.config.trusted_proxy
            ]
        except ValueError:
            self._cache_trusted_proxy_networks = []
            self._cache_trusted_proxy_networks = []

    def __is_trusted_proxy(self, ip: str) -> bool:
        """Check if the given IP is in the trusted proxy CIDR ranges."""
        try:
            client_ip = ipaddress.ip_address(ip)
            for network in self._cache_trusted_proxy_networks:
                if client_ip in network:
                    return True
        except ValueError:
            pass
        return False

    def __should_log_request(self, request: Request, response: Response, process_time: float) -> bool:
        """Determine if this request should be logged based on configuration."""
        if not self.config.enabled:
            return False

        if request.url.path in self.config.exclude_paths:
            return False

        if request.url.path in self.config.exclude_paths_if_ok_or_missing and response.status_code in {
            200,
            404,
        }:
            return False

        if request.method in self.config.exclude_methods:
            return False

        if response.status_code in self.config.exclude_status_codes:
            return False

        if self.config.min_process_time and process_time < self.config.min_process_time:
            return False

        if self.config.max_process_time and process_time > self.config.max_process_time:
            return False

        return True

    def __extract_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP from request headers or connection info."""
        remote_host: Optional[str] = request.client.host if request.client else None
        if remote_host and self.__is_trusted_proxy(remote_host):
            x_forwarded_for: Optional[str] = request.headers.get("x-forwarded-for")
            if x_forwarded_for:
                return x_forwarded_for.split(",")[0].strip()

            x_real_ip: Optional[str] = request.headers.get("x-real-ip")
            if x_real_ip:
                return x_real_ip

        return remote_host

    def __build_context_vars(self, request: Request) -> Dict[str, Any]:
        """Build context variables for structured logging."""
        context_vars = {}

        remote_host = request.client.host if request.client else None
        if remote_host:
            context_vars["remote_host"] = remote_host

        if self.config.include_method:
            context_vars["method"] = request.method

        if self.config.include_path:
            context_vars["path"] = request.url.path

        if self.config.include_query_params and request.query_params:
            context_vars["query_params"] = str(request.query_params)

        if self.config.include_client_ip:
            client_ip = self.__extract_client_ip(request)
            if client_ip:
                context_vars["client_ip"] = client_ip

        if self.config.include_forwarded_headers:
            for header in [
                "x-forwarded-for",
                "x-real-ip",
                "x-forwarded-proto",
                "x-forwarded-host",
                "x-forwarded-port",
            ]:
                value = request.headers.get(header)
                if value:
                    context_vars[header.replace("-", "_")] = value

        if self.config.include_user_agent:
            user_agent = request.headers.get("user-agent")
            if user_agent:
                context_vars["user_agent"] = user_agent

        if self.config.include_referer:
            referer = request.headers.get("referer")
            if referer:
                context_vars["referer"] = referer

        context_vars.update(self.config.custom_fields)

        return context_vars

    def __build_log_data(self, response: Response, process_time: float) -> Dict[str, Any]:
        """Build log data for the access log entry."""
        log_data = {}

        if self.config.include_status_code:
            log_data["status_code"] = response.status_code

        if self.config.include_process_time:
            log_data["process_time_ms"] = round(process_time * 1000, 6)

        if self.config.include_content_length:
            content_length = response.headers.get("content-length")
            if content_length:
                log_data["content_length"] = int(content_length)

        _add_trace_info(None, None, log_data)

        return log_data

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore
        """Process the request and log access information."""

        clear_contextvars()
        context_vars = self.__build_context_vars(request)
        bind_contextvars(**context_vars)

        # Time the request
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        if self.__should_log_request(request, response, process_time):
            log_data = self.__build_log_data(response, process_time)

            log_method = getattr(self.logger, self.config.log_level.lower(), self.logger.info)
            log_method(self.config.custom_message, **log_data)

        return response
