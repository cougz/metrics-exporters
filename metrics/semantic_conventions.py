"""OpenTelemetry semantic conventions for metric naming and labeling"""
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass


class MetricUnit(Enum):
    """Standard OpenTelemetry metric units"""
    BYTES = "By"
    BYTES_PER_SECOND = "By/s"
    PERCENT = "1"
    SECONDS = "s"
    HERTZ = "Hz"
    OPERATIONS = "{operation}"
    COUNT = "1"
    RATIO = "1"


@dataclass
class OTelMetricMapping:
    """Mapping from Prometheus-style metric to OpenTelemetry semantic convention"""
    otel_name: str
    unit: MetricUnit
    description: str
    consolidate_with_labels: Optional[Dict[str, str]] = None


class SemanticConventions:
    """OpenTelemetry semantic conventions for system metrics"""
    
    # CPU Metrics
    CPU_MAPPINGS = {
        "node_cpu_count": OTelMetricMapping(
            "system.cpu.logical.count",
            MetricUnit.COUNT,
            "Number of logical CPUs"
        ),
        "node_cpu_usage_percent": OTelMetricMapping(
            "system.cpu.utilization",
            MetricUnit.RATIO,
            "CPU utilization as a fraction"
        ),
        "node_cpu_user_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "user"}
        ),
        "node_cpu_system_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "system"}
        ),
        "node_cpu_idle_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "idle"}
        ),
        "node_cpu_iowait_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "iowait"}
        ),
        "node_cpu_frequency_hertz": OTelMetricMapping(
            "system.cpu.frequency",
            MetricUnit.HERTZ,
            "Current CPU frequency"
        ),
        "node_cpu_frequency_max_hertz": OTelMetricMapping(
            "system.cpu.frequency",
            MetricUnit.HERTZ,
            "Maximum CPU frequency",
            {"type": "max"}
        ),
        "node_cpu_frequency_min_hertz": OTelMetricMapping(
            "system.cpu.frequency",
            MetricUnit.HERTZ,
            "Minimum CPU frequency",
            {"type": "min"}
        ),
        "node_load1": OTelMetricMapping(
            "system.cpu.load_average.1m",
            MetricUnit.RATIO,
            "1-minute load average"
        ),
        "node_load5": OTelMetricMapping(
            "system.cpu.load_average.5m",
            MetricUnit.RATIO,
            "5-minute load average"
        ),
        "node_load15": OTelMetricMapping(
            "system.cpu.load_average.15m",
            MetricUnit.RATIO,
            "15-minute load average"
        ),
        "node_cpu_guest_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "guest"}
        ),
        "node_cpu_irq_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "irq"}
        ),
        "node_cpu_softirq_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "softirq"}
        ),
        "node_cpu_steal_percent": OTelMetricMapping(
            "system.cpu.time.ratio",
            MetricUnit.RATIO,
            "CPU time usage by state as ratio",
            {"state": "steal"}
        ),
        "node_cpu_seconds_total": OTelMetricMapping(
            "system.cpu.time",
            MetricUnit.SECONDS,
            "Total CPU time spent",
            {"state": "total"}
        ),
        "node_cpu_user_seconds_total": OTelMetricMapping(
            "system.cpu.time",
            MetricUnit.SECONDS,
            "Total CPU time spent",
            {"state": "user"}
        ),
        "node_cpu_system_seconds_total": OTelMetricMapping(
            "system.cpu.time",
            MetricUnit.SECONDS,
            "Total CPU time spent",
            {"state": "system"}
        ),
    }
    
    # Memory Metrics
    MEMORY_MAPPINGS = {
        "node_memory_total_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "total"}
        ),
        "node_memory_free_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "free"}
        ),
        "node_memory_available_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "available"}
        ),
        "node_memory_usage_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "used"}
        ),
        "node_memory_cached_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "cached"}
        ),
        "node_memory_buffered_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "buffered"}
        ),
        "node_memory_utilization": OTelMetricMapping(
            "system.memory.utilization",
            MetricUnit.RATIO,
            "Memory utilization as a fraction"
        ),
        "node_memory_buffers_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "buffers"}
        ),
        "node_memory_dirty_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "dirty"}
        ),
        "node_memory_writeback_bytes": OTelMetricMapping(
            "system.memory.usage",
            MetricUnit.BYTES,
            "Memory usage by state",
            {"state": "writeback"}
        ),
        "node_memory_swap_total_bytes": OTelMetricMapping(
            "system.memory.swap",
            MetricUnit.BYTES,
            "Swap memory by state",
            {"state": "total"}
        ),
        "node_memory_swap_used_bytes": OTelMetricMapping(
            "system.memory.swap",
            MetricUnit.BYTES,
            "Swap memory by state",
            {"state": "used"}
        ),
        "node_memory_swap_free_bytes": OTelMetricMapping(
            "system.memory.swap",
            MetricUnit.BYTES,
            "Swap memory by state",
            {"state": "free"}
        ),
    }
    
    # Disk Metrics
    DISK_MAPPINGS = {
        "node_disk_read_bytes_total": OTelMetricMapping(
            "system.disk.io",
            MetricUnit.BYTES,
            "Disk I/O bytes",
            {"direction": "read"}
        ),
        "node_disk_written_bytes_total": OTelMetricMapping(
            "system.disk.io",
            MetricUnit.BYTES,
            "Disk I/O bytes",
            {"direction": "write"}
        ),
        "node_disk_read_bytes_per_sec": OTelMetricMapping(
            "system.disk.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Disk I/O rate",
            {"direction": "read"}
        ),
        "node_disk_written_bytes_per_sec": OTelMetricMapping(
            "system.disk.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Disk I/O rate",
            {"direction": "write"}
        ),
        "node_disk_reads_completed_total": OTelMetricMapping(
            "system.disk.operations",
            MetricUnit.OPERATIONS,
            "Disk operations",
            {"direction": "read"}
        ),
        "node_disk_writes_completed_total": OTelMetricMapping(
            "system.disk.operations",
            MetricUnit.OPERATIONS,
            "Disk operations",
            {"direction": "write"}
        ),
        "node_disk_io_time_seconds_total": OTelMetricMapping(
            "system.disk.time",
            MetricUnit.SECONDS,
            "Total time spent doing I/O",
            {"type": "io"}
        ),
        "node_disk_read_time_seconds_total": OTelMetricMapping(
            "system.disk.time",
            MetricUnit.SECONDS,
            "Total time spent",
            {"direction": "read"}
        ),
        "node_disk_write_time_seconds_total": OTelMetricMapping(
            "system.disk.time",
            MetricUnit.SECONDS,
            "Total time spent",
            {"direction": "write"}
        ),
    }
    
    # Filesystem Metrics
    FILESYSTEM_MAPPINGS = {
        "node_filesystem_size_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "total"}
        ),
        "node_filesystem_usage_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "used"}
        ),
        "node_filesystem_free_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "free"}
        ),
        "node_filesystem_available_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "available"}
        ),
        "node_filesystem_utilization": OTelMetricMapping(
            "system.filesystem.utilization",
            MetricUnit.RATIO,
            "Filesystem utilization as a fraction"
        ),
        "node_filesystem_avail_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "available"}
        ),
    }
    
    # Network Metrics
    NETWORK_MAPPINGS = {
        "node_network_receive_bytes_total": OTelMetricMapping(
            "system.network.io",
            MetricUnit.BYTES,
            "Network I/O bytes",
            {"direction": "receive"}
        ),
        "node_network_transmit_bytes_total": OTelMetricMapping(
            "system.network.io",
            MetricUnit.BYTES,
            "Network I/O bytes",
            {"direction": "transmit"}
        ),
        "node_network_receive_bytes_per_sec": OTelMetricMapping(
            "system.network.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Network I/O rate",
            {"direction": "receive"}
        ),
        "node_network_transmit_bytes_per_sec": OTelMetricMapping(
            "system.network.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Network I/O rate",
            {"direction": "transmit"}
        ),
        "node_network_receive_packets_total": OTelMetricMapping(
            "system.network.packets",
            MetricUnit.COUNT,
            "Network packets",
            {"direction": "receive"}
        ),
        "node_network_transmit_packets_total": OTelMetricMapping(
            "system.network.packets",
            MetricUnit.COUNT,
            "Network packets",
            {"direction": "transmit"}
        ),
        "node_network_receive_errors_total": OTelMetricMapping(
            "system.network.errors",
            MetricUnit.COUNT,
            "Network errors",
            {"direction": "receive"}
        ),
        "node_network_transmit_errors_total": OTelMetricMapping(
            "system.network.errors",
            MetricUnit.COUNT,
            "Network errors",
            {"direction": "transmit"}
        ),
        "node_network_receive_errs_total": OTelMetricMapping(
            "system.network.errors",
            MetricUnit.COUNT,
            "Network errors",
            {"direction": "receive"}
        ),
        "node_network_transmit_errs_total": OTelMetricMapping(
            "system.network.errors",
            MetricUnit.COUNT,
            "Network errors",
            {"direction": "transmit"}
        ),
        "node_network_receive_bytes_per_sec": OTelMetricMapping(
            "system.network.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Network I/O rate",
            {"direction": "receive"}
        ),
        "node_network_transmit_bytes_per_sec": OTelMetricMapping(
            "system.network.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Network I/O rate",
            {"direction": "transmit"}
        ),
        "node_network_receive_packets_per_sec": OTelMetricMapping(
            "system.network.packets.rate",
            MetricUnit.COUNT,
            "Network packet rate",
            {"direction": "receive"}
        ),
        "node_network_transmit_packets_per_sec": OTelMetricMapping(
            "system.network.packets.rate",
            MetricUnit.COUNT,
            "Network packet rate",
            {"direction": "transmit"}
        ),
        "node_network_receive_drop_total": OTelMetricMapping(
            "system.network.dropped",
            MetricUnit.COUNT,
            "Network dropped packets",
            {"direction": "receive"}
        ),
        "node_network_transmit_drop_total": OTelMetricMapping(
            "system.network.dropped",
            MetricUnit.COUNT,
            "Network dropped packets",
            {"direction": "transmit"}
        ),
        "node_network_receive_drop_per_sec": OTelMetricMapping(
            "system.network.dropped.rate",
            MetricUnit.COUNT,
            "Network dropped packet rate",
            {"direction": "receive"}
        ),
        "node_network_transmit_drop_per_sec": OTelMetricMapping(
            "system.network.dropped.rate",
            MetricUnit.COUNT,
            "Network dropped packet rate",
            {"direction": "transmit"}
        ),
        "node_network_receive_errs_per_sec": OTelMetricMapping(
            "system.network.errors.rate",
            MetricUnit.COUNT,
            "Network error rate",
            {"direction": "receive"}
        ),
        "node_network_transmit_errs_per_sec": OTelMetricMapping(
            "system.network.errors.rate",
            MetricUnit.COUNT,
            "Network error rate",
            {"direction": "transmit"}
        ),
        "node_network_up": OTelMetricMapping(
            "system.network.state",
            MetricUnit.COUNT,
            "Network interface operational state"
        ),
        "node_network_info": OTelMetricMapping(
            "system.network.info",
            MetricUnit.COUNT,
            "Network interface information"
        ),
        "node_network_speed_bytes": OTelMetricMapping(
            "system.network.bandwidth",
            MetricUnit.BYTES_PER_SECOND,
            "Network interface speed"
        ),
    }
    
    # Process Metrics
    PROCESS_MAPPINGS = {
        "node_processes_total": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes",
            {"state": "total"}
        ),
        "node_processes_running": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes by state",
            {"state": "running"}
        ),
        "node_processes_sleeping": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes by state",
            {"state": "sleeping"}
        ),
        "node_processes_zombie": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes by state",
            {"state": "zombie"}
        ),
        "node_procs_running": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes by state",
            {"state": "running"}
        ),
        "node_procs_blocked": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Number of processes by state",
            {"state": "blocked"}
        ),
        "node_procs_total": OTelMetricMapping(
            "system.process.count",
            MetricUnit.COUNT,
            "Total number of processes",
            {"state": "total"}
        ),
        "node_forks_total": OTelMetricMapping(
            "system.process.created",
            MetricUnit.COUNT,
            "Total number of processes created"
        ),
    }
    
    # ZFS Metrics (mapped to filesystem for consistency)
    ZFS_MAPPINGS = {
        "node_zfs_pool_size_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "total", "fstype": "zfs"}
        ),
        "node_zfs_pool_allocated_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "used", "fstype": "zfs"}
        ),
        "node_zfs_pool_free_bytes": OTelMetricMapping(
            "system.filesystem.usage",
            MetricUnit.BYTES,
            "Filesystem usage by state",
            {"state": "free", "fstype": "zfs"}
        ),
        "node_zfs_pool_capacity_percent": OTelMetricMapping(
            "system.filesystem.utilization",
            MetricUnit.RATIO,
            "Filesystem utilization as a fraction",
            {"fstype": "zfs"}
        ),
        "node_zfs_pool_fragmentation_percent": OTelMetricMapping(
            "system.filesystem.fragmentation",
            MetricUnit.RATIO,
            "Filesystem fragmentation as a fraction",
            {"fstype": "zfs"}
        ),
        "node_zfs_pool_read_bytes_per_sec": OTelMetricMapping(
            "system.filesystem.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Filesystem I/O rate",
            {"direction": "read", "fstype": "zfs", "type": "bytes"}
        ),
        "node_zfs_pool_write_bytes_per_sec": OTelMetricMapping(
            "system.filesystem.io.rate",
            MetricUnit.BYTES_PER_SECOND,
            "Filesystem I/O rate",
            {"direction": "write", "fstype": "zfs", "type": "bytes"}
        ),
        "node_zfs_pool_read_ops_per_sec": OTelMetricMapping(
            "system.filesystem.io.rate",
            MetricUnit.COUNT,
            "Filesystem I/O operations rate",
            {"direction": "read", "fstype": "zfs", "type": "operations"}
        ),
        "node_zfs_pool_write_ops_per_sec": OTelMetricMapping(
            "system.filesystem.io.rate",
            MetricUnit.COUNT,
            "Filesystem I/O operations rate",
            {"direction": "write", "fstype": "zfs", "type": "operations"}
        ),
        "node_zfs_pool_readonly": OTelMetricMapping(
            "system.filesystem.readonly",
            MetricUnit.COUNT,
            "Filesystem readonly status",
            {"fstype": "zfs"}
        ),
    }
    
    # Temperature Metrics
    TEMPERATURE_MAPPINGS = {
        "node_thermal_zone_temperature_celsius": OTelMetricMapping(
            "system.thermal.temperature",
            MetricUnit.RATIO,
            "System temperature"
        ),
        "node_cpu_core_temperature_celsius": OTelMetricMapping(
            "system.cpu.temperature",
            MetricUnit.RATIO,
            "CPU core temperature"
        ),
        "node_nvme_temperature_celsius": OTelMetricMapping(
            "system.disk.temperature",
            MetricUnit.RATIO,
            "NVMe disk temperature"
        ),
    }
    
    @classmethod
    def get_all_mappings(cls) -> Dict[str, OTelMetricMapping]:
        """Get all metric mappings combined"""
        all_mappings = {}
        all_mappings.update(cls.CPU_MAPPINGS)
        all_mappings.update(cls.MEMORY_MAPPINGS)
        all_mappings.update(cls.DISK_MAPPINGS)
        all_mappings.update(cls.FILESYSTEM_MAPPINGS)
        all_mappings.update(cls.NETWORK_MAPPINGS)
        all_mappings.update(cls.PROCESS_MAPPINGS)
        all_mappings.update(cls.ZFS_MAPPINGS)
        all_mappings.update(cls.TEMPERATURE_MAPPINGS)
        return all_mappings
    
    @classmethod
    def get_otel_metric_name(cls, prometheus_name: str) -> str:
        """Get OpenTelemetry metric name for a Prometheus metric"""
        mapping = cls.get_all_mappings().get(prometheus_name)
        return mapping.otel_name if mapping else prometheus_name
    
    @classmethod
    def get_otel_unit(cls, prometheus_name: str) -> str:
        """Get OpenTelemetry unit for a Prometheus metric"""
        mapping = cls.get_all_mappings().get(prometheus_name)
        return mapping.unit.value if mapping else "1"
    
    @classmethod
    def get_otel_description(cls, prometheus_name: str) -> str:
        """Get OpenTelemetry description for a Prometheus metric"""
        mapping = cls.get_all_mappings().get(prometheus_name)
        return mapping.description if mapping else ""
    
    @classmethod
    def get_consolidation_labels(cls, prometheus_name: str) -> Dict[str, str]:
        """Get additional labels for metric consolidation"""
        mapping = cls.get_all_mappings().get(prometheus_name)
        return mapping.consolidate_with_labels if mapping and mapping.consolidate_with_labels else {}
    
    @classmethod
    def should_consolidate_metric(cls, prometheus_name: str) -> bool:
        """Check if metric should be consolidated with others using labels"""
        mapping = cls.get_all_mappings().get(prometheus_name)
        return mapping and mapping.consolidate_with_labels is not None
    
    @classmethod
    def get_resource_attributes(cls) -> List[str]:
        """Get list of attributes that should be moved to resource level"""
        return [
            "hostname",
            "host_name", 
            "instance",
            "service_name",
            "service_version",
            "container_id",
            "container_name"
        ]
    
    @classmethod
    def is_resource_attribute(cls, label_key: str) -> bool:
        """Check if a label should be moved to resource attributes"""
        return label_key in cls.get_resource_attributes()
    
    @classmethod
    def convert_percentage_to_ratio(cls, value: float, metric_name: str) -> float:
        """Convert percentage values to ratios (0-1) for OpenTelemetry"""
        if any(keyword in metric_name.lower() for keyword in ['percent', 'utilization']):
            return value / 100.0
        return value