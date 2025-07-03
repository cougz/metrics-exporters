"""Base collector class and interfaces"""
from abc import ABC, abstractmethod
from typing import List
from metrics.models import MetricValue


class BaseCollector(ABC):
    """Base class for all metric collectors"""
    
    def __init__(self, config=None):
        self.config = config or {}
    
    @abstractmethod
    def collect(self) -> List[MetricValue]:
        """Collect metrics and return list of MetricValue objects"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Collector name for identification"""
        pass
    
    @property
    def enabled(self) -> bool:
        """Whether this collector is enabled"""
        return True
    
    @property
    def help_text(self) -> str:
        """Help text describing what this collector does"""
        return f"{self.name} metrics collector"
    
    def validate_number(self, value: str) -> bool:
        """Check if a string is a valid number"""
        if not value:
            return False
        try:
            float(value)
            return True
        except ValueError:
            return False