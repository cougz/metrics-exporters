"""Configuration management for LXC Metrics Exporter"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Literal
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from metrics.models import ExportFormat


class Config(BaseSettings):
    """Configuration class with Pydantic validation and environment-based settings"""
    
    # Core settings
    collection_interval: int = Field(default=30, ge=1, description="Collection interval in seconds")
    metrics_port: int = Field(default=9100, ge=1, le=65535, description="Metrics server port")
    metrics_host: str = Field(default="0.0.0.0", description="Metrics server host")
    
    # Export configuration - mutually exclusive formats
    export_format: ExportFormat = Field(default=ExportFormat.OTLP, description="Export format (prometheus or otlp)")
    
    # Prometheus configuration (only used when export_format=PROMETHEUS)
    prometheus_file: Path = Field(default=Path("/opt/metrics-exporters/lxc/data/metrics.prom"), description="Prometheus metrics file path")
    
    # OpenTelemetry configuration (only used when export_format=OTLP)
    otel_endpoint: Optional[str] = Field(default=None, description="OpenTelemetry endpoint URL")
    otel_headers: Dict[str, str] = Field(default_factory=dict, description="OpenTelemetry headers")
    otel_insecure: bool = Field(default=True, description="Use insecure connection for OpenTelemetry")
    otel_service_name: str = Field(default="lxc-metrics-exporter", description="OpenTelemetry service name")
    otel_service_version: str = Field(default="1.0.0", description="OpenTelemetry service version")
    
    # Collector settings
    enabled_collectors: List[str] = Field(default=["memory", "disk", "process"], description="List of enabled collectors")
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", description="Log level")
    log_file: Path = Field(default=Path("/opt/metrics-exporters/lxc/logs/app.log"), description="Log file path")
    
    # Service settings
    service_name: str = Field(default="lxc-metrics-exporter", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")
    
    # Instance identification
    instance_id: Optional[str] = Field(default=None, description="Instance ID (auto-generated if not specified)")
    service_instance_id: Optional[str] = Field(default=None, description="Service instance ID (auto-generated if not specified)")
    
    # Security settings
    trusted_hosts: List[str] = Field(default_factory=list, description="List of trusted hosts")
    rate_limit_requests: int = Field(default=100, ge=1, description="Max requests per window")
    rate_limit_window: int = Field(default=60, ge=1, description="Rate limit window in seconds")
    enable_request_logging: bool = Field(default=True, description="Enable HTTP request logging")
    
    # Performance settings
    otel_batch_size: int = Field(default=100, ge=1, description="OpenTelemetry batch size")
    otel_batch_timeout: float = Field(default=5.0, ge=0.1, description="OpenTelemetry batch timeout in seconds")
    otel_max_queue_size: int = Field(default=1000, ge=1, description="OpenTelemetry max queue size")
    otel_worker_threads: int = Field(default=2, ge=1, description="OpenTelemetry worker threads")
    
    class Config:
        env_prefix = ""
        case_sensitive = False
        
    @validator('otel_endpoint')
    def validate_otel_endpoint(cls, v, values):
        """Validate OpenTelemetry endpoint when OTLP format is selected"""
        export_format = values.get('export_format')
        if export_format == ExportFormat.OTLP and not v:
            raise ValueError("OTEL_ENDPOINT must be set when export_format is 'otlp'")
        return v
    
    @validator('prometheus_file', 'log_file')
    def ensure_parent_directories(cls, v):
        """Ensure parent directories exist for file paths"""
        if isinstance(v, Path):
            v.parent.mkdir(parents=True, exist_ok=True)
        return v
    
    @validator('otel_headers', pre=True)
    def parse_otel_headers(cls, v):
        """Parse OpenTelemetry headers from environment variable"""
        if isinstance(v, str):
            headers = {}
            if v:
                for header in v.split(','):
                    if '=' in header:
                        key, value = header.split('=', 1)
                        headers[key.strip()] = value.strip()
            return headers
        return v or {}
    
    @validator('enabled_collectors', pre=True)
    def parse_enabled_collectors(cls, v):
        """Parse comma-separated list of collectors"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v or []
    
    @validator('trusted_hosts', pre=True)
    def parse_trusted_hosts(cls, v):
        """Parse comma-separated list of trusted hosts"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v or []
    
    def is_collector_enabled(self, collector_name: str) -> bool:
        """Check if a specific collector is enabled"""
        return collector_name in self.enabled_collectors
    
    def is_prometheus_format(self) -> bool:
        """Check if Prometheus export format is selected"""
        return self.export_format == ExportFormat.PROMETHEUS
    
    def is_otlp_format(self) -> bool:
        """Check if OTLP export format is selected"""
        return self.export_format == ExportFormat.OTLP
    
    def get_instance_id(self) -> str:
        """Get or generate instance ID"""
        if self.instance_id:
            return self.instance_id
        # Auto-generate based on hostname and container ID
        import socket
        from utils.container import extract_container_id
        hostname = socket.gethostname()
        container_id = extract_container_id() or "unknown"
        return f"{hostname}:{container_id}"
    
    def get_service_instance_id(self) -> str:
        """Get or generate service instance ID"""
        if self.service_instance_id:
            return self.service_instance_id
        # Use the same as instance_id for consistency
        return self.get_instance_id()
    
    def get_otel_resource_attributes(self) -> Dict[str, str]:
        """Get OpenTelemetry resource attributes"""
        return {
            "service.name": self.otel_service_name,
            "service.version": self.otel_service_version,
            "service.instance.id": self.get_service_instance_id(),
            "instance": self.get_instance_id(),
        }