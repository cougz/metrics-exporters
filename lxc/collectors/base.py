"""Base collector class and interfaces"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from metrics.models import MetricValue


class BaseCollector(ABC):
    """Base class for all metric collectors"""
    
    def __init__(self, config=None, name: str = "", help_text: str = ""):
        self.config = config or {}
        self._name = name
        self._help_text = help_text
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{name}_collector")
    
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