"""Configuration management for LXC Metrics Exporter"""
import os
from typing import Dict, List, Optional


class Config:
    """Configuration class with environment-based settings"""
    
    def __init__(self):
        # Core settings
        self.collection_interval = int(os.getenv('COLLECTION_INTERVAL', '30'))
        self.metrics_port = int(os.getenv('METRICS_PORT', '9100'))
        self.metrics_host = os.getenv('METRICS_HOST', '0.0.0.0')
        
        # Export configuration
        self.prometheus_enabled = os.getenv('PROMETHEUS_ENABLED', 'true').lower() == 'true'
        self.prometheus_file = os.getenv('PROMETHEUS_FILE', '/opt/lxc-metrics-exporter/data/metrics.prom')
        
        # OpenTelemetry configuration
        self.otel_enabled = os.getenv('OTEL_ENABLED', 'false').lower() == 'true'
        self.otel_endpoint = os.getenv('OTEL_ENDPOINT', None)
        self.otel_headers = self._parse_otel_headers()
        self.otel_insecure = os.getenv('OTEL_INSECURE', 'true').lower() == 'true'
        self.otel_service_name = os.getenv('OTEL_SERVICE_NAME', 'lxc-metrics-exporter')
        self.otel_service_version = os.getenv('OTEL_SERVICE_VERSION', '1.0.0')
        
        # Collector settings
        self.enabled_collectors = self._parse_list(os.getenv('ENABLED_COLLECTORS', 'memory,disk,process'))
        
        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', '/opt/lxc-metrics-exporter/logs/app.log')
        
        # Service settings
        self.service_name = "lxc-metrics-exporter"
        self.service_version = "1.0.0"
        
        # Validate configuration
        self._validate()
    
    def _parse_otel_headers(self) -> Dict[str, str]:
        """Parse OpenTelemetry headers from environment"""
        headers_str = os.getenv('OTEL_HEADERS', '')
        headers = {}
        if headers_str:
            for header in headers_str.split(','):
                if '=' in header:
                    key, value = header.split('=', 1)
                    headers[key.strip()] = value.strip()
        return headers
    
    def _parse_list(self, value: str) -> List[str]:
        """Parse comma-separated list from environment variable"""
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item.strip()]
    
    def _validate(self):
        """Validate configuration settings"""
        if self.otel_enabled and not self.otel_endpoint:
            raise ValueError("OTEL_ENDPOINT must be set when OTEL_ENABLED is true")
        
        if self.collection_interval < 1:
            raise ValueError("COLLECTION_INTERVAL must be at least 1 second")
        
        if not (1 <= self.metrics_port <= 65535):
            raise ValueError("METRICS_PORT must be between 1 and 65535")
    
    def is_collector_enabled(self, collector_name: str) -> bool:
        """Check if a specific collector is enabled"""
        return collector_name in self.enabled_collectors
    
    def get_otel_resource_attributes(self) -> Dict[str, str]:
        """Get OpenTelemetry resource attributes"""
        return {
            "service.name": self.otel_service_name,
            "service.version": self.otel_service_version,
            "service.instance.id": os.uname().nodename,
        }