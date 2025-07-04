"""Clean Prometheus exporter for file-based metrics"""
import time
from datetime import datetime
from typing import List, Dict
from pathlib import Path
from .base import BaseExporter
from metrics.models import MetricValue
from config import Config
from logging_config import get_logger


logger = get_logger(__name__)


class CleanPrometheusExporter(BaseExporter):
    """Clean Prometheus exporter that writes metrics to file"""
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.metrics_file = config.prometheus_file
        self._healthy = False
    
    async def start(self) -> None:
        """Initialize the Prometheus exporter"""
        try:
            # Ensure the metrics file directory exists
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_content = "# Prometheus exporter test\n"
            self.metrics_file.write_text(test_content, encoding='utf-8')
            
            self._healthy = True
            logger.info(f"Prometheus exporter started, writing to {self.metrics_file}")
            
        except Exception as e:
            logger.error(f"Failed to start Prometheus exporter: {e}")
            self._healthy = False
            raise
    
    async def export_metrics(self, metrics: List[MetricValue]) -> None:
        """Export metrics to Prometheus file format"""
        if not self._healthy:
            return
        
        try:
            content = self._generate_prometheus_output(metrics)
            
            # Write atomically using temporary file
            temp_file = self.metrics_file.with_suffix('.tmp')
            temp_file.write_text(content, encoding='utf-8')
            temp_file.replace(self.metrics_file)
            
            logger.debug(f"Exported {len(metrics)} metrics to Prometheus file")
            
        except Exception as e:
            logger.error(f"Failed to write Prometheus metrics: {e}")
            self._healthy = False
    
    async def shutdown(self) -> None:
        """Cleanup the Prometheus exporter"""
        self._healthy = False
        logger.info("Prometheus exporter shutdown")
    
    def is_healthy(self) -> bool:
        """Check if exporter is healthy"""
        return self._healthy
    
    def _generate_prometheus_output(self, metrics: List[MetricValue]) -> str:
        """Generate Prometheus exposition format output"""
        if not metrics:
            return "# No metrics available\n"
        
        lines = []
        
        # Add header
        hostname = next((m.labels.get('host_name', 'unknown') for m in metrics if 'host_name' in m.labels), 'unknown')
        timestamp = datetime.now().isoformat()
        lines.append(f"# Node metrics for {hostname}")
        lines.append(f"# Generated at {timestamp}")
        
        # Group metrics by name to add HELP and TYPE comments
        metrics_by_name = self._group_metrics_by_name(metrics)
        
        for metric_name, metric_list in metrics_by_name.items():
            # Add HELP comment (use first metric's help text)
            help_text = metric_list[0].help_text
            lines.append(f"# HELP {metric_name} {help_text}")
            
            # Add TYPE comment
            metric_type = metric_list[0].metric_type.value
            lines.append(f"# TYPE {metric_name} {metric_type}")
            
            # Add metric lines
            for metric in metric_list:
                lines.append(metric.to_prometheus_line())
        
        lines.append("# End of metrics")
        lines.append("")  # Final newline
        
        return "\n".join(lines)
    
    def _group_metrics_by_name(self, metrics: List[MetricValue]) -> Dict[str, List[MetricValue]]:
        """Group metrics by name, preserving order"""
        grouped = {}
        for metric in metrics:
            if metric.name not in grouped:
                grouped[metric.name] = []
            grouped[metric.name].append(metric)
        return grouped