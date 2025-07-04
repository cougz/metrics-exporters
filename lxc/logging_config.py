"""Structured logging configuration for LXC Metrics Exporter"""
import os
import sys
from pathlib import Path
from typing import Any, Dict
import structlog
from structlog.stdlib import LoggerFactory
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer, TimeStamper, add_log_level, StackInfoRenderer
from config import Config


def setup_structured_logging(config: Config) -> None:
    """Setup structured logging with JSON format for production and console for development"""
    
    # Ensure log directory exists
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure processors
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        TimeStamper(fmt="iso"),
        StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Use JSON renderer for production, console for development
    is_development = os.getenv("ENVIRONMENT", "production").lower() == "development"
    if is_development:
        processors.append(ConsoleRenderer())
    else:
        processors.append(JSONRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    import logging
    
    # Create handlers
    handlers = []
    
    # File handler
    file_handler = logging.FileHandler(str(config.log_file))
    file_handler.setLevel(getattr(logging, config.log_level.upper()))
    handlers.append(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, config.log_level.upper()))
    handlers.append(console_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format="%(message)s",
        handlers=handlers
    )
    
    # Set specific logger levels to reduce noise
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('opentelemetry').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)


def add_correlation_id(logger: structlog.stdlib.BoundLogger, correlation_id: str) -> structlog.stdlib.BoundLogger:
    """Add correlation ID to logger context"""
    return logger.bind(correlation_id=correlation_id)


def log_metrics_collection(logger: structlog.stdlib.BoundLogger, metrics_count: int, collection_time: float, errors: int = 0) -> None:
    """Log metrics collection event with structured data"""
    logger.info(
        "Metrics collection completed",
        metrics_count=metrics_count,
        collection_time_seconds=round(collection_time, 3),
        errors=errors,
        event_type="metrics_collection"
    )


def log_server_startup(logger: structlog.stdlib.BoundLogger, config: Config) -> None:
    """Log server startup with configuration details"""
    logger.info(
        "Server starting up",
        service_name=config.service_name,
        service_version=config.service_version,
        collection_interval=config.collection_interval,
        enabled_collectors=config.enabled_collectors,
        prometheus_enabled=config.prometheus_enabled,
        otel_enabled=config.otel_enabled,
        metrics_port=config.metrics_port,
        event_type="server_startup"
    )


def log_error(logger: structlog.stdlib.BoundLogger, error: Exception, context: Dict[str, Any] = None) -> None:
    """Log error with structured context"""
    logger.error(
        "Error occurred",
        error=str(error),
        error_type=type(error).__name__,
        context=context or {},
        event_type="error",
        exc_info=True
    )