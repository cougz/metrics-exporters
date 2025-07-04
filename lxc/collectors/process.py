"""Process metrics collector"""
import socket
from utils.container import extract_container_id
import subprocess
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType


class ProcessCollector(BaseCollector):
    """Collect process count metrics using ps command"""
    
    def __init__(self, config=None):
        super().__init__(config, "process", "LXC container process count metrics")
    
    def collect(self) -> List[MetricValue]:
        """Collect process metrics"""
        metrics = []
        
        try:
            # Count processes using ps
            result = subprocess.run(["ps", "-A", "--no-headers"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                process_count = len(result.stdout.strip().split('\n'))
                
                metrics.extend([
                    MetricValue(
                        name="node_processes_total",
                        value=process_count,
                        labels={"host_name": socket.gethostname(), "container_id": extract_container_id() or "unknown"},
                        help_text="Number of processes",
                        metric_type=MetricType.GAUGE
                    )
                ])
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        return metrics