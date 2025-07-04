"""Base strategy interface for metrics collection"""
import abc
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from environment.capabilities import CollectionMethod


class StrategyStatus(Enum):
    """Status of a collection strategy execution"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    NOT_SUPPORTED = "not_supported"


@dataclass
class StrategyResult:
    """Result of a collection strategy execution"""
    status: StrategyStatus
    data: Dict[str, Any]
    errors: List[str]
    method_used: Optional[CollectionMethod] = None
    fallback_attempted: bool = False
    
    @property
    def is_success(self) -> bool:
        """Check if strategy was successful"""
        return self.status in [StrategyStatus.SUCCESS, StrategyStatus.PARTIAL_SUCCESS]
    
    @property
    def has_data(self) -> bool:
        """Check if strategy returned any data"""
        return bool(self.data)


class CollectionStrategy(abc.ABC):
    """Abstract base class for collection strategies"""
    
    def __init__(self, name: str, supported_methods: List[CollectionMethod]):
        self.name = name
        self.supported_methods = supported_methods
        self._method_cache: Dict[str, CollectionMethod] = {}
    
    @abc.abstractmethod
    def collect_memory(self) -> StrategyResult:
        """Collect memory metrics"""
        pass
    
    @abc.abstractmethod
    def collect_cpu(self) -> StrategyResult:
        """Collect CPU metrics"""
        pass
    
    @abc.abstractmethod
    def collect_disk(self) -> StrategyResult:
        """Collect disk metrics"""
        pass
    
    @abc.abstractmethod
    def collect_network(self) -> StrategyResult:
        """Collect network metrics"""
        pass
    
    @abc.abstractmethod
    def collect_process(self) -> StrategyResult:
        """Collect process metrics"""
        pass
    
    def supports_method(self, method: CollectionMethod) -> bool:
        """Check if strategy supports a collection method"""
        return method in self.supported_methods
    
    def get_preferred_method(self, metric_type: str) -> Optional[CollectionMethod]:
        """Get preferred collection method for a metric type"""
        if metric_type in self._method_cache:
            return self._method_cache[metric_type]
        
        # Default implementation - subclasses should override
        return self.supported_methods[0] if self.supported_methods else None
    
    def _create_success_result(self, data: Dict[str, Any], 
                              method: CollectionMethod) -> StrategyResult:
        """Create a successful result"""
        return StrategyResult(
            status=StrategyStatus.SUCCESS,
            data=data,
            errors=[],
            method_used=method
        )
    
    def _create_partial_result(self, data: Dict[str, Any], 
                              errors: List[str],
                              method: CollectionMethod) -> StrategyResult:
        """Create a partial success result"""
        return StrategyResult(
            status=StrategyStatus.PARTIAL_SUCCESS,
            data=data,
            errors=errors,
            method_used=method
        )
    
    def _create_failure_result(self, errors: List[str],
                              method: Optional[CollectionMethod] = None) -> StrategyResult:
        """Create a failure result"""
        return StrategyResult(
            status=StrategyStatus.FAILURE,
            data={},
            errors=errors,
            method_used=method
        )
    
    def _create_not_supported_result(self, reason: str) -> StrategyResult:
        """Create a not supported result"""
        return StrategyResult(
            status=StrategyStatus.NOT_SUPPORTED,
            data={},
            errors=[reason]
        )
    
    def _safe_read_file(self, file_path: str) -> Optional[str]:
        """Safely read a file, returning None on error"""
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except (OSError, IOError, PermissionError):
            return None
    
    def _safe_read_int(self, file_path: str) -> Optional[int]:
        """Safely read an integer from a file"""
        content = self._safe_read_file(file_path)
        if content:
            try:
                return int(content)
            except ValueError:
                pass
        return None
    
    def _safe_read_float(self, file_path: str) -> Optional[float]:
        """Safely read a float from a file"""
        content = self._safe_read_file(file_path)
        if content:
            try:
                return float(content)
            except ValueError:
                pass
        return None
    
    def _parse_key_value_file(self, file_path: str) -> Dict[str, str]:
        """Parse a key-value file like /proc/meminfo"""
        data = {}
        content = self._safe_read_file(file_path)
        if content:
            for line in content.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    data[key.strip()] = value.strip()
        return data
    
    def _bytes_to_kb(self, bytes_value: int) -> int:
        """Convert bytes to kilobytes"""
        return bytes_value // 1024
    
    def _kb_to_bytes(self, kb_value: int) -> int:
        """Convert kilobytes to bytes"""
        return kb_value * 1024