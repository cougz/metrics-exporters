"""Enhanced unified sensors collector using sensors command"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class SensorsCollector(EnvironmentAwareCollector):
    """Environment-aware unified sensors collector for all temperature sensors"""
    
    def __init__(self, config=None):
        super().__init__(config, "sensors", "Temperature sensors using sensors command")
    
    def collect(self) -> List[MetricValue]:
        """Collect sensor metrics using environment-appropriate strategy"""
        try:
            logger.debug("Starting unified sensor collection")
            # Use strategy to collect sensor data
            result = self.collect_with_strategy("sensors")
            
            if not result.is_success:
                logger.warning(f"Sensors collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process all temperature sensors from the sensors command
            if "sensors" in data:
                for sensor_info in data["sensors"]:
                    if isinstance(sensor_info, dict):
                        self._process_sensor(sensor_info, metrics, labels)
            
            logger.debug(f"Collected {len(metrics)} sensor metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Sensors collection failed: {e}")
            return []
    
    def _process_sensor(self, sensor_info: dict, metrics: List[MetricValue], base_labels: dict):
        """Process a single sensor and create appropriate metrics"""
        sensor_type = sensor_info.get("sensor_type", "unknown")
        
        if sensor_type == "cpu":
            self._process_cpu_sensor(sensor_info, metrics, base_labels)
        elif sensor_type == "nvme":
            self._process_nvme_sensor(sensor_info, metrics, base_labels)
        # Can add more sensor types here in the future
    
    def _process_cpu_sensor(self, sensor_info: dict, metrics: List[MetricValue], base_labels: dict):
        """Process CPU temperature sensor"""
        sensor_labels = base_labels.copy()
        sensor_labels.update({
            "sensor.chip": sensor_info.get("chip", "unknown"),
            "sensor.type": "cpu",
            "sensor.component": sensor_info.get("feature", "unknown")
        })
        
        # Extract CPU-specific labels
        feature = sensor_info.get("feature", "")
        if "Package" in feature:
            sensor_labels["cpu.core"] = "package"
            # Extract package ID from feature name
            import re
            match = re.search(r'Package id (\d+)', feature)
            if match:
                sensor_labels["cpu.package"] = match.group(1)
        elif "Core" in feature:
            # Extract core number
            import re
            match = re.search(r'Core (\d+)', feature)
            if match:
                sensor_labels["cpu.core"] = match.group(1)
            sensor_labels["cpu.package"] = "0"  # Assuming package 0 for now
        
        # Current temperature
        if "temp_celsius" in sensor_info:
            metrics.append(MetricValue(
                name="system.cpu.temperature",
                value=float(sensor_info["temp_celsius"]),
                labels=sensor_labels.copy(),
                help_text="CPU temperature in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        # Temperature thresholds
        if "temp_max_celsius" in sensor_info:
            threshold_labels = sensor_labels.copy()
            threshold_labels["threshold.type"] = "max"
            metrics.append(MetricValue(
                name="system.cpu.temperature.threshold",
                value=float(sensor_info["temp_max_celsius"]),
                labels=threshold_labels,
                help_text="CPU temperature threshold in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        if "temp_crit_celsius" in sensor_info:
            threshold_labels = sensor_labels.copy()
            threshold_labels["threshold.type"] = "critical"
            metrics.append(MetricValue(
                name="system.cpu.temperature.threshold",
                value=float(sensor_info["temp_crit_celsius"]),
                labels=threshold_labels,
                help_text="CPU temperature threshold in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        # Alarm state
        if "alarm" in sensor_info:
            metrics.append(MetricValue(
                name="system.cpu.temperature.alarm",
                value=float(sensor_info["alarm"]),
                labels=sensor_labels.copy(),
                help_text="CPU temperature alarm state",
                metric_type=MetricType.GAUGE
            ))
    
    def _process_nvme_sensor(self, sensor_info: dict, metrics: List[MetricValue], base_labels: dict):
        """Process NVMe temperature sensor"""
        sensor_labels = base_labels.copy()
        sensor_labels.update({
            "sensor.chip": sensor_info.get("chip", "unknown"),
            "sensor.type": "nvme",
            "nvme.device": sensor_info.get("chip", "unknown")
        })
        
        # Determine sensor type from feature name
        feature = sensor_info.get("feature", "")
        if "Composite" in feature:
            sensor_labels["nvme.sensor"] = "composite"
        elif "Sensor 1" in feature:
            sensor_labels["nvme.sensor"] = "sensor_1"
        elif "Sensor 2" in feature:
            sensor_labels["nvme.sensor"] = "sensor_2"
        else:
            sensor_labels["nvme.sensor"] = feature.lower().replace(" ", "_")
        
        # Current temperature
        if "temp_celsius" in sensor_info:
            metrics.append(MetricValue(
                name="system.nvme.temperature",
                value=float(sensor_info["temp_celsius"]),
                labels=sensor_labels.copy(),
                help_text="NVMe temperature in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        # Temperature thresholds (only for reasonable values)
        if "temp_max_celsius" in sensor_info and sensor_info["temp_max_celsius"] < 1000:
            threshold_labels = sensor_labels.copy()
            threshold_labels["threshold.type"] = "max"
            metrics.append(MetricValue(
                name="system.nvme.temperature.threshold",
                value=float(sensor_info["temp_max_celsius"]),
                labels=threshold_labels,
                help_text="NVMe temperature threshold in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        if "temp_crit_celsius" in sensor_info:
            threshold_labels = sensor_labels.copy()
            threshold_labels["threshold.type"] = "critical"
            metrics.append(MetricValue(
                name="system.nvme.temperature.threshold",
                value=float(sensor_info["temp_crit_celsius"]),
                labels=threshold_labels,
                help_text="NVMe temperature threshold in Celsius",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        # Alarm state
        if "alarm" in sensor_info:
            metrics.append(MetricValue(
                name="system.nvme.temperature.alarm",
                value=float(sensor_info["alarm"]),
                labels=sensor_labels.copy(),
                help_text="NVMe temperature alarm state",
                metric_type=MetricType.GAUGE
            ))