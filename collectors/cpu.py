"""CPU metrics collector for LXC containers"""
import time
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType
from utils.cgroup import CgroupReader
from logging_config import get_logger

logger = get_logger(__name__)


class CPUCollector(BaseCollector):
    """Collect CPU usage, load averages, and CPU count metrics"""
    
    def __init__(self, config=None):
        super().__init__(config, "cpu", "LXC container CPU usage and load metrics")
        self.cgroup_reader = CgroupReader()
        self._last_collection_time = 0
        
    def collect(self) -> List[MetricValue]:
        """Collect CPU metrics"""
        metrics = []
        current_time = time.time()
        
        try:
            # Get standard labels for all CPU metrics
            standard_labels = self.get_standard_labels()
            
            # Collect CPU usage statistics
            cpu_stats = self.cgroup_reader.get_cpu_stats()
            if cpu_stats:
                metrics.extend(self._create_cpu_usage_metrics(cpu_stats, standard_labels))
            
            # Collect load averages (system-wide)
            load_stats = self.cgroup_reader.get_load_averages()
            if load_stats:
                metrics.extend(self._create_load_metrics(load_stats, standard_labels))
            
            # Collect CPU count
            cpu_count = self.cgroup_reader.get_cpu_count()
            if cpu_count > 0:
                metrics.append(
                    MetricValue(
                        name="node_cpu_count",
                        value=cpu_count,
                        labels=standard_labels,
                        help_text="Number of CPU cores",
                        metric_type=MetricType.GAUGE
                    )
                )
            
            self._last_collection_time = current_time
            logger.debug(f"Collected {len(metrics)} CPU metrics")
            
        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {e}")
        
        return metrics
    
    def _create_cpu_usage_metrics(self, cpu_stats: dict, labels: dict) -> List[MetricValue]:
        """Create CPU usage metrics from cgroup stats"""
        metrics = []
        
        # CPU usage percentage (if available)
        if 'cpu_usage_percent' in cpu_stats:
            metrics.append(
                MetricValue(
                    name="node_cpu_usage_percent",
                    value=cpu_stats['cpu_usage_percent'],
                    labels=labels,
                    help_text="CPU usage percentage",
                    metric_type=MetricType.GAUGE,
                    unit="percent"
                )
            )
        
        # Total CPU time in seconds (cumulative counter)
        if 'cpu_usage_ns' in cpu_stats:
            cpu_seconds = cpu_stats['cpu_usage_ns'] / 1_000_000_000
            metrics.append(
                MetricValue(
                    name="node_cpu_seconds_total",
                    value=cpu_seconds,
                    labels=labels,
                    help_text="Total CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                )
            )
        
        # User CPU time percentage
        if 'cpu_user_percent' in cpu_stats:
            metrics.append(
                MetricValue(
                    name="node_cpu_user_percent",
                    value=cpu_stats['cpu_user_percent'],
                    labels=labels,
                    help_text="CPU time spent in user mode percentage",
                    metric_type=MetricType.GAUGE,
                    unit="percent"
                )
            )
        
        # System CPU time percentage
        if 'cpu_system_percent' in cpu_stats:
            metrics.append(
                MetricValue(
                    name="node_cpu_system_percent",
                    value=cpu_stats['cpu_system_percent'],
                    labels=labels,
                    help_text="CPU time spent in system mode percentage",
                    metric_type=MetricType.GAUGE,
                    unit="percent"
                )
            )
        
        # User CPU time in seconds (cumulative counter)
        if 'cpu_user_ns' in cpu_stats:
            user_seconds = cpu_stats['cpu_user_ns'] / 1_000_000_000
            metrics.append(
                MetricValue(
                    name="node_cpu_user_seconds_total",
                    value=user_seconds,
                    labels=labels,
                    help_text="Total user CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                )
            )
        
        # System CPU time in seconds (cumulative counter)
        if 'cpu_system_ns' in cpu_stats:
            system_seconds = cpu_stats['cpu_system_ns'] / 1_000_000_000
            metrics.append(
                MetricValue(
                    name="node_cpu_system_seconds_total",
                    value=system_seconds,
                    labels=labels,
                    help_text="Total system CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                )
            )
        
        # Idle CPU time (if available from fallback)
        if 'cpu_idle_ns' in cpu_stats:
            idle_seconds = cpu_stats['cpu_idle_ns'] / 1_000_000_000
            metrics.append(
                MetricValue(
                    name="node_cpu_idle_seconds_total",
                    value=idle_seconds,
                    labels=labels,
                    help_text="Total idle CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                )
            )
        
        return metrics
    
    def _create_load_metrics(self, load_stats: dict, labels: dict) -> List[MetricValue]:
        """Create load average metrics"""
        metrics = []
        
        load_periods = [
            ('load1', 'node_load1', '1-minute load average'),
            ('load5', 'node_load5', '5-minute load average'),
            ('load15', 'node_load15', '15-minute load average')
        ]
        
        for load_key, metric_name, help_text in load_periods:
            if load_key in load_stats:
                metrics.append(
                    MetricValue(
                        name=metric_name,
                        value=load_stats[load_key],
                        labels=labels,
                        help_text=help_text,
                        metric_type=MetricType.GAUGE
                    )
                )
        
        return metrics
    
    def get_collection_interval_hint(self) -> float:
        """Suggest collection interval for CPU metrics"""
        # CPU metrics benefit from frequent collection for accurate rates
        return 15.0  # 15 seconds
    
    def requires_rate_calculation(self) -> bool:
        """Indicate that this collector needs rate calculations"""
        return True