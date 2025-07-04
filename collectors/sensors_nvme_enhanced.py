"""Enhanced NVMe/disk sensors collector for disk temperature monitoring"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class SensorsNVMeCollector(EnvironmentAwareCollector):
    """Environment-aware NVMe/disk sensors collector for temperature monitoring"""
    
    def __init__(self, config=None):
        super().__init__(config, "sensors_nvme", "NVMe/disk temperature sensors with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect NVMe/disk sensor metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect NVMe sensor data
            result = self.collect_with_strategy("sensors_nvme")
            
            if not result.is_success:
                logger.warning(f"NVMe sensors collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process disk temperature sensors (from smartctl)
            if "disk_temperatures" in data:
                for disk_info in data["disk_temperatures"]:
                    if isinstance(disk_info, dict):
                        disk_labels = labels.copy()
                        disk_labels.update({
                            "device": disk_info.get("device", "unknown"),
                            "model": disk_info.get("model", "unknown"),
                            "interface": disk_info.get("interface", "unknown")
                        })
                        
                        # Current disk temperature
                        if "temperature_celsius" in disk_info:
                            metrics.append(MetricValue(
                                name="node_disk_temperature_celsius",
                                value=float(disk_info["temperature_celsius"]),
                                labels=disk_labels.copy(),
                                help_text="Disk temperature in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
                        
                        # Disk temperature warning threshold
                        if "temp_warning_celsius" in disk_info:
                            metrics.append(MetricValue(
                                name="node_disk_temp_warning_celsius",
                                value=float(disk_info["temp_warning_celsius"]),
                                labels=disk_labels.copy(),
                                help_text="Disk temperature warning threshold in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
                        
                        # Disk temperature critical threshold
                        if "temp_critical_celsius" in disk_info:
                            metrics.append(MetricValue(
                                name="node_disk_temp_critical_celsius",
                                value=float(disk_info["temp_critical_celsius"]),
                                labels=disk_labels.copy(),
                                help_text="Disk temperature critical threshold in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
                        
                        # SMART health status
                        if "smart_health" in disk_info:
                            health_value = 1.0 if disk_info["smart_health"] == "PASSED" else 0.0
                            metrics.append(MetricValue(
                                name="node_disk_smart_health_ok",
                                value=health_value,
                                labels=disk_labels.copy(),
                                help_text="Disk SMART health status (1 = healthy, 0 = unhealthy)",
                                metric_type=MetricType.GAUGE
                            ))
            
            logger.debug(f"Collected {len(metrics)} NVMe sensor metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"NVMe sensors collection failed: {e}")
            return []