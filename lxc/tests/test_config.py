"""Tests for configuration module"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from pydantic import ValidationError

from config import Config


class TestConfig:
    """Test configuration validation and parsing"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = Config()
        
        assert config.collection_interval == 30
        assert config.metrics_port == 9100
        assert config.metrics_host == "0.0.0.0"
        assert config.prometheus_enabled is True
        assert config.otel_enabled is False
        assert config.log_level == "INFO"
        assert config.enabled_collectors == ["memory", "disk", "process"]
    
    def test_environment_override(self):
        """Test configuration override from environment variables"""
        env_vars = {
            "COLLECTION_INTERVAL": "60",
            "METRICS_PORT": "8080",
            "METRICS_HOST": "127.0.0.1",
            "PROMETHEUS_ENABLED": "false",
            "OTEL_ENABLED": "true",
            "OTEL_ENDPOINT": "http://localhost:4317",
            "LOG_LEVEL": "DEBUG",
            "ENABLED_COLLECTORS": "memory,disk"
        }
        
        with patch.dict(os.environ, env_vars):
            config = Config()
            
            assert config.collection_interval == 60
            assert config.metrics_port == 8080
            assert config.metrics_host == "127.0.0.1"
            assert config.prometheus_enabled is False
            assert config.otel_enabled is True
            assert config.otel_endpoint == "http://localhost:4317"
            assert config.log_level == "DEBUG"
            assert config.enabled_collectors == ["memory", "disk"]
    
    def test_validation_collection_interval(self):
        """Test validation of collection interval"""
        with patch.dict(os.environ, {"COLLECTION_INTERVAL": "0"}):
            with pytest.raises(ValidationError):
                Config()
    
    def test_validation_metrics_port(self):
        """Test validation of metrics port"""
        with patch.dict(os.environ, {"METRICS_PORT": "0"}):
            with pytest.raises(ValidationError):
                Config()
                
        with patch.dict(os.environ, {"METRICS_PORT": "70000"}):
            with pytest.raises(ValidationError):
                Config()
    
    def test_validation_otel_endpoint(self):
        """Test validation of OpenTelemetry endpoint"""
        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            with pytest.raises(ValidationError):
                Config()
    
    def test_otel_headers_parsing(self):
        """Test OpenTelemetry headers parsing"""
        headers_str = "Authorization=Bearer token123,X-Custom-Header=value456"
        
        with patch.dict(os.environ, {"OTEL_HEADERS": headers_str}):
            config = Config()
            
            assert config.otel_headers == {
                "Authorization": "Bearer token123",
                "X-Custom-Header": "value456"
            }
    
    def test_enabled_collectors_parsing(self):
        """Test enabled collectors parsing"""
        with patch.dict(os.environ, {"ENABLED_COLLECTORS": "memory, disk , process"}):
            config = Config()
            
            assert config.enabled_collectors == ["memory", "disk", "process"]
    
    def test_is_collector_enabled(self):
        """Test collector enabled check"""
        config = Config()
        
        assert config.is_collector_enabled("memory") is True
        assert config.is_collector_enabled("disk") is True
        assert config.is_collector_enabled("process") is True
        assert config.is_collector_enabled("nonexistent") is False
    
    def test_get_otel_resource_attributes(self):
        """Test OpenTelemetry resource attributes"""
        config = Config()
        attrs = config.get_otel_resource_attributes()
        
        assert "service.name" in attrs
        assert "service.version" in attrs
        assert "service.instance.id" in attrs
        assert attrs["service.name"] == "lxc-metrics-exporter"
        assert attrs["service.version"] == "1.0.0"
    
    def test_directory_creation(self):
        """Test that parent directories are created for file paths"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "subdir" / "test.log"
            prometheus_file = Path(tmp_dir) / "metrics" / "test.prom"
            
            env_vars = {
                "LOG_FILE": str(log_file),
                "PROMETHEUS_FILE": str(prometheus_file)
            }
            
            with patch.dict(os.environ, env_vars):
                config = Config()
                
                assert config.log_file.parent.exists()
                assert config.prometheus_file.parent.exists()