"""Prometheus format exporter"""
import os
import time
import logging
from typing import List
from datetime import datetime
from ..models import MetricValue


logger = logging.getLogger(__name__)


class PrometheusExporter:
    """Export metrics in Prometheus format"""
    
    def __init__(self, config=None):
        self.config = config
        self.metrics_file = getattr(config, 'prometheus_file', '/opt/lxc-metrics-exporter/data/metrics.prom')
    
    def export_metrics(self, metrics: List[MetricValue]) -> str:
        """Convert metrics to Prometheus format"""
        lines = []
        
        # Add header
        lines.append("# OpenTelemetry metrics for LXC")
        lines.append(f"# Generated at {datetime.now().astimezone().isoformat()}")
        
        # Group metrics by name to avoid duplicate TYPE comments
        metrics_by_name = {}
        for metric in metrics:
            if metric.name not in metrics_by_name:
                metrics_by_name[metric.name] = []
            metrics_by_name[metric.name].append(metric)
        
        # Output metrics
        for metric_name, metric_list in metrics_by_name.items():
            # Add TYPE comment (use the first metric's type)
            lines.append(f"# TYPE {metric_name} {metric_list[0].metric_type.value}")
            
            # Add all metrics with this name
            for metric in metric_list:
                lines.append(metric.to_prometheus_line())
        
        lines.append("# End of metrics")
        return "\n".join(lines)
    
    def write_metrics_file(self, metrics: List[MetricValue]) -> bool:
        """Write metrics to file atomically"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            
            # Generate content
            content = self.export_metrics(metrics)
            
            # Write to temp file first
            temp_file = f"{self.metrics_file}.tmp"
            with open(temp_file, 'w') as f:
                f.write(content)
            
            # Atomic move
            os.rename(temp_file, self.metrics_file)
            
            # Set permissions
            os.chmod(self.metrics_file, 0o644)
            
            # Try to set ownership (might fail if not root)
            try:
                import pwd
                import grp
                otelcol_user = pwd.getpwnam('otelcol')
                otelcol_group = grp.getgrnam('otelcol')
                os.chown(self.metrics_file, otelcol_user.pw_uid, otelcol_group.gr_gid)
            except (KeyError, OSError):
                pass  # Ignore if user/group doesn't exist or no permission
            
            logger.debug(f"Written {len(metrics)} metrics to {self.metrics_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing metrics file: {e}")
            return False
    
    def read_metrics_file(self) -> str:
        """Read current metrics file content"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    return f.read()
            return "# No metrics available\n"
        except Exception as e:
            logger.error(f"Error reading metrics file: {e}")
            return f"# Error reading metrics: {e}\n"