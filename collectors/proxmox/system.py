"""Proxmox system metrics collector"""
import logging
from typing import List
from ..base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class ProxmoxSystemCollector(EnvironmentAwareCollector):
    """Proxmox system-specific metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "proxmox_system", "Proxmox system and cluster metrics")
    
    def collect(self) -> List[MetricValue]:
        """Collect Proxmox system metrics"""
        try:
            runtime_env = self.get_runtime_environment()
            
            # Only run on Proxmox hosts
            if not runtime_env.supports_proxmox_features:
                logger.debug("Proxmox system collector skipped - not on Proxmox host")
                return []
            
            # Use host strategy to collect Proxmox system data
            strategy = self.get_collection_strategy()
            
            if hasattr(strategy, 'collect_proxmox_system'):
                result = strategy.collect_proxmox_system()
            else:
                logger.warning("Strategy does not support Proxmox system collection")
                return []
            
            if not result.is_success:
                logger.warning(f"Proxmox system collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Proxmox version info
            if "pve_version" in data:
                version_labels = labels.copy()
                version_lines = data["pve_version"].split('\n')
                for line in version_lines:
                    if 'pve-manager' in line:
                        version_labels["pve_manager_version"] = line.split()[1] if len(line.split()) > 1 else "unknown"
                        break
                
                metrics.append(MetricValue(
                    name="proxmox_version_info",
                    value=1.0,
                    labels=version_labels,
                    help_text="Proxmox VE version information",
                    metric_type=MetricType.GAUGE
                ))
            
            # Cluster status
            if "cluster_status" in data:
                cluster_active = 1.0 if "standalone" not in data["cluster_status"].lower() else 0.0
                metrics.append(MetricValue(
                    name="proxmox_cluster_active",
                    value=cluster_active,
                    labels=labels.copy(),
                    help_text="Whether node is part of active cluster",
                    metric_type=MetricType.GAUGE
                ))
            
            # Node status
            if "node_status" in data:
                metrics.append(MetricValue(
                    name="proxmox_node_up",
                    value=1.0,  # If we can collect, node is up
                    labels=labels.copy(),
                    help_text="Proxmox node operational status",
                    metric_type=MetricType.GAUGE
                ))
            
            logger.debug(f"Collected {len(metrics)} Proxmox system metrics")
            return metrics
        
        except Exception as e:
            logger.error(f"Proxmox system collection failed: {e}")
            return []