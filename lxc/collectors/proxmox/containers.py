"""Container inventory collector for Proxmox hosts"""
import logging
from typing import List
from ..base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class ContainerInventoryCollector(EnvironmentAwareCollector):
    """Container and VM inventory metrics for Proxmox hosts"""
    
    def __init__(self, config=None):
        super().__init__(config, "container_inventory", "Container and VM inventory metrics")
    
    def collect(self) -> List[MetricValue]:
        """Collect container and VM inventory metrics"""
        try:
            runtime_env = self.get_runtime_environment()
            
            # Only run on Proxmox hosts with multi-container support
            if not runtime_env.supports_multi_container:
                logger.debug("Container inventory collector skipped - no multi-container support")
                return []
            
            # Use host strategy to collect container inventory
            strategy = self.get_collection_strategy()
            
            if hasattr(strategy, 'collect_container_inventory'):
                result = strategy.collect_container_inventory()
            else:
                logger.warning("Strategy does not support container inventory collection")
                return []
            
            if not result.is_success:
                logger.warning(f"Container inventory collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Container summary metrics
            container_metrics = [
                ("container_count", "proxmox_containers_total", "Total number of LXC containers"),
                ("running_containers", "proxmox_containers_running", "Number of running LXC containers"),
                ("stopped_containers", "proxmox_containers_stopped", "Number of stopped LXC containers"),
            ]
            
            for data_key, metric_name, help_text in container_metrics:
                if data_key in data:
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(data[data_key]),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=MetricType.GAUGE
                    ))
            
            # VM summary metrics
            vm_metrics = [
                ("vm_count", "proxmox_vms_total", "Total number of VMs"),
                ("running_vms", "proxmox_vms_running", "Number of running VMs"),
                ("stopped_vms", "proxmox_vms_stopped", "Number of stopped VMs"),
            ]
            
            for data_key, metric_name, help_text in vm_metrics:
                if data_key in data:
                    metrics.append(MetricValue(
                        name=metric_name,
                        value=float(data[data_key]),
                        labels=labels.copy(),
                        help_text=help_text,
                        metric_type=MetricType.GAUGE
                    ))
            
            # Individual container status
            if "containers" in data:
                for container in data["containers"]:
                    if isinstance(container, dict):
                        container_labels = labels.copy()
                        container_labels.update({
                            "container_id": str(container.get("id", "unknown")),
                            "container_name": str(container.get("name", "unknown"))
                        })
                        
                        status_value = 1.0 if container.get("status") == "running" else 0.0
                        metrics.append(MetricValue(
                            name="proxmox_container_up",
                            value=status_value,
                            labels=container_labels,
                            help_text="Container operational status",
                            metric_type=MetricType.GAUGE
                        ))
            
            # Individual VM status
            if "vms" in data:
                for vm in data["vms"]:
                    if isinstance(vm, dict):
                        vm_labels = labels.copy()
                        vm_labels.update({
                            "vm_id": str(vm.get("id", "unknown")),
                            "vm_name": str(vm.get("name", "unknown"))
                        })
                        
                        status_value = 1.0 if vm.get("status") == "running" else 0.0
                        metrics.append(MetricValue(
                            name="proxmox_vm_up",
                            value=status_value,
                            labels=vm_labels,
                            help_text="VM operational status",
                            metric_type=MetricType.GAUGE
                        ))
            
            logger.debug(f"Collected {len(metrics)} container inventory metrics")
            return metrics
        
        except Exception as e:
            logger.error(f"Container inventory collection failed: {e}")
            return []