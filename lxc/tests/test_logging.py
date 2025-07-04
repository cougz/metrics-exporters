"""Tests for logging configuration"""
import tempfile
import os
import logging
from pathlib import Path
from unittest.mock import patch
import pytest

from config import Config
from logging_config import (
    setup_structured_logging,
    get_logger,
    log_metrics_collection,
    log_server_startup,
    log_error
)


class TestLoggingConfig:
    """Test logging configuration and structured logging"""
    
    def test_setup_structured_logging(self):
        """Test structured logging setup"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test.log"
            
            # Create config with test log file
            config = Config()
            config.log_file = log_file
            config.log_level = "DEBUG"
            
            # Setup logging
            setup_structured_logging(config)
            
            # Test that log file parent directory is created
            assert log_file.parent.exists()
            
            # Test that logging level is set correctly
            logger = logging.getLogger("test")
            assert logger.isEnabledFor(logging.DEBUG)
    
    def test_get_logger(self):
        """Test getting structured logger"""
        logger = get_logger("test_logger")
        
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'warning')
    
    def test_log_metrics_collection(self):
        """Test structured metrics collection logging"""
        logger = get_logger("test")
        
        # This should not raise an exception
        log_metrics_collection(logger, metrics_count=10, collection_time=0.5, errors=0)
        log_metrics_collection(logger, metrics_count=5, collection_time=1.2, errors=1)
    
    def test_log_server_startup(self):
        """Test structured server startup logging"""
        logger = get_logger("test")
        config = Config()
        
        # This should not raise an exception
        log_server_startup(logger, config)
    
    def test_log_error(self):
        """Test structured error logging"""
        logger = get_logger("test")
        error = ValueError("Test error")
        context = {"component": "test", "request_id": "123"}
        
        # This should not raise an exception
        log_error(logger, error, context)
        log_error(logger, error)  # Without context
    
    def test_development_vs_production_logging(self):
        """Test different logging configurations for development vs production"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test.log"
            config = Config()
            config.log_file = log_file
            
            # Test development mode
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                setup_structured_logging(config)
                logger = get_logger("test")
                logger.info("Test development log")
            
            # Test production mode
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                setup_structured_logging(config)
                logger = get_logger("test")
                logger.info("Test production log")
    
    def test_log_levels(self):
        """Test different log levels"""
        logger = get_logger("test")
        
        # Test all log levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
    
    def test_logger_context_binding(self):
        """Test logger context binding"""
        logger = get_logger("test")
        
        # Test binding context
        bound_logger = logger.bind(request_id="123", user_id="456")
        bound_logger.info("Test message with context")
        
        # Test adding more context
        more_bound = bound_logger.bind(operation="test_op")
        more_bound.info("Test message with more context")