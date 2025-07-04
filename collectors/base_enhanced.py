"""Enhanced base collector with environment-aware strategy selection"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from metrics.models import MetricValue, MetricType
from environment.context import runtime_context, RuntimeEnvironment
from environment.capabilities import CollectionMethod
from .strategies.base import CollectionStrategy, StrategyResult
from .strategies.container import ContainerStrategy
from .strategies.host import HostStrategy
from .strategies.fallback import FallbackStrategy

logger = logging.getLogger(__name__)


class EnvironmentAwareCollector(ABC):
    """Enhanced base collector with environment-aware strategy selection"""
    
    def __init__(self, config=None, name: str = "", help_text: str = ""):
        self.config = config or {}
        self._name = name
        self._help_text = help_text
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{name}_collector")
        
        # Environment and strategy management
        self._runtime_env: Optional[RuntimeEnvironment] = None
        self._strategy: Optional[CollectionStrategy] = None
        self._strategy_initialized = False
    
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
        """Collector name for identification"""
        return self._name
    
    @property
    def help_text(self) -> str:
        """Help text describing what this collector does"""
        return self._help_text or f"{self.name} metrics collector"
    
    def is_enabled(self) -> bool:
        """Check if this collector is enabled"""
        if hasattr(self.config, 'is_collector_enabled'):
            return self.config.is_collector_enabled(self.name)
        return True
    
    def get_runtime_environment(self) -> RuntimeEnvironment:
        """Get runtime environment, initializing if needed"""
        if not self._runtime_env:
            self._runtime_env = runtime_context.get_runtime_environment()
        return self._runtime_env
    
    def get_collection_strategy(self) -> CollectionStrategy:
        """Get appropriate collection strategy for current environment"""
        if not self._strategy_initialized:
            self._initialize_strategy()
        
        if not self._strategy:
            # Fallback to basic strategy
            logger.warning(f"No strategy available for {self.name} collector, using fallback")
            self._strategy = FallbackStrategy()
        
        return self._strategy
    
    def _initialize_strategy(self) -> None:
        """Initialize collection strategy based on environment"""
        try:
            runtime_env = self.get_runtime_environment()
            
            if runtime_env.is_container:
                self._strategy = ContainerStrategy()
                logger.debug(f"Using container strategy for {self.name} collector")
            
            elif runtime_env.is_host:
                self._strategy = HostStrategy()
                logger.debug(f"Using host strategy for {self.name} collector")
            
            else:
                self._strategy = FallbackStrategy()
                logger.debug(f"Using fallback strategy for {self.name} collector")
            
            self._strategy_initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize strategy for {self.name} collector: {e}")
            self._strategy = FallbackStrategy()
            self._strategy_initialized = True
    
    def collect_with_strategy(self, metric_type: str) -> StrategyResult:
        """Collect metrics using environment-appropriate strategy"""
        strategy = self.get_collection_strategy()
        
        try:
            if metric_type == "memory":
                return strategy.collect_memory()
            elif metric_type == "cpu":
                return strategy.collect_cpu()
            elif metric_type == "disk" or metric_type == "filesystem":
                return strategy.collect_filesystem()
            elif metric_type == "network":
                return strategy.collect_network()
            elif metric_type == "process":
                return strategy.collect_process()
            elif metric_type == "zfs":
                return strategy.collect_zfs()
            elif metric_type == "sensors_cpu":
                return strategy.collect_sensors_cpu()
            elif metric_type == "sensors_nvme":
                return strategy.collect_sensors_nvme()
            elif metric_type == "sensors":
                return strategy.collect_sensors()
            elif metric_type == "smart":
                return strategy.collect_smart()
            else:
                return strategy._create_not_supported_result(f"Unknown metric type: {metric_type}")
        
        except Exception as e:
            logger.error(f"Strategy collection failed for {metric_type}: {e}")
            return strategy._create_failure_result([f"Collection error: {e}"])
    
    def get_standard_labels(self, additional_labels: Dict[str, str] = None) -> Dict[str, str]:
        """Get standard labels based on environment context"""
        try:
            runtime_env = self.get_runtime_environment()
            labels = runtime_env.get_instance_labels()
            
            if additional_labels:
                labels.update(additional_labels)
            
            return labels
        
        except Exception as e:
            logger.error(f"Failed to get environment labels: {e}")
            # Fallback to basic labels
            import socket
            from utils.container import extract_container_id
            
            hostname = socket.gethostname()
            container_id = extract_container_id() or "unknown"
            
            labels = {
                "host_name": hostname,
                "container_id": container_id,
                "instance": f"{hostname}:{container_id}"
            }
            
            if additional_labels:
                labels.update(additional_labels)
            
            return labels
    
    def strategy_result_to_metrics(self, result: StrategyResult, 
                                  metric_name_prefix: str,
                                  metric_type: MetricType = MetricType.GAUGE,
                                  labels: Optional[Dict[str, str]] = None) -> List[MetricValue]:
        """Convert strategy result to MetricValue objects"""
        metrics = []
        
        if not result.is_success or not result.has_data:
            logger.warning(f"Strategy result failed for {metric_name_prefix}: {result.errors}")
            return metrics
        
        base_labels = labels or self.get_standard_labels()
        
        # Convert data to metrics
        for key, value in result.data.items():
            if isinstance(value, (int, float)):
                metric_name = f"{metric_name_prefix}_{key}"
                
                try:
                    metric = MetricValue(
                        name=metric_name,
                        value=float(value),
                        labels=base_labels.copy(),
                        metric_type=metric_type,
                        help_text=f"{key.replace('_', ' ').title()}"
                    )
                    metrics.append(metric)
                except Exception as e:
                    logger.error(f"Failed to create metric {metric_name}: {e}")
            
            elif isinstance(value, dict):
                # Handle nested data (like interfaces, filesystems)
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict):
                        # Add sub_key as label and create metrics for numeric values
                        sub_labels = base_labels.copy()
                        sub_labels[key.rstrip('s')] = str(sub_key)  # interface -> eth0, filesystem -> /
                        
                        for metric_key, metric_value in sub_value.items():
                            if isinstance(metric_value, (int, float)):
                                metric_name = f"{metric_name_prefix}_{metric_key}"
                                
                                try:
                                    metric = MetricValue(
                                        name=metric_name,
                                        value=float(metric_value),
                                        labels=sub_labels.copy(),
                                        metric_type=metric_type,
                                        help_text=f"{metric_key.replace('_', ' ').title()}"
                                    )
                                    metrics.append(metric)
                                except Exception as e:
                                    logger.error(f"Failed to create nested metric {metric_name}: {e}")
            
            elif isinstance(value, list):
                # Handle list data (like filesystem info)
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        item_labels = base_labels.copy()
                        
                        # Use meaningful labels from the item if available
                        if "device" in item:
                            item_labels["device"] = str(item["device"])
                        if "mountpoint" in item:
                            item_labels["mountpoint"] = str(item["mountpoint"])
                        if "fstype" in item:
                            item_labels["fstype"] = str(item["fstype"])
                        
                        # Create info metric for this item
                        metric_name = f"{metric_name_prefix}_{key}_info"
                        try:
                            metric = MetricValue(
                                name=metric_name,
                                value=1.0,
                                labels=item_labels,
                                metric_type=MetricType.GAUGE,
                                help_text=f"{key.replace('_', ' ').title()} information"
                            )
                            metrics.append(metric)
                        except Exception as e:
                            logger.error(f"Failed to create list metric {metric_name}: {e}")
        
        return metrics
    
    def validate_number(self, value: str) -> bool:
        """Check if a string is a valid number"""
        if not value:
            return False
        try:
            float(value)
            return True
        except ValueError:
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)


# For backward compatibility, create an alias
BaseCollector = EnvironmentAwareCollector