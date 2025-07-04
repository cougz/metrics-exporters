"""Simplified configuration for OTLP-only export"""
import os
from pathlib import Path
from typing import List, Dict
from pydantic import Field, validator
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    """Simplified configuration - OTLP only"""
    
    # Core settings
    collection_interval: int = Field(default=30, ge=1, description="Collection interval in seconds")
    
    # OTLP settings (required)
    otlp_endpoint: str = Field(..., description="OTLP gRPC endpoint (required)")
    service_name: str = Field(default="metrics-exporter", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")
    otlp_insecure: bool = Field(default=True, description="Use insecure OTLP connection")
    otlp_headers: Dict[str, str] = Field(default_factory=dict, description="OTLP headers")
    
    # Collection settings
    enabled_collectors: List[str] = Field(
        default=["memory", "cpu", "filesystem", "network", "process"], 
        description="Enabled collectors"
    )
    
    # Server settings (for health checks only)
    metrics_port: int = Field(default=9100, ge=1, le=65535, description="Health check server port")
    metrics_host: str = Field(default="0.0.0.0", description="Health check server host")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: Path = Field(default=Path("/opt/metrics-exporters/logs/app.log"), description="Log file")
    
    # Instance identification
    instance_id: str = Field(default="", description="Override instance ID")
    
    class Config:
        env_prefix = ""
        case_sensitive = False
    
    @validator('otlp_endpoint')
    def validate_otlp_endpoint(cls, v):
        if not v:
            raise ValueError("OTLP_ENDPOINT is required")
        return v
    
    @validator('otlp_headers', pre=True)
    def parse_otlp_headers(cls, v):
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
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v or []
    
    @validator('log_file')
    def ensure_log_directory(cls, v):
        if isinstance(v, Path):
            v.parent.mkdir(parents=True, exist_ok=True)
        return v
    
    def get_otlp_resource_attributes(self) -> Dict[str, str]:
        """Get OTLP resource attributes"""
        return {
            "service.name": self.service_name,
            "service.version": self.service_version,
            "service.instance.id": self.instance_id or self._generate_instance_id(),
        }
    
    def _generate_instance_id(self) -> str:
        """Generate instance ID"""
        import socket
        hostname = socket.gethostname()
        
        # Try to get container ID
        try:
            from utils.container import extract_container_id
            container_id = extract_container_id()
            if container_id:
                short_id = container_id[:12]
                return f"{hostname}-{short_id}"
        except:
            pass
        
        return hostname