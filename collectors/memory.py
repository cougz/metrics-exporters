"""Memory metrics collector"""
import socket
from utils.container import extract_container_id
import os
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType


class MemoryCollector(BaseCollector):
    """Collect memory usage metrics from /proc/meminfo and cgroups"""
    
    def __init__(self, config=None):
        super().__init__(config, "memory", "LXC container memory usage metrics")
    
    def collect(self) -> List[MetricValue]:
        """Collect memory metrics"""
        metrics = []
        
        # Check cgroup v2 memory info
        cgroup_memory_limit = None
        cgroup_memory_usage = None
        
        try:
            if os.path.exists("/sys/fs/cgroup/memory.max"):
                with open("/sys/fs/cgroup/memory.max", "r") as f:
                    cgroup_memory_limit = f.read().strip()
                
                with open("/sys/fs/cgroup/memory.current", "r") as f:
                    cgroup_memory_usage = f.read().strip()
        except (IOError, OSError):
            pass
        
        # Parse /proc/meminfo
        proc_meminfo = {}
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        # Extract numeric value (remove kB suffix)
                        value_kb = value.strip().split()[0]
                        proc_meminfo[key] = int(value_kb)
        except (IOError, OSError, ValueError):
            return metrics
        
        # Calculate memory metrics
        if cgroup_memory_limit == "max" or not cgroup_memory_limit:
            # Use /proc/meminfo
            total_kb = proc_meminfo.get("MemTotal", 0)
            available_kb = proc_meminfo.get("MemAvailable", 0)
            free_kb = proc_meminfo.get("MemFree", 0)
            buffers_kb = proc_meminfo.get("Buffers", 0)
            cached_kb = proc_meminfo.get("Cached", 0)
            
            total_mem = total_kb * 1024
            
            # If total memory is reasonable container size (< 10GB), use it
            if total_mem < 10737418240:
                # Get current usage from cgroup if available
                if cgroup_memory_usage and self.validate_number(cgroup_memory_usage):
                    used_mem = int(cgroup_memory_usage)
                else:
                    # Calculate used memory
                    used_mem = (total_kb - free_kb - buffers_kb - cached_kb) * 1024
                
                free_mem = total_mem - used_mem
                available_mem = available_kb * 1024
            else:
                # Fallback to known 2GB limit
                total_mem = 2147483648  # 2GB
                used_mem = int(cgroup_memory_usage) if cgroup_memory_usage and self.validate_number(cgroup_memory_usage) else 0
                free_mem = total_mem - used_mem
                available_mem = free_mem
        else:
            # Use cgroup limits
            total_mem = int(cgroup_memory_limit)
            used_mem = int(cgroup_memory_usage)
            free_mem = total_mem - used_mem
            available_mem = free_mem
        
        # Create metrics following Prometheus best practices
        standard_labels = self.get_standard_labels()
        
        metrics.extend([
            MetricValue(
                name="node_memory_usage_bytes",
                value=used_mem,
                labels=standard_labels,
                help_text="Memory currently in use in bytes",
                metric_type=MetricType.GAUGE,
                unit="bytes"
            ),
            MetricValue(
                name="node_memory_free_bytes",
                value=free_mem,
                labels=standard_labels,
                help_text="Amount of free memory in bytes",
                metric_type=MetricType.GAUGE,
                unit="bytes"
            ),
            MetricValue(
                name="node_memory_available_bytes",
                value=available_mem,
                labels=standard_labels,
                help_text="Memory available for allocation in bytes",
                metric_type=MetricType.GAUGE,
                unit="bytes"
            ),
            MetricValue(
                name="node_memory_total_bytes",
                value=total_mem,
                labels=standard_labels,
                help_text="Total memory in bytes",
                metric_type=MetricType.GAUGE,
                unit="bytes"
            )
        ])
        
        return metrics