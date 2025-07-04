#!/usr/bin/env python3
"""Main entry point for LXC Metrics Exporter"""
import sys
import uvicorn
from config import Config
from app.server import MetricsServer
from logging_config import setup_structured_logging, get_logger, log_server_startup, log_error


def main():
    """Main application entry point"""
    try:
        # Load configuration
        config = Config()
        
        # Setup structured logging
        setup_structured_logging(config)
        logger = get_logger(__name__)
        
        # Log startup
        log_server_startup(logger, config)
        
        # Create server
        server = MetricsServer(config)
        app = server.get_app()
        
        # Run server
        uvicorn.run(
            app,
            host=config.metrics_host,
            port=config.metrics_port,
            log_config=None  # We handle logging ourselves
        )
        
    except Exception as e:
        logger = get_logger(__name__)
        log_error(logger, e, {"component": "main", "phase": "startup"})
        sys.exit(1)


if __name__ == '__main__':
    main()