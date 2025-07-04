"""Metrics registry for managing collectors and orchestrating collection"""
import asyncio
import importlib
import pkgutil
from typing import Dict, List, Type
from .models import MetricValue
from collectors.base import BaseCollector
from logging_config import get_logger


logger = get_logger(__name__)


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
        """Collect metrics from all enabled collectors (synchronous)"""
        all_metrics = []
        
        for name, collector in self.collectors.items():
            if not collector.is_enabled():
                continue
            
            try:
                logger.debug("Collecting metrics", collector=name, event_type="collection_start")
                metrics = collector.collect()
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
    
    async def _collect_single_async(self, name: str, collector: BaseCollector) -> List[MetricValue]:
        """Collect metrics from a single collector asynchronously"""
        try:
            logger.debug("Starting async collection", collector=name, event_type="async_collection_start")
            metrics = await collector.collect_async()
            logger.debug("Completed async collection", collector=name, metrics_count=len(metrics), event_type="async_collection_complete")
            return metrics
        except Exception as e:
            logger.error("Async collector failed", collector=name, error=str(e), event_type="async_collection_error", exc_info=True)
            return []
    
    def get_collector_status(self) -> Dict[str, Dict]:
        """Get status information for all collectors"""
        status = {}
        
        for name, collector in self.collectors.items():
            status[name] = {
                "enabled": collector.is_enabled(),
                "class": collector.__class__.__name__,
                "help": collector.help_text
            }
        
        return status
    
    def cleanup(self):
        """Cleanup all collectors"""
        for collector in self.collectors.values():
            try:
                collector.cleanup()
            except Exception as e:
                logger.error("Failed to cleanup collector", collector=collector.name, error=str(e))