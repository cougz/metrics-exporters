#!/usr/bin/env python3
"""Main entry point for LXC Metrics Exporter"""
import logging
import sys
import uvicorn
from config import Config
from app.server import MetricsServer


def setup_logging(config: Config):
    """Setup logging configuration"""
    # Ensure log directory exists
    import os
    os.makedirs(os.path.dirname(config.log_file), exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific logger levels
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('opentelemetry').setLevel(logging.WARNING)


def main():
    """Main application entry point"""
    try:
        # Load configuration
        config = Config()
        
        # Setup logging
        setup_logging(config)
        logger = logging.getLogger(__name__)
        logger.info("Starting LXC Metrics Exporter")
        
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
        print(f"Failed to start application: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()