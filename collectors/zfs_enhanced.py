"""Enhanced ZFS collector for ZFS pool monitoring"""
import logging
from typing import List
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class ZFSCollector(EnvironmentAwareCollector):
    """Environment-aware ZFS pool collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "zfs", "ZFS pool monitoring with environment-aware collection")
    
    def collect(self) -> List[MetricValue]:
        """Collect ZFS metrics using environment-appropriate strategy"""
        try:
            # Use strategy to collect ZFS data
            result = self.collect_with_strategy("zfs")
            
            if not result.is_success:
                logger.warning(f"ZFS collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process ZFS pool information
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
            
            logger.debug(f"Collected {len(metrics)} ZFS metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"ZFS collection failed: {e}")
            return []