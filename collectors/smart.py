"""Enhanced SMART data collector for detailed disk health monitoring"""
import logging
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class SmartCollector(BaseCollector):
    """Environment-aware SMART data collector for comprehensive disk monitoring"""
    
    def __init__(self, config=None):
        super().__init__(config, "smart", "SMART disk health data collector (requires sudo)")
    
    def collect(self) -> List[MetricValue]:
        """Collect SMART metrics using environment-appropriate strategy"""
        try:
            logger.debug("Starting SMART data collection")
            # Use strategy to collect SMART data
            result = self.collect_with_strategy("smart")
            
            if not result.is_success:
                logger.warning(f"SMART collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process SMART data for each disk
            if "disks" in data:
                for disk_info in data["disks"]:
                    if isinstance(disk_info, dict):
                        self._process_disk_smart(disk_info, metrics, labels)
            
            logger.debug(f"Collected {len(metrics)} SMART metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"SMART collection failed: {e}")
            return []
    
    def _process_disk_smart(self, disk_info: dict, metrics: List[MetricValue], base_labels: dict):
        """Process SMART data for a single disk"""
        disk_labels = base_labels.copy()
        disk_labels.update({
            "device": disk_info.get("device", "unknown"),
            "model": disk_info.get("model", "unknown"),
            "serial": disk_info.get("serial", "unknown"),
            "interface": disk_info.get("interface", "unknown")
        })
        
        # Overall SMART health status
        if "smart_passed" in disk_info:
            metrics.append(MetricValue(
                name="disk.smart.health_status",
                value=1.0 if disk_info["smart_passed"] else 0.0,
                labels=disk_labels.copy(),
                help_text="SMART overall health status (1=passed, 0=failed)",
                metric_type=MetricType.GAUGE
            ))
        
        # Temperature (already collected by sensors, but include for completeness)
        if "temperature_celsius" in disk_info:
            metrics.append(MetricValue(
                name="disk.smart.temperature",
                value=float(disk_info["temperature_celsius"]),
                labels=disk_labels.copy(),
                help_text="Disk temperature in Celsius from SMART",
                metric_type=MetricType.GAUGE,
                unit="celsius"
            ))
        
        # Power-on hours
        if "power_on_hours" in disk_info:
            metrics.append(MetricValue(
                name="disk.smart.power_on_hours",
                value=float(disk_info["power_on_hours"]),
                labels=disk_labels.copy(),
                help_text="Total power-on hours",
                metric_type=MetricType.COUNTER,
                unit="hours"
            ))
        
        # Power cycle count
        if "power_cycles" in disk_info:
            metrics.append(MetricValue(
                name="disk.smart.power_cycles",
                value=float(disk_info["power_cycles"]),
                labels=disk_labels.copy(),
                help_text="Power cycle count",
                metric_type=MetricType.COUNTER
            ))
        
        # For SATA/SAS disks - process ATA SMART attributes
        if "ata_smart_attributes" in disk_info:
            for attr in disk_info["ata_smart_attributes"]:
                self._process_ata_attribute(attr, metrics, disk_labels)
        
        # For NVMe disks - process NVMe-specific metrics
        if disk_info.get("interface") == "nvme" and "nvme_smart_log" in disk_info:
            self._process_nvme_smart(disk_info["nvme_smart_log"], metrics, disk_labels)
    
    def _process_ata_attribute(self, attr: dict, metrics: List[MetricValue], disk_labels: dict):
        """Process individual ATA SMART attribute"""
        if not isinstance(attr, dict):
            return
        
        attr_labels = disk_labels.copy()
        attr_labels["attribute_id"] = str(attr.get("id", ""))
        attr_labels["attribute_name"] = attr.get("name", "unknown")
        
        # Raw value (most useful for monitoring)
        if "raw_value" in attr:
            metrics.append(MetricValue(
                name="disk.smart.attribute.raw_value",
                value=float(attr["raw_value"]),
                labels=attr_labels.copy(),
                help_text="SMART attribute raw value",
                metric_type=MetricType.GAUGE
            ))
        
        # Current normalized value
        if "value" in attr:
            metrics.append(MetricValue(
                name="disk.smart.attribute.current",
                value=float(attr["value"]),
                labels=attr_labels.copy(),
                help_text="SMART attribute current normalized value (0-255)",
                metric_type=MetricType.GAUGE
            ))
        
        # Worst value
        if "worst" in attr:
            metrics.append(MetricValue(
                name="disk.smart.attribute.worst",
                value=float(attr["worst"]),
                labels=attr_labels.copy(),
                help_text="SMART attribute worst normalized value",
                metric_type=MetricType.GAUGE
            ))
        
        # Threshold
        if "threshold" in attr:
            metrics.append(MetricValue(
                name="disk.smart.attribute.threshold",
                value=float(attr["threshold"]),
                labels=attr_labels.copy(),
                help_text="SMART attribute failure threshold",
                metric_type=MetricType.GAUGE
            ))
    
    def _process_nvme_smart(self, nvme_log: dict, metrics: List[MetricValue], disk_labels: dict):
        """Process NVMe-specific SMART health log"""
        # Critical warning flags
        if "critical_warning" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.critical_warning",
                value=float(nvme_log["critical_warning"]),
                labels=disk_labels.copy(),
                help_text="NVMe critical warning flags",
                metric_type=MetricType.GAUGE
            ))
        
        # Available spare percentage
        if "available_spare" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.available_spare_percent",
                value=float(nvme_log["available_spare"]),
                labels=disk_labels.copy(),
                help_text="NVMe available spare percentage",
                metric_type=MetricType.GAUGE,
                unit="percent"
            ))
        
        # Percentage used (wear indicator)
        if "percentage_used" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.percentage_used",
                value=float(nvme_log["percentage_used"]),
                labels=disk_labels.copy(),
                help_text="NVMe percentage of life used",
                metric_type=MetricType.GAUGE,
                unit="percent"
            ))
        
        # Data units read/written (convert to bytes)
        if "data_units_read" in nvme_log:
            # Each unit is 512KB
            bytes_read = nvme_log["data_units_read"] * 512 * 1024
            metrics.append(MetricValue(
                name="disk.nvme.data_read_bytes",
                value=float(bytes_read),
                labels=disk_labels.copy(),
                help_text="Total data read in bytes",
                metric_type=MetricType.COUNTER,
                unit="bytes"
            ))
        
        if "data_units_written" in nvme_log:
            # Each unit is 512KB
            bytes_written = nvme_log["data_units_written"] * 512 * 1024
            metrics.append(MetricValue(
                name="disk.nvme.data_written_bytes",
                value=float(bytes_written),
                labels=disk_labels.copy(),
                help_text="Total data written in bytes",
                metric_type=MetricType.COUNTER,
                unit="bytes"
            ))
        
        # Error counts
        if "media_errors" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.media_errors",
                value=float(nvme_log["media_errors"]),
                labels=disk_labels.copy(),
                help_text="NVMe media error count",
                metric_type=MetricType.COUNTER
            ))
        
        # Unsafe shutdowns
        if "unsafe_shutdowns" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.unsafe_shutdowns",
                value=float(nvme_log["unsafe_shutdowns"]),
                labels=disk_labels.copy(),
                help_text="NVMe unsafe shutdown count",
                metric_type=MetricType.COUNTER
            ))
        
        # Controller busy time
        if "controller_busy_time" in nvme_log:
            metrics.append(MetricValue(
                name="disk.nvme.controller_busy_minutes",
                value=float(nvme_log["controller_busy_time"]),
                labels=disk_labels.copy(),
                help_text="NVMe controller busy time in minutes",
                metric_type=MetricType.COUNTER,
                unit="minutes"
            ))