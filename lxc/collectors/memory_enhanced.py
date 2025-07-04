"""Enhanced memory metrics collector with environment-aware strategies"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class MemoryCollector(EnvironmentAwareCollector):
    """Environment-aware memory metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "memory", "Memory usage metrics with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect memory metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect memory data
            result = self.collect_with_strategy("memory")
            
            if not result.is_success:
                logger.warning(f"Memory collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            
            # Process strategy result into standard memory metrics
            data = result.data
            
            # Handle different data formats from different strategies
            if "usage_bytes" in data:
                # cgroup data format
                metrics.append(MetricValue(
                    name="node_memory_usage_bytes",
                    value=float(data["usage_bytes"]),
                    labels=labels.copy(),
                    help_text="Memory currently in use in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            elif "memused_bytes" in data:
                # proc meminfo calculated usage
                metrics.append(MetricValue(
                    name="node_memory_usage_bytes", 
                    value=float(data["memused_bytes"]),
                    labels=labels.copy(),
                    help_text="Memory currently in use in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            
            # Total memory
            if "limit_bytes" in data:
                # cgroup limit
                metrics.append(MetricValue(
                    name="node_memory_total_bytes",
                    value=float(data["limit_bytes"]),
                    labels=labels.copy(),
                    help_text="Total memory in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            elif "memtotal_bytes" in data:
                # proc meminfo total
                metrics.append(MetricValue(
                    name="node_memory_total_bytes",
                    value=float(data["memtotal_bytes"]),
                    labels=labels.copy(),
                    help_text="Total memory in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            
            # Free memory
            if "memfree_bytes" in data:
                metrics.append(MetricValue(
                    name="node_memory_free_bytes",
                    value=float(data["memfree_bytes"]),
                    labels=labels.copy(),
                    help_text="Amount of free memory in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            
            # Available memory
            if "memavailable_bytes" in data:
                metrics.append(MetricValue(
                    name="node_memory_available_bytes",
                    value=float(data["memavailable_bytes"]),
                    labels=labels.copy(),
                    help_text="Memory available for allocation in bytes",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                ))
            
            # Additional memory metrics from different strategies
            memory_fields = [
                ("cache_bytes", "node_memory_cached_bytes", "Cached memory in bytes"),
                ("rss_bytes", "node_memory_rss_bytes", "RSS memory in bytes"),
                ("swap_bytes", "node_memory_swap_bytes", "Swap memory in bytes"),
                ("mapped_file_bytes", "node_memory_mapped_bytes", "Memory mapped files in bytes"),
                ("buffers_bytes", "node_memory_buffers_bytes", "Buffer memory in bytes"),
                ("swaptotal_bytes", "node_memory_swap_total_bytes", "Total swap memory in bytes"),
                ("swapfree_bytes", "node_memory_swap_free_bytes", "Free swap memory in bytes"),
                ("swapused_bytes", "node_memory_swap_used_bytes", "Used swap memory in bytes"),
                ("dirty_bytes", "node_memory_dirty_bytes", "Dirty memory in bytes"),
                ("writeback_bytes", "node_memory_writeback_bytes", "Writeback memory in bytes"),
            ]
            
            for data_key, metric_name, help_text in memory_fields:
                if data_key in data:
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(data[data_key]),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=MetricType.GAUGE,
                        unit="bytes"
                    ))
            
            # VM statistics (host environments)
            vm_fields = [
                ("vm_pgfault", "node_memory_page_faults_total", "Total page faults"),
                ("vm_pgmajfault", "node_memory_major_page_faults_total", "Major page faults"),
                ("vm_pgpgin", "node_memory_pages_in_total", "Pages paged in"),
                ("vm_pgpgout", "node_memory_pages_out_total", "Pages paged out"),
                ("vm_pswpin", "node_memory_swap_in_total", "Swap pages in"),
                ("vm_pswpout", "node_memory_swap_out_total", "Swap pages out"),
            ]
            
            for data_key, metric_name, help_text in vm_fields:
                if data_key in data:
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(data[data_key]),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=MetricType.COUNTER
                    ))
            
            logger.debug(f"Collected {len(metrics)} memory metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Memory collection failed: {e}")
            return []