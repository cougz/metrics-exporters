"""Collection strategies for different runtime environments"""
from .base import CollectionStrategy, StrategyResult
from .container import ContainerStrategy
from .host import HostStrategy
from .fallback import FallbackStrategy

__all__ = [
    'CollectionStrategy',
    'StrategyResult',
    'ContainerStrategy',
    'HostStrategy', 
    'FallbackStrategy'
]