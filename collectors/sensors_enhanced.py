"""Enhanced sensors collector for hardware temperature monitoring"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class SensorsCollector(EnvironmentAwareCollector):
    """Environment-aware sensors collector for temperature monitoring"""
    
    def __init__(self, config=None):
        super().__init__(config, "sensors", "Hardware temperature sensors with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect sensor metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect sensor data
            result = self.collect_with_strategy("sensors")
            
            if not result.is_success:
                logger.warning(f"Sensors collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process CPU temperature sensors
            if "cpu_temperatures" in data:
                for sensor_info in data["cpu_temperatures"]:
                    if isinstance(sensor_info, dict):
                        sensor_labels = labels.copy()
                        sensor_labels.update({
                            "sensor": sensor_info.get("sensor_name", "unknown"),
                            "chip": sensor_info.get("chip", "unknown"),
                            "feature": sensor_info.get("feature", "unknown")
                        })
                        
                        # Current temperature
                        if "temp_celsius" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_temp_celsius",
                                value=float(sensor_info["temp_celsius"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor temperature in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
                        
                        # Critical temperature threshold
                        if "temp_crit_celsius" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_temp_crit_celsius",
                                value=float(sensor_info["temp_crit_celsius"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor critical temperature threshold in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
                        
                        # Maximum temperature threshold
                        if "temp_max_celsius" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_temp_max_celsius",
                                value=float(sensor_info["temp_max_celsius"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor maximum temperature threshold in Celsius",
                                metric_type=MetricType.GAUGE,
                                unit="celsius"
                            ))
            
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
            
            # Process additional thermal sensors (fans, voltage, etc.)
            if "thermal_sensors" in data:
                for sensor_info in data["thermal_sensors"]:
                    if isinstance(sensor_info, dict):
                        sensor_labels = labels.copy()
                        sensor_labels.update({
                            "sensor": sensor_info.get("sensor_name", "unknown"),
                            "chip": sensor_info.get("chip", "unknown"),
                            "type": sensor_info.get("sensor_type", "unknown")
                        })
                        
                        # Fan speed
                        if "fan_rpm" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_fan_rpm",
                                value=float(sensor_info["fan_rpm"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor fan speed in RPM",
                                metric_type=MetricType.GAUGE,
                                unit="rpm"
                            ))
                        
                        # Voltage
                        if "voltage_volts" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_voltage_volts",
                                value=float(sensor_info["voltage_volts"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor voltage in volts",
                                metric_type=MetricType.GAUGE,
                                unit="volts"
                            ))
                        
                        # Power consumption
                        if "power_watts" in sensor_info:
                            metrics.append(MetricValue(
                                name="node_hwmon_power_watts",
                                value=float(sensor_info["power_watts"]),
                                labels=sensor_labels.copy(),
                                help_text="Hardware monitor power consumption in watts",
                                metric_type=MetricType.GAUGE,
                                unit="watts"
                            ))
            
            logger.debug(f"Collected {len(metrics)} sensor metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Sensors collection failed: {e}")
            return []