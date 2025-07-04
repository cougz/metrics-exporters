"""Enhanced disk metrics collector with environment-aware strategies"""
import logging
import os
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class DiskCollector(EnvironmentAwareCollector):
    """Environment-aware disk metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "disk", "Disk usage and ZFS pool metrics with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect disk metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect disk data
            result = self.collect_with_strategy("disk")
            
            if not result.is_success:
                logger.warning(f"Disk collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process filesystem information
            if "filesystems" in data:
                for filesystem in data["filesystems"]:
                    if isinstance(filesystem, dict):
                        device = filesystem.get("device", "unknown")
                        mountpoint = filesystem.get("mountpoint", "/")
                        fstype = filesystem.get("fstype", "unknown")
                        
                        fs_labels = labels.copy()
                        fs_labels.update({
                            "device": device,
                            "mountpoint": mountpoint,
                            "fstype": fstype
                        })
                        
                        # Get disk usage for this filesystem
                        try:
                            stat = os.statvfs(mountpoint)
                            total_bytes = stat.f_blocks * stat.f_frsize
                            free_bytes = stat.f_bavail * stat.f_frsize
                            used_bytes = total_bytes - free_bytes
                            
                            metrics.extend([
                                MetricValue(
                                    name="node_filesystem_size_bytes",
                                    value=float(total_bytes),
                                    labels=fs_labels.copy(),
                                    help_text="Filesystem size in bytes",
                                    metric_type=MetricType.GAUGE,
                                    unit="bytes"
                                ),
                                MetricValue(
                                    name="node_filesystem_usage_bytes",
                                    value=float(used_bytes),
                                    labels=fs_labels.copy(),
                                    help_text="Filesystem space used in bytes",
                                    metric_type=MetricType.GAUGE,
                                    unit="bytes"
                                ),
                                MetricValue(
                                    name="node_filesystem_avail_bytes",
                                    value=float(free_bytes),
                                    labels=fs_labels.copy(),
                                    help_text="Filesystem space available to non-root users in bytes",
                                    metric_type=MetricType.GAUGE,
                                    unit="bytes"
                                )
                            ])
                        except OSError as e:
                            logger.warning(f"Could not get disk usage for {mountpoint}: {e}")
            
            # Process disk I/O statistics (host environments)
            if "disk_stats" in data:
                for device_name, stats in data["disk_stats"].items():
                    if isinstance(stats, dict):
                        device_labels = labels.copy()
                        device_labels["device"] = device_name
                        
                        # Convert sector counts to bytes (usually 512 bytes per sector)
                        sector_size = 512
                        
                        io_metrics = [
                            ("reads_completed", "node_disk_reads_completed_total", "Total number of reads completed"),
                            ("writes_completed", "node_disk_writes_completed_total", "Total number of writes completed"),
                            ("read_time_ms", "node_disk_read_time_seconds_total", "Total time spent reading"),
                            ("write_time_ms", "node_disk_write_time_seconds_total", "Total time spent writing"),
                            ("io_time_ms", "node_disk_io_time_seconds_total", "Total time spent doing I/O"),
                        ]
                        
                        for stat_key, metric_name, help_text in io_metrics:
                            if stat_key in stats:
                                value = stats[stat_key]
                                # Convert milliseconds to seconds for time metrics
                                if "time_ms" in stat_key:
                                    value = value / 1000.0
                                
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=float(value),
                                    labels=device_labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.COUNTER,
                                    unit="seconds" if "time" in metric_name else None
                                ))
                        
                        # Byte metrics
                        if "sectors_read" in stats:
                            bytes_read = stats["sectors_read"] * sector_size
                            metrics.append(MetricValue(
                                name="node_disk_read_bytes_total",
                                value=float(bytes_read),
                                labels=device_labels.copy(),
                                help_text="Total bytes read from disk",
                                metric_type=MetricType.COUNTER,
                                unit="bytes"
                            ))
                        
                        if "sectors_written" in stats:
                            bytes_written = stats["sectors_written"] * sector_size
                            metrics.append(MetricValue(
                                name="node_disk_written_bytes_total",
                                value=float(bytes_written),
                                labels=device_labels.copy(),
                                help_text="Total bytes written to disk",
                                metric_type=MetricType.COUNTER,
                                unit="bytes"
                            ))
            
            # Process ZFS pool information (host environments)
            if "zfs_pools" in data:
                for pool in data["zfs_pools"]:
                    if isinstance(pool, dict):
                        pool_name = pool.get("name", "unknown")
                        pool_labels = labels.copy()
                        pool_labels.update({
                            "pool": pool_name,
                            "health": pool.get("health", "unknown")
                        })
                        
                        # ZFS pool size metrics
                        zfs_size_metrics = [
                            ("size_bytes", "node_zfs_pool_size_bytes", "ZFS pool total size in bytes"),
                            ("allocated_bytes", "node_zfs_pool_allocated_bytes", "ZFS pool allocated space in bytes"),
                            ("free_bytes", "node_zfs_pool_free_bytes", "ZFS pool free space in bytes"),
                        ]
                        
                        for pool_key, metric_name, help_text in zfs_size_metrics:
                            if pool_key in pool:
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=float(pool[pool_key]),
                                    labels=pool_labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.GAUGE,
                                    unit="bytes"
                                ))
                        
                        # ZFS pool capacity percentage
                        if "capacity_percent" in pool:
                            metrics.append(MetricValue(
                                name="node_zfs_pool_capacity_percent",
                                value=float(pool["capacity_percent"]),
                                labels=pool_labels.copy(),
                                help_text="ZFS pool capacity as percentage",
                                metric_type=MetricType.GAUGE,
                                unit="percent"
                            ))
                        
                        # ZFS pool fragmentation
                        if "fragmentation_percent" in pool:
                            metrics.append(MetricValue(
                                name="node_zfs_pool_fragmentation_percent",
                                value=float(pool["fragmentation_percent"]),
                                labels=pool_labels.copy(),
                                help_text="ZFS pool fragmentation percentage",
                                metric_type=MetricType.GAUGE,
                                unit="percent"
                            ))
                        
                        # ZFS pool readonly status
                        if "readonly" in pool:
                            metrics.append(MetricValue(
                                name="node_zfs_pool_readonly",
                                value=float(1 if pool["readonly"] else 0),
                                labels=pool_labels.copy(),
                                help_text="ZFS pool readonly status (1 = readonly, 0 = read-write)",
                                metric_type=MetricType.GAUGE
                            ))
                        
                        # ZFS pool I/O metrics
                        zfs_io_metrics = [
                            ("read_operations_per_sec", "node_zfs_pool_read_ops_per_sec", "ZFS pool read operations per second"),
                            ("write_operations_per_sec", "node_zfs_pool_write_ops_per_sec", "ZFS pool write operations per second"),
                            ("read_bandwidth_bytes_per_sec", "node_zfs_pool_read_bytes_per_sec", "ZFS pool read bandwidth in bytes per second"),
                            ("write_bandwidth_bytes_per_sec", "node_zfs_pool_write_bytes_per_sec", "ZFS pool write bandwidth in bytes per second"),
                        ]
                        
                        for pool_key, metric_name, help_text in zfs_io_metrics:
                            if pool_key in pool:
                                unit = "bytes" if "bytes" in pool_key else None
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=float(pool[pool_key]),
                                    labels=pool_labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.GAUGE,
                                    unit=unit
                                ))
            
            logger.debug(f"Collected {len(metrics)} disk metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Disk collection failed: {e}")
            return []