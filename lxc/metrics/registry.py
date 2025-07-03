"""Metrics registry for managing collectors and orchestrating collection"""
import importlib
import pkgutil
import logging
from typing import Dict, List, Type
from .models import MetricValue
from collectors.base import BaseCollector


logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Central registry for all metric collectors"""
    
    def __init__(self, config=None):
        self.config = config
        self.collectors: Dict[str, BaseCollector] = {}
        self.auto_discover_collectors()
    
    def auto_discover_collectors(self):
        """Automatically discover and register collectors"""
        import collectors
        
        # Get all modules in the collectors package
        for importer, modname, ispkg in pkgutil.iter_modules(collectors.__path__, collectors.__name__ + "."):
            if modname.endswith('.base'):
                continue  # Skip base module
                
            try:
                module = importlib.import_module(modname)
                
                # Look for collector classes in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseCollector) and 
                        attr != BaseCollector):
                        
                        # Instantiate and register collector
                        collector = attr(self.config)
                        self.register_collector(collector)
                        logger.info(f"Discovered collector: {collector.name}")
                        
            except Exception as e:
                logger.error(f"Failed to load collector module {modname}: {e}")
    
    def register_collector(self, collector: BaseCollector):
        """Register a new collector"""
        if not isinstance(collector, BaseCollector):
            raise ValueError("Collector must inherit from BaseCollector")
        
        self.collectors[collector.name] = collector
        logger.info(f"Registered collector: {collector.name}")
    
    def get_collector(self, name: str) -> BaseCollector:
        """Get collector by name"""
        return self.collectors.get(name)
    
    def list_collectors(self) -> List[str]:
        """List all registered collector names"""
        return list(self.collectors.keys())
    
    def collect_all(self) -> List[MetricValue]:
        """Collect metrics from all enabled collectors"""
        all_metrics = []
        
        for name, collector in self.collectors.items():
            if not collector.enabled:
                continue
                
            # Check if collector is enabled in config
            if self.config and hasattr(self.config, 'is_collector_enabled'):
                if not self.config.is_collector_enabled(name):
                    continue
            
            try:
                logger.debug(f"Collecting metrics from {name}")
                metrics = collector.collect()
                all_metrics.extend(metrics)
                logger.debug(f"Collected {len(metrics)} metrics from {name}")
                
            except Exception as e:
                logger.error(f"Collector {name} failed: {e}")
                # Continue with other collectors even if one fails
        
        return all_metrics
    
    def get_collector_status(self) -> Dict[str, Dict]:
        """Get status information for all collectors"""
        status = {}
        
        for name, collector in self.collectors.items():
            enabled = collector.enabled
            if self.config and hasattr(self.config, 'is_collector_enabled'):
                enabled = enabled and self.config.is_collector_enabled(name)
            
            status[name] = {
                "enabled": enabled,
                "class": collector.__class__.__name__,
                "help": collector.help_text
            }
        
        return status