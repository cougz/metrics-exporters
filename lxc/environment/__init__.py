"""Environment detection and capability mapping for platform-agnostic metrics collection"""
from .detection import EnvironmentDetector, EnvironmentType
from .capabilities import EnvironmentCapabilities
from .context import RuntimeEnvironment

__all__ = [
    'EnvironmentDetector',
    'EnvironmentType', 
    'EnvironmentCapabilities',
    'RuntimeEnvironment'
]