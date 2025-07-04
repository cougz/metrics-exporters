"""Always-on OpenTelemetry transformer"""
from typing import List, Dict
from collections import defaultdict
from .models import MetricValue, MetricType
from logging_config import get_logger

logger = get_logger(__name__)

# OpenTelemetry semantic convention mappings with standardized units
SEMANTIC_MAPPINGS = {
    # Memory mappings (bytes)
    "node_memory_total_bytes": ("system.memory.usage", {"state": "total"}),
    "node_memory_free_bytes": ("system.memory.usage", {"state": "free"}),
    "node_memory_usage_bytes": ("system.memory.usage", {"state": "used"}),
    "node_memory_available_bytes": ("system.memory.usage", {"state": "available"}),
    
    # CPU mappings  
    "node_cpu_count": ("system.cpu.logical.count", {}),
    "node_cpu_usage_percent": ("system.cpu.utilization", {}),
    "node_load1": ("system.cpu.load_average.1m", {}),
    "node_load5": ("system.cpu.load_average.5m", {}),
    "node_load15": ("system.cpu.load_average.15m", {}),
    
    # Filesystem mappings (bytes)
    "node_filesystem_size_bytes": ("system.filesystem.usage", {"state": "total"}),
    "node_filesystem_usage_bytes": ("system.filesystem.usage", {"state": "used"}),
    "node_filesystem_avail_bytes": ("system.filesystem.usage", {"state": "available"}),
    
    # Network mappings (bytes for io, count for packets)
    "node_network_receive_bytes_total": ("system.network.io", {"direction": "receive"}),
    "node_network_transmit_bytes_total": ("system.network.io", {"direction": "transmit"}),
    "node_network_receive_packets_total": ("system.network.packets", {"direction": "receive"}),
    "node_network_transmit_packets_total": ("system.network.packets", {"direction": "transmit"}),
    
    # Process mappings (count)
    "node_processes_total": ("system.process.count", {"state": "total"}),
    "node_procs_running": ("system.process.count", {"state": "running"}),
    "node_procs_blocked": ("system.process.count", {"state": "blocked"}),
}

class MetricTransformer:
    """Always transforms metrics to OpenTelemetry format"""
    
    def __init__(self, config):
        self.config = config
    
    def transform_all(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Transform all metrics to OpenTelemetry semantic conventions"""
        logger.debug(f"Transforming {len(metrics)} metrics to OpenTelemetry format")
        
        # Step 1: Convert naming and add semantic labels
        transformed = self._convert_to_semantic_names(metrics)
        
        # Step 2: Convert percentages to ratios
        normalized = self._normalize_values(transformed)
        
        # Step 3: Consolidate metrics with same names
        consolidated = self._consolidate_metrics(normalized)
        
        # Step 4: Add calculated utilization metrics
        enhanced = self._add_utilization_metrics(consolidated)
        
        logger.debug(f"Transformed to {len(enhanced)} OpenTelemetry metrics")
        return enhanced
    
    def _convert_to_semantic_names(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Convert metric names to OpenTelemetry semantic conventions"""
        transformed = []
        
        for metric in metrics:
            if metric.name in SEMANTIC_MAPPINGS:
                # Use explicit mapping
                new_name, additional_labels = SEMANTIC_MAPPINGS[metric.name]
                new_labels = self._standardize_labels(metric.labels.copy())
                new_labels.update(additional_labels)
                
                transformed_metric = MetricValue(
                    name=new_name,
                    value=metric.value,
                    labels=new_labels,
                    help_text=metric.help_text,
                    metric_type=metric.metric_type,
                    unit=self._get_semantic_unit(metric.name),
                    timestamp=metric.timestamp
                )
                transformed.append(transformed_metric)
                
            elif metric.name.startswith("node_"):
                # Fallback: convert node_ to system.
                new_name = metric.name.replace("node_", "system.")
                transformed_metric = MetricValue(
                    name=new_name,
                    value=metric.value,
                    labels=self._standardize_labels(metric.labels.copy()),
                    help_text=metric.help_text,
                    metric_type=metric.metric_type,
                    unit=self._get_semantic_unit(metric.name, metric.unit),
                    timestamp=metric.timestamp
                )
                transformed.append(transformed_metric)
            else:
                # Keep as-is if already semantic, but standardize labels
                transformed_metric = MetricValue(
                    name=metric.name,
                    value=metric.value,
                    labels=self._standardize_labels(metric.labels.copy()),
                    help_text=metric.help_text,
                    metric_type=metric.metric_type,
                    unit=self._get_semantic_unit(metric.name, metric.unit),
                    timestamp=metric.timestamp
                )
                transformed.append(transformed_metric)
        
        return transformed
    
    def _standardize_labels(self, labels: Dict[str, str]) -> Dict[str, str]:
        """Standardize label names to OpenTelemetry semantic conventions"""
        standardized = {}
        
        for key, value in labels.items():
            # Standardize label names
            if key == "host_name":
                standardized["host.name"] = value
            elif key == "device":
                # Context-aware device labeling
                if self._is_network_device(value):
                    standardized["network.interface.name"] = value
                    # Add interface type detection
                    if value == "lo":
                        standardized["network.interface.type"] = "loopback"
                    elif value.startswith(("eth", "eno", "ens")):
                        standardized["network.interface.type"] = "ethernet"
                    elif value.startswith(("wlan", "wifi")):
                        standardized["network.interface.type"] = "wireless"
                    elif value.startswith("docker"):
                        standardized["network.interface.type"] = "bridge"
                    else:
                        standardized["network.interface.type"] = "other"
                elif self._is_disk_device(value):
                    standardized["disk.device"] = value
                    # Add disk type detection
                    if "nvme" in value.lower():
                        standardized["disk.type"] = "ssd"
                    elif value.lower().startswith(("sd", "hd")):
                        standardized["disk.type"] = "unknown"  # Could be SSD or HDD
                    else:
                        standardized["disk.type"] = "other"
                else:
                    # Generic device
                    standardized["device"] = value
            elif key == "instance":
                # Check if instance is redundant with host.name
                host_name = labels.get("host_name") or standardized.get("host.name")
                if not (host_name and host_name == value):
                    # Keep instance if it's different from host name
                    standardized["service.instance.id"] = value
            else:
                # Keep other labels as-is
                standardized[key] = value
        
        return standardized
    
    def _is_network_device(self, device_name: str) -> bool:
        """Check if device name represents a network interface"""
        network_prefixes = ["eth", "eno", "ens", "enp", "wlan", "wifi", "lo", "docker", "br", "virbr", "veth", "tun", "tap"]
        return any(device_name.startswith(prefix) for prefix in network_prefixes)
    
    def _is_disk_device(self, device_name: str) -> bool:
        """Check if device name represents a disk device"""
        disk_prefixes = ["sd", "hd", "nvme", "vd", "xvd", "mmcblk"]
        return any(device_name.startswith(prefix) for prefix in disk_prefixes)
    
    def _get_semantic_unit(self, original_name: str, existing_unit: str = None) -> str:
        """Get appropriate OpenTelemetry unit with standardized names"""
        # If we already have a good unit, prefer it
        if existing_unit and existing_unit not in ["By", "%"]:
            return existing_unit
            
        if "bytes" in original_name:
            return "bytes"
        elif "percent" in original_name or existing_unit == "%":
            return "percent"
        elif "seconds" in original_name:
            return "s"
        elif "hertz" in original_name:
            return "Hz"
        elif existing_unit == "By":
            return "bytes"
        elif existing_unit:
            return existing_unit
        else:
            return "1"
    
    def _normalize_values(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Convert percentages to ratios for OpenTelemetry"""
        normalized = []
        
        for metric in metrics:
            new_metric = metric
            
            # Convert percentages to ratios (0-100 → 0-1)
            if (metric.name.endswith(".utilization") or 
                "percent" in metric.name.lower() or
                metric.unit in ["%", "percent"]):
                
                new_value = metric.value / 100.0 if metric.value <= 100 else metric.value
                new_metric = MetricValue(
                    name=metric.name,
                    value=new_value,
                    labels=metric.labels,
                    help_text=metric.help_text,
                    metric_type=metric.metric_type,
                    unit="1",  # Ratios are unitless
                    timestamp=metric.timestamp
                )
            
            normalized.append(new_metric)
        
        return normalized
    
    def _consolidate_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Remove duplicate metrics with same name+labels"""
        metric_map = {}
        
        for metric in metrics:
            # Create unique key from name and labels
            label_key = tuple(sorted(metric.labels.items()))
            key = (metric.name, label_key)
            
            if key in metric_map:
                # Keep the metric with higher value (prefer non-zero)
                existing = metric_map[key]
                if metric.value > existing.value or (existing.value == 0 and metric.value > 0):
                    metric_map[key] = metric
            else:
                metric_map[key] = metric
        
        return list(metric_map.values())
    
    def _add_utilization_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Add calculated utilization metrics"""
        enhanced = metrics.copy()
        
        # Group metrics by name for calculations
        grouped = defaultdict(list)
        for metric in metrics:
            grouped[metric.name].append(metric)
        
        # Calculate memory utilization
        if "system.memory.usage" in grouped:
            utilization = self._calculate_memory_utilization(grouped["system.memory.usage"])
            if utilization:
                enhanced.append(utilization)
        
        # Calculate filesystem utilizations
        if "system.filesystem.usage" in grouped:
            fs_utilizations = self._calculate_filesystem_utilizations(grouped["system.filesystem.usage"])
            enhanced.extend(fs_utilizations)
        
        return enhanced
    
    def _calculate_memory_utilization(self, memory_metrics: List[MetricValue]) -> MetricValue:
        """Calculate memory utilization from usage metrics"""
        used_value = None
        total_value = None
        base_labels = {}
        
        for metric in memory_metrics:
            state = metric.labels.get("state")
            if state == "used":
                used_value = metric.value
                base_labels = {k: v for k, v in metric.labels.items() if k != "state"}
            elif state == "total":
                total_value = metric.value
        
        if used_value is not None and total_value is not None and total_value > 0:
            utilization = used_value / total_value
            return MetricValue(
                name="system.memory.utilization",
                value=utilization,
                labels=base_labels,
                help_text="Memory utilization as a fraction",
                metric_type=MetricType.GAUGE,
                unit="1"
            )
        
        return None
    
    def _calculate_filesystem_utilizations(self, fs_metrics: List[MetricValue]) -> List[MetricValue]:
        """Calculate filesystem utilizations"""
        # Group by mountpoint/device
        fs_groups = defaultdict(dict)
        
        for metric in fs_metrics:
            key = (metric.labels.get("mountpoint", ""), metric.labels.get("device", ""))
            state = metric.labels.get("state")
            if state in ["used", "total"]:
                fs_groups[key][state] = metric
        
        utilizations = []
        for (mountpoint, device), states in fs_groups.items():
            if "used" in states and "total" in states:
                used = states["used"].value
                total = states["total"].value
                
                if total > 0:
                    utilization = used / total
                    base_labels = {k: v for k, v in states["used"].labels.items() if k != "state"}
                    
                    utilizations.append(MetricValue(
                        name="system.filesystem.utilization",
                        value=utilization,
                        labels=base_labels,
                        help_text="Filesystem utilization as a fraction",
                        metric_type=MetricType.GAUGE,
                        unit="1"
                    ))
        
        return utilizations