"""Enhanced CPU metrics collector with environment-aware strategies"""
import logging
import time
from typing import List, Dict, Any, Optional
from .base import BaseCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class CPUCollector(BaseCollector):
    """Environment-aware CPU metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "cpu", "CPU usage metrics with environment-aware collection")
        self._last_cpu_times: Optional[Dict[str, Any]] = None
        self._last_collection_time: Optional[float] = None
        self._measurement_interval = getattr(config, 'cpu_measurement_interval', 15.0) if config else 15.0
    
    def collect(self) -> List[MetricValue]:
        """Collect CPU metrics using environment-appropriate strategy"""
        try:
            current_time = time.time()
            
            # Use strategy to collect CPU data
            result = self.collect_with_strategy("cpu")
            
            if not result.is_success:
                logger.warning(f"CPU collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process CPU time data and calculate percentages
            if self._last_cpu_times and self._last_collection_time:
                time_delta = current_time - self._last_collection_time
                if time_delta > 0:
                    cpu_metrics = self._calculate_cpu_percentages(data, time_delta)
                    metrics.extend(cpu_metrics)
            
            # Store current measurements for next calculation
            self._last_cpu_times = data.copy()
            self._last_collection_time = current_time
            
            # Add absolute time metrics
            if "usage_seconds" in data:
                # cgroup data
                metrics.append(MetricValue(
                    name="node_cpu_seconds_total",
                    value=float(data["usage_seconds"]),
                    labels=labels.copy(),
                    help_text="Total CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                ))
            elif "total_time" in data:
                # proc stat data (convert from jiffies to seconds)
                jiffies_per_second = 100  # Standard Linux value
                total_seconds = data["total_time"] / jiffies_per_second
                metrics.append(MetricValue(
                    name="node_cpu_seconds_total",
                    value=total_seconds,
                    labels=labels.copy(),
                    help_text="Total CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                ))
            
            # Individual CPU time components (from proc stat)
            if "user_time" in data:
                jiffies_per_second = 100
                user_seconds = data["user_time"] / jiffies_per_second
                metrics.append(MetricValue(
                    name="node_cpu_user_seconds_total",
                    value=user_seconds,
                    labels=labels.copy(),
                    help_text="Total user CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                ))
            
            if "system_time" in data:
                jiffies_per_second = 100
                system_seconds = data["system_time"] / jiffies_per_second
                metrics.append(MetricValue(
                    name="node_cpu_system_seconds_total",
                    value=system_seconds,
                    labels=labels.copy(),
                    help_text="Total system CPU time spent in seconds",
                    metric_type=MetricType.COUNTER,
                    unit="seconds"
                ))
            
            # Load averages
            for load_type in ["load1", "load5", "load15"]:
                if load_type in data:
                    metrics.append(MetricValue(
                        name=f"node_{load_type}",
                        value=float(data[load_type]),
                        labels=labels.copy(),
                        help_text=f"{load_type.replace('load', '')}-minute load average",
                        metric_type=MetricType.GAUGE
                    ))
            
            # CPU count
            if "cpu_count" in data:
                metrics.append(MetricValue(
                    name="node_cpu_count",
                    value=float(data["cpu_count"]),
                    labels=labels.copy(),
                    help_text="Number of CPU cores",
                    metric_type=MetricType.GAUGE
                ))
            
            # CPU frequency information (host environments)
            freq_fields = [
                ("max_frequency_khz", "node_cpu_frequency_max_hertz", "Maximum CPU frequency in Hz"),
                ("min_frequency_khz", "node_cpu_frequency_min_hertz", "Minimum CPU frequency in Hz"),
                ("current_frequency_khz", "node_cpu_frequency_hertz", "Current CPU frequency in Hz"),
            ]
            
            for data_key, metric_name, help_text in freq_fields:
                if data_key in data:
                    # Convert kHz to Hz
                    freq_hz = data[data_key] * 1000
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(freq_hz),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=MetricType.GAUGE,
                        unit="hertz"
                    ))
            
            # Process statistics (host environments)
            process_fields = [
                ("running_processes", "node_procs_running", "Number of running processes"),
                ("total_processes", "node_procs_total", "Total number of processes (from loadavg)"),
                ("processes_created", "node_forks_total", "Total number of processes created"),
                ("processes_blocked", "node_procs_blocked", "Number of blocked processes"),
            ]
            
            for data_key, metric_name, help_text in process_fields:
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
            
            # Container CPU limits (container environments)
            if "quota_microseconds" in data and "period_microseconds" in data:
                quota = data["quota_microseconds"]
                period = data["period_microseconds"]
                if quota > 0 and period > 0:
                    cpu_limit = quota / period
                    metrics.append(MetricValue(
                        name="node_cpu_limit_ratio",
                        value=cpu_limit,
                        labels=labels.copy(),
                        help_text="CPU limit as ratio of available cores",
                        metric_type=MetricType.GAUGE
                    ))
            
            logger.debug(f"Collected {len(metrics)} CPU metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"CPU collection failed: {e}")
            return []
    
    def _calculate_cpu_percentages(self, current_data: Dict[str, Any], time_delta: float) -> List[MetricValue]:
        """Calculate CPU percentage metrics from time deltas"""
        metrics = []
        labels = self.get_standard_labels()
        
        try:
            # Handle different data formats
            if "total_time" in current_data and "total_time" in self._last_cpu_times:
                # proc stat format
                current_total = current_data["total_time"]
                last_total = self._last_cpu_times["total_time"]
                total_delta = current_total - last_total
                
                if total_delta > 0:
                    # Calculate overall CPU usage percentage
                    if "idle_time" in current_data and "idle_time" in self._last_cpu_times:
                        current_idle = current_data["idle_time"]
                        last_idle = self._last_cpu_times["idle_time"]
                        idle_delta = current_idle - last_idle
                        
                        cpu_usage_percent = ((total_delta - idle_delta) / total_delta) * 100
                        metrics.append(MetricValue(
                            name="node_cpu_usage_percent",
                            value=max(0.0, min(100.0, cpu_usage_percent)),
                            labels=labels.copy(),
                            help_text="CPU usage percentage",
                            metric_type=MetricType.GAUGE,
                            unit="percent"
                        ))
                    
                    # Calculate individual component percentages
                    cpu_components = [
                        ("user_time", "node_cpu_user_percent", "CPU time spent in user mode percentage"),
                        ("system_time", "node_cpu_system_percent", "CPU time spent in system mode percentage"),
                        ("iowait_time", "node_cpu_iowait_percent", "CPU time spent waiting for I/O percentage"),
                        ("irq_time", "node_cpu_irq_percent", "CPU time spent servicing interrupts percentage"),
                        ("softirq_time", "node_cpu_softirq_percent", "CPU time spent servicing soft interrupts percentage"),
                        ("steal_time", "node_cpu_steal_percent", "CPU time stolen by hypervisor percentage"),
                        ("guest_time", "node_cpu_guest_percent", "CPU time spent running guest VMs percentage"),
                    ]
                    
                    for data_key, metric_name, help_text in cpu_components:
                        if data_key in current_data and data_key in self._last_cpu_times:
                            current_value = current_data[data_key]
                            last_value = self._last_cpu_times[data_key]
                            component_delta = current_value - last_value
                            
                            if component_delta >= 0:
                                component_percent = (component_delta / total_delta) * 100
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=max(0.0, min(100.0, component_percent)),
                                    labels=labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.GAUGE,
                                    unit="percent"
                                ))
            
            elif "usage_seconds" in current_data and "usage_seconds" in self._last_cpu_times:
                # cgroup format - calculate usage rate
                current_usage = current_data["usage_seconds"]
                last_usage = self._last_cpu_times["usage_seconds"]
                usage_delta = current_usage - last_usage
                
                if usage_delta >= 0 and time_delta > 0:
                    # Get CPU count for normalization
                    cpu_count = current_data.get("cpu_count", 1)
                    if "quota_microseconds" in current_data and "period_microseconds" in current_data:
                        quota = current_data["quota_microseconds"]
                        period = current_data["period_microseconds"]
                        if quota > 0 and period > 0:
                            cpu_count = quota / period
                    
                    # Calculate CPU usage percentage
                    max_possible_usage = time_delta * cpu_count
                    if max_possible_usage > 0:
                        cpu_usage_percent = (usage_delta / max_possible_usage) * 100
                        metrics.append(MetricValue(
                            name="node_cpu_usage_percent",
                            value=max(0.0, min(100.0, cpu_usage_percent)),
                            labels=labels.copy(),
                            help_text="CPU usage percentage",
                            metric_type=MetricType.GAUGE,
                            unit="percent"
                        ))
        
        except Exception as e:
            logger.warning(f"Failed to calculate CPU percentages: {e}")
        
        return metrics