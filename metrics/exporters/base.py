"""Base exporter interface and factory"""
import abc
from typing import List
from config import Config
from metrics.models import MetricValue, ExportFormat


class BaseExporter(abc.ABC):
    """Abstract base class for metric exporters"""
    
    def __init__(self, config: Config):
        self.config = config
    
    @abc.abstractmethod
    async def start(self) -> None:
        """Initialize the exporter"""
        pass
    
    @abc.abstractmethod
    async def export_metrics(self, metrics: List[MetricValue]) -> None:
        """Export metrics using this exporter"""
        pass
    
    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Cleanup the exporter"""
        pass
    
    @abc.abstractmethod
    def is_healthy(self) -> bool:
        """Check if exporter is healthy"""
        pass


class ExporterFactory:
    """Factory for creating exporters based on configuration"""
    
    @staticmethod
    def create_exporter(config: Config) -> BaseExporter:
        """Create an exporter based on the configured export format"""
        if config.export_format == ExportFormat.PROMETHEUS:
            from .prometheus_clean import CleanPrometheusExporter
            return CleanPrometheusExporter(config)
        elif config.export_format == ExportFormat.OTLP:
            from .otlp_clean import CleanOTLPExporter
            return CleanOTLPExporter(config)
        else:
            raise ValueError(f"Unsupported export format: {config.export_format}")