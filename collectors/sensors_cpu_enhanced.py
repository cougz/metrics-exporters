"""Enhanced CPU sensors collector for CPU temperature monitoring"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class SensorsCPUCollector(EnvironmentAwareCollector):
    """Environment-aware CPU sensors collector for temperature monitoring"""
    
    def __init__(self, config=None):
        super().__init__(config, "sensors_cpu", "CPU temperature sensors with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect CPU sensor metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect CPU sensor data
            result = self.collect_with_strategy("sensors_cpu")
            
            if not result.is_success:
                logger.warning(f"CPU sensors collection failed: {result.errors}")
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
            
            logger.debug(f"Collected {len(metrics)} CPU sensor metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"CPU sensors collection failed: {e}")
            return []