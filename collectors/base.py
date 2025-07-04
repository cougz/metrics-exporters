"""Simplified base collector"""
import asyncio
import socket
from abc import ABC, abstractmethod
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from metrics.models import MetricValue
from environment.context import runtime_context

class BaseCollector(ABC):
    """Base class for all metric collectors"""
    
    def __init__(self, config=None, name: str = "", help_text: str = ""):
        self.config = config or {}
        self._name = name
        self._help_text = help_text
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{name}_collector")
        self._strategy = self._get_strategy()
    
    def _get_strategy(self):
        """Get collection strategy based on environment"""
        runtime_env = runtime_context.get_runtime_environment()
        if runtime_env.is_container:
            from .strategies.container import ContainerStrategy
            return ContainerStrategy()
        elif runtime_env.is_host:
            from .strategies.host import HostStrategy
            return HostStrategy()
        else:
            from .strategies.fallback import FallbackStrategy
            return FallbackStrategy()
    
    @abstractmethod
    def collect(self) -> List[MetricValue]:
        """Collect metrics and return list of MetricValue objects"""
        pass
    
    async def collect_async(self) -> List[MetricValue]:
        """Async version of collect method"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.collect)
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def help_text(self) -> str:
        return self._help_text or f"{self.name} metrics collector"
    
    def is_enabled(self) -> bool:
        """Check if this collector is enabled"""
        if hasattr(self.config, 'enabled_collectors'):
            return self.name in self.config.enabled_collectors
        return True
    
    def collect_with_strategy(self, metric_type: str):
        """Collect metrics using the appropriate strategy for the current environment"""
        # Map metric types to strategy methods
        strategy_methods = {
            "cpu": "collect_cpu",
            "memory": "collect_memory", 
            "filesystem": "collect_filesystem",
            "network": "collect_network",
            "process": "collect_process",
            "sensors": "collect_sensors",
            "smart": "collect_smart",
            "zfs": "collect_zfs"
        }
        
        method_name = strategy_methods.get(metric_type)
        if not method_name:
            from .strategies.base import StrategyResult, StrategyStatus
            return StrategyResult(
                status=StrategyStatus.NOT_SUPPORTED,
                data={},
                errors=[f"Unknown metric type: {metric_type}"]
            )
        
        # Get the appropriate method from the strategy
        if hasattr(self._strategy, method_name):
            method = getattr(self._strategy, method_name)
            return method()
        else:
            from .strategies.base import StrategyResult, StrategyStatus
            return StrategyResult(
                status=StrategyStatus.NOT_SUPPORTED,
                data={},
                errors=[f"Strategy does not support {metric_type} collection"]
            )
    
    def get_standard_labels(self, additional_labels: Dict[str, str] = None) -> Dict[str, str]:
        """Get standard labels for OpenTelemetry"""
        runtime_env = runtime_context.get_runtime_environment()
        labels = {}
        
        # Simplified labeling to avoid Grafana conflicts
        hostname = runtime_env.metadata.get("hostname", socket.gethostname())
        labels["host_name"] = hostname
        
        if runtime_env.is_container:
            container_id = runtime_env.metadata.get("container_id")
            if container_id:
                # Use short container ID to avoid conflicts
                short_id = container_id[:12] if len(container_id) > 12 else container_id
                labels["instance"] = f"{hostname}-{short_id}"
            else:
                labels["instance"] = hostname
        else:
            labels["instance"] = hostname
        
        if additional_labels:
            labels.update(additional_labels)
            
        return labels
    
    def cleanup(self):
        """Cleanup resources"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)