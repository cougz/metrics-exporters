"""Enhanced process metrics collector with environment-aware strategies"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class ProcessCollector(EnvironmentAwareCollector):
    """Environment-aware process metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "process", "Process metrics with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect process metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect process data
            result = self.collect_with_strategy("process")
            
            if not result.is_success:
                logger.warning(f"Process collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Basic process count
            if "process_count" in data:
                metrics.append(MetricValue(
                    name="node_processes_total",
                    value=float(data["process_count"]),
                    labels=labels.copy(),
                    help_text="Total number of processes (from /proc directory count)",
                    metric_type=MetricType.GAUGE,
                    unit="1"
                ))
            
            # Process state metrics (host environments)
            state_metrics = [
                ("processes_running", "node_procs_running", "Number of running processes"),
                ("processes_blocked", "node_procs_blocked", "Number of blocked processes"),
                ("zombie_count", "node_processes_zombie", "Number of zombie processes"),
                ("processes_created", "node_forks_total", "Total number of processes created"),
            ]
            
            for data_key, metric_name, help_text in state_metrics:
                if data_key in data:
                    metric_type = MetricType.COUNTER if "created" in data_key or "forks" in metric_name else MetricType.GAUGE
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(data[data_key]),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=metric_type,
                        unit="1"
                    ))
            
            logger.debug(f"Collected {len(metrics)} process metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Process collection failed: {e}")
            return []