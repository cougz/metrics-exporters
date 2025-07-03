"""Disk metrics collector"""
import subprocess
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType


class DiskCollector(BaseCollector):
    """Collect disk usage metrics using df command"""
    
    @property
    def name(self) -> str:
        return "disk"
    
    @property
    def help_text(self) -> str:
        return "LXC container disk usage metrics"
    
    def collect(self) -> List[MetricValue]:
        """Collect disk metrics"""
        metrics = []
        
        try:
            # Get disk usage using df command
            result = subprocess.run(["df", "-T", "/"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    # Parse df output: Filesystem Type 1K-blocks Used Available Use% Mounted-on
                    parts = lines[1].split()
                    if len(parts) >= 7:
                        filesystem = parts[0]
                        fstype = parts[1]
                        size_kb = int(parts[2])
                        used_kb = int(parts[3])
                        avail_kb = int(parts[4])
                        mountpoint = parts[6]
                        
                        # Convert to bytes
                        size_bytes = size_kb * 1024
                        used_bytes = used_kb * 1024
                        avail_bytes = avail_kb * 1024
                        
                        # Format labels
                        disk_labels = {
                            "device": filesystem,
                            "mountpoint": mountpoint,
                            "fstype": fstype
                        }
                        
                        # Create metrics following Prometheus best practices
                        metrics.extend([
                            MetricValue(
                                name="node_filesystem_usage_bytes",
                                value=used_bytes,
                                labels=disk_labels,
                                help_text="Filesystem space used in bytes",
                                metric_type=MetricType.GAUGE
                            ),
                            MetricValue(
                                name="node_filesystem_avail_bytes",
                                value=avail_bytes,
                                labels=disk_labels,
                                help_text="Filesystem space available to non-root users in bytes",
                                metric_type=MetricType.GAUGE
                            ),
                            MetricValue(
                                name="node_filesystem_size_bytes",
                                value=size_bytes,
                                labels=disk_labels,
                                help_text="Filesystem size in bytes",
                                metric_type=MetricType.GAUGE
                            )
                        ])
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, IndexError):
            pass
        
        return metrics