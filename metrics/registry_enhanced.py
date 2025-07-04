"""Enhanced metrics registry with environment-aware collector management"""
import asyncio
import importlib
import pkgutil
from typing import Dict, List, Type, Optional
from .models import MetricValue
from collectors.base_enhanced import EnvironmentAwareCollector
from environment.context import runtime_context, EnvironmentType
from environment.detection import EnvironmentDetector
from logging_config import get_logger

logger = get_logger(__name__)


class EnvironmentAwareMetricsRegistry:
    """Environment-aware metrics registry that adapts collectors to runtime environment"""
    
    def __init__(self, config=None):
        self.config = config
        self.collectors: Dict[str, EnvironmentAwareCollector] = {}
        self._runtime_env = None
        self._initialize_environment()
        self._register_collectors()
    
    def _initialize_environment(self):
        """Initialize runtime environment detection"""
        try:
            # Handle forced environment from config
            if (hasattr(self.config, 'force_environment') and 
                self.config.force_environment):
                
                env_type_map = {
                    'container': EnvironmentType.CONTAINER,
                    'host': EnvironmentType.HOST,
                    'unknown': EnvironmentType.UNKNOWN
                }
                
                forced_env = env_type_map.get(self.config.force_environment.lower())
                if forced_env:
                    logger.info(f"Forcing environment to: {forced_env.value}")
                    self._runtime_env = runtime_context.initialize(
                        force_environment=forced_env
                    )
                else:
                    logger.warning(f"Invalid forced environment: {self.config.force_environment}")
                    self._runtime_env = runtime_context.initialize()
            else:
                # Auto-detect environment
                self._runtime_env = runtime_context.initialize()
            
            logger.info(f"Runtime environment: {self._runtime_env.environment_type.value}")
            
        except Exception as e:
            logger.error(f"Failed to initialize environment: {e}")
            # Fallback to basic initialization
            self._runtime_env = runtime_context.initialize()
    
    def _register_collectors(self):
        """Register collectors based on runtime environment and available hardware"""
        try:
            # Always start with environment-detected collectors
            auto_detected_collectors = self._runtime_env.get_default_collectors()
            
            # Use auto-detected collectors by default, allow config override only if explicitly set
            config_collectors = getattr(self.config, 'enabled_collectors', [])
            config_is_default = set(config_collectors) == {"memory", "filesystem", "process", "cpu", "network"}
            
            if config_collectors and not config_is_default:
                # Config has been explicitly overridden from defaults
                enabled_collectors = config_collectors
                logger.info(f"Using config-specified collectors: {enabled_collectors}")
                
                # Warn about potentially unavailable collectors
                for collector in enabled_collectors:
                    if collector not in auto_detected_collectors:
                        logger.warning(f"Collector '{collector}' enabled in config but not auto-detected for this environment")
                
                # Suggest auto-detected collectors if config is more limited
                missing_auto = set(auto_detected_collectors) - set(enabled_collectors)
                if missing_auto:
                    logger.info(f"Auto-detected collectors not in config: {list(missing_auto)}")
            else:
                # Use auto-detected collectors (config is at defaults or empty)
                enabled_collectors = auto_detected_collectors
                logger.info(f"Using auto-detected collectors (config at defaults): {enabled_collectors}")
                
                # Update config to reflect the auto-detected collectors so is_collector_enabled works correctly
                if hasattr(self.config, 'enabled_collectors'):
                    self.config.enabled_collectors = enabled_collectors
                    logger.debug(f"Updated config.enabled_collectors to: {enabled_collectors}")
            
            logger.info(f"Auto-detected collectors: {auto_detected_collectors}")
            logger.info(f"Enabled collectors: {enabled_collectors}")
            
            # Register core collectors
            self._register_core_collectors(enabled_collectors)
            
            # Register environment-specific collectors
            self._register_environment_specific_collectors()
            
        except Exception as e:
            logger.error(f"Failed to register collectors: {e}")
    
    def _register_core_collectors(self, enabled_collectors: List[str]):
        """Register core collectors using enhanced versions"""
        collector_mapping = {
            'memory': ('collectors.memory_enhanced', 'MemoryCollector'),
            'cpu': ('collectors.cpu_enhanced', 'CPUCollector'),
            'filesystem': ('collectors.filesystem_enhanced', 'FilesystemCollector'),
            'network': ('collectors.network_enhanced', 'NetworkCollector'),
            'process': ('collectors.process_enhanced', 'ProcessCollector'),
            'sensors': ('collectors.sensors_enhanced', 'SensorsCollector'),
            'smart': ('collectors.smart_enhanced', 'SmartCollector'),
            'zfs': ('collectors.zfs_enhanced', 'ZFSCollector'),
        }
        
        for collector_name in enabled_collectors:
            if collector_name in collector_mapping:
                module_name, class_name = collector_mapping[collector_name]
                
                try:
                    module = importlib.import_module(module_name)
                    collector_class = getattr(module, class_name)
                    collector = collector_class(self.config)
                    
                    self.collectors[collector_name] = collector
                    logger.info(f"Registered enhanced collector: {collector_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to register collector {collector_name}: {e}")
                    # Try fallback to original collector
                    self._register_fallback_collector(collector_name)
    
    def _register_environment_specific_collectors(self):
        """Register collectors specific to the current environment"""
        try:
            # Environment-specific collectors can be added here if needed
            pass
            
            # Could add other environment-specific collectors here
            
        except Exception as e:
            logger.error(f"Failed to register environment-specific collectors: {e}")
    
    
    def _register_fallback_collector(self, collector_name: str):
        """Register fallback to original collector if enhanced version fails"""
        try:
            # Import original collectors as fallback
            original_mapping = {
                'memory': ('collectors.memory', 'MemoryCollector'),
                'cpu': ('collectors.cpu', 'CPUCollector'),
                'filesystem': ('collectors.disk', 'DiskCollector'),  # Fallback to old disk collector
                'network': ('collectors.network', 'NetworkCollector'),
                'process': ('collectors.process', 'ProcessCollector'),
            }
            
            if collector_name in original_mapping:
                module_name, class_name = original_mapping[collector_name]
                module = importlib.import_module(module_name)
                collector_class = getattr(module, class_name)
                collector = collector_class(self.config)
                
                self.collectors[collector_name] = collector
                logger.warning(f"Using fallback collector for {collector_name}")
                
        except Exception as e:
            logger.error(f"Failed to register fallback collector {collector_name}: {e}")
    
    def auto_discover_collectors(self):
        """Auto-discover additional collectors (legacy compatibility)"""
        try:
            import collectors
            
            # Get all modules in the collectors package
            for importer, modname, ispkg in pkgutil.iter_modules(collectors.__path__, collectors.__name__ + "."):
                if modname.endswith('.base') or modname.endswith('_enhanced'):
                    continue  # Skip base and enhanced modules
                    
                try:
                    module = importlib.import_module(modname)
                    
                    # Look for collector classes in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            hasattr(attr, 'collect') and
                            attr_name.endswith('Collector') and
                            attr_name not in ['BaseCollector', 'EnvironmentAwareCollector']):
                            
                            collector_name = attr_name.lower().replace('collector', '')
                            
                            # Only register if not already registered
                            if collector_name not in self.collectors:
                                collector = attr(self.config)
                                self.collectors[collector_name] = collector
                                logger.info(f"Auto-discovered collector: {collector_name}")
                            
                except Exception as e:
                    logger.error(f"Failed to auto-discover in module {modname}: {e}")
                    
        except Exception as e:
            logger.error(f"Auto-discovery failed: {e}")
    
    def register_collector(self, collector: EnvironmentAwareCollector):
        """Register a new collector"""
        if not hasattr(collector, 'collect'):
            raise ValueError("Collector must have a collect method")
        
        self.collectors[collector.name] = collector
        logger.info(f"Manually registered collector: {collector.name}")
    
    def get_collector(self, name: str) -> Optional[EnvironmentAwareCollector]:
        """Get collector by name"""
        return self.collectors.get(name)
    
    def list_collectors(self) -> List[str]:
        """List all registered collector names"""
        return list(self.collectors.keys())
    
    def collect_all(self) -> List[MetricValue]:
        """Collect metrics from all enabled collectors (synchronous)"""
        all_metrics = []
        
        for name, collector in self.collectors.items():
            if not collector.is_enabled():
                continue
            
            try:
                logger.debug("Collecting metrics", collector=name, event_type="collection_start")
                metrics = collector.collect()
                
                # Add collector name to each metric for debugging
                for metric in metrics:
                    metric.collector_name = name
                
                all_metrics.extend(metrics)
                logger.debug("Collected metrics", collector=name, metrics_count=len(metrics), event_type="collection_complete")
                
            except Exception as e:
                logger.error("Collector failed", collector=name, error=str(e), event_type="collection_error", exc_info=True)
                # Continue with other collectors even if one fails
        
        return all_metrics
    
    async def collect_all_async(self) -> List[MetricValue]:
        """Collect metrics from all enabled collectors asynchronously"""
        tasks = []
        
        for name, collector in self.collectors.items():
            if not collector.is_enabled():
                continue
            tasks.append(self._collect_single_async(name, collector))
        
        if not tasks:
            return []
        
        # Execute all collections concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results and handle exceptions
        all_metrics = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("Async collection failed", error=str(result), event_type="async_collection_error", exc_info=True)
            elif isinstance(result, list):
                all_metrics.extend(result)
        
        return all_metrics
    
    async def _collect_single_async(self, name: str, collector: EnvironmentAwareCollector) -> List[MetricValue]:
        """Collect metrics from a single collector asynchronously"""
        try:
            logger.debug("Starting async collection", collector=name, event_type="async_collection_start")
            metrics = await collector.collect_async()
            
            # Add collector name to each metric for debugging
            for metric in metrics:
                metric.collector_name = name
            
            logger.debug("Completed async collection", collector=name, metrics_count=len(metrics), event_type="async_collection_complete")
            return metrics
        except Exception as e:
            logger.error("Async collector failed", collector=name, error=str(e), event_type="async_collection_error", exc_info=True)
            return []
    
    def get_collector_status(self) -> Dict[str, Dict]:
        """Get status information for all collectors"""
        # Get auto-detected collectors to show which ones are available
        auto_detected_collectors = self._runtime_env.get_default_collectors()
        
        # Define all possible collectors
        all_possible_collectors = {
            'memory': 'Memory usage metrics with environment-aware collection',
            'cpu': 'CPU usage metrics with environment-aware collection', 
            'filesystem': 'Filesystem usage metrics with environment-aware collection',
            'network': 'Network metrics with environment-aware collection',
            'process': 'Process metrics with environment-aware collection',
            'zfs': 'ZFS pool metrics (host environments only)',
            'sensors': 'Hardware temperature sensors using sensors command (host environments only)',
            'smart': 'SMART disk health monitoring (host environments only, optional)'
        }
        
        status = {
            "environment": {
                "type": self._runtime_env.environment_type.value,
                "detection_confidence": self._runtime_env.detection_result.confidence,
                "detection_methods": self._runtime_env.detection_result.detection_methods,
                "supports_hardware_access": self._runtime_env.supports_hardware_access,
            },
            "collectors": {}
        }
        
        # Add registered collectors
        for name, collector in self.collectors.items():
            status["collectors"][name] = {
                "enabled": collector.is_enabled(),
                "registered": True,
                "auto_detected": name in auto_detected_collectors,
                "class": collector.__class__.__name__,
                "help": collector.help_text,
                "strategy": getattr(collector.get_collection_strategy(), 'name', 'unknown') if hasattr(collector, 'get_collection_strategy') else 'legacy'
            }
        
        # Add auto-detected but not registered collectors
        for name in auto_detected_collectors:
            if name not in status["collectors"]:
                status["collectors"][name] = {
                    "enabled": False,
                    "registered": False,
                    "auto_detected": True,
                    "class": "Not Registered",
                    "help": all_possible_collectors.get(name, "Auto-detected collector"),
                    "strategy": "N/A"
                }
        
        # Add other possible collectors that weren't auto-detected
        for name, description in all_possible_collectors.items():
            if name not in status["collectors"]:
                status["collectors"][name] = {
                    "enabled": False,
                    "registered": False,
                    "auto_detected": False,
                    "class": "Not Available",
                    "help": description,
                    "strategy": "N/A"
                }
        
        return status
    
    def get_runtime_environment(self):
        """Get the current runtime environment"""
        return self._runtime_env
    
    def cleanup(self):
        """Cleanup all collectors"""
        for collector in self.collectors.values():
            try:
                collector.cleanup()
            except Exception as e:
                logger.error("Failed to cleanup collector", collector=collector.name, error=str(e))


# For backward compatibility, create an alias
MetricsRegistry = EnvironmentAwareMetricsRegistry