"""Runtime environment context for the metrics exporter"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from .detection import EnvironmentDetector, EnvironmentType, DetectionResult
from .capabilities import EnvironmentCapabilities, CollectionMethod

logger = logging.getLogger(__name__)


@dataclass
class RuntimeEnvironment:
    """Runtime environment context with detection results and capabilities"""
    detection_result: DetectionResult
    capabilities: 'EnvironmentCapabilities'
    metadata: Dict[str, Any]
    
    @property
    def environment_type(self) -> EnvironmentType:
        """Get the detected environment type"""
        return self.detection_result.environment_type
    
    @property
    def is_container(self) -> bool:
        """Check if running in a container environment"""
        return self.environment_type == EnvironmentType.CONTAINER
    
    @property
    def is_host(self) -> bool:
        """Check if running on a host environment"""
        return self.environment_type == EnvironmentType.HOST
    
    @property
    def supports_hardware_access(self) -> bool:
        """Check if hardware access is supported"""
        return self.capabilities.supports_hardware_access(self.environment_type)
    
    def get_optimal_collection_methods(self, collector_type: str) -> list[CollectionMethod]:
        """Get optimal collection methods for a collector type"""
        return self.capabilities.get_optimal_collection_strategy(
            self.environment_type, collector_type
        )
    
    def has_collection_method(self, method: CollectionMethod) -> bool:
        """Check if a specific collection method is available"""
        return self.capabilities.has_method(self.environment_type, method)
    
    def get_instance_labels(self) -> Dict[str, str]:
        """Generate appropriate instance labels for the environment"""
        labels = {}
        
        if self.is_container:
            # Container-specific labels
            container_id = self.metadata.get("container_id")
            hostname = self.metadata.get("hostname")
            
            if container_id:
                labels["container_id"] = str(container_id)
            if hostname:
                labels["host_name"] = hostname
                if container_id:
                    labels["instance"] = f"{hostname}:{container_id}"
                else:
                    labels["instance"] = hostname
        
        elif self.is_host:
            # Host labels
            hostname = self.metadata.get("hostname")
            if hostname:
                labels["host_name"] = hostname
                labels["instance"] = f"host-{hostname}"
        
        return labels
    
    def get_default_collectors(self) -> list[str]:
        """Get default collectors for the environment"""
        if self.is_container:
            return ["memory", "cpu", "filesystem", "network", "process"]
        elif self.is_host:
            return ["memory", "cpu", "filesystem", "network", "process", "sensors_cpu", "sensors_nvme", "zfs"]
        else:
            return ["memory", "process"]  # Minimal set for unknown environments
    
    def get_collection_interval(self) -> int:
        """Get recommended collection interval for the environment"""
        return 30  # Standard interval for all environments


class EnvironmentContext:
    """Singleton context manager for runtime environment"""
    
    _instance: Optional['EnvironmentContext'] = None
    _runtime_env: Optional[RuntimeEnvironment] = None
    
    def __new__(cls) -> 'EnvironmentContext':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._detector = EnvironmentDetector()
            self._initialized = True
    
    def initialize(self, force_redetect: bool = False, 
                  force_environment: Optional[EnvironmentType] = None) -> RuntimeEnvironment:
        """Initialize runtime environment context"""
        if force_environment:
            self._detector.force_environment(force_environment)
        
        if not self._runtime_env or force_redetect:
            # Detect environment
            detection_result = self._detector.detect(force_redetect)
            
            # Get capabilities
            capabilities = EnvironmentCapabilities()
            
            # Gather additional metadata
            metadata = self._gather_metadata(detection_result)
            
            # Create runtime environment
            self._runtime_env = RuntimeEnvironment(
                detection_result=detection_result,
                capabilities=capabilities,
                metadata=metadata
            )
            
            logger.info(f"Runtime environment initialized: {self._runtime_env.environment_type.value}")
        
        return self._runtime_env
    
    def get_runtime_environment(self) -> Optional[RuntimeEnvironment]:
        """Get current runtime environment (initialize if needed)"""
        if not self._runtime_env:
            return self.initialize()
        return self._runtime_env
    
    def _gather_metadata(self, detection_result: DetectionResult) -> Dict[str, Any]:
        """Gather additional metadata about the environment"""
        metadata = detection_result.metadata.copy()
        
        # Add hostname
        try:
            import socket
            metadata["hostname"] = socket.gethostname()
        except Exception:
            metadata["hostname"] = "unknown"
        
        # Add container ID if in container
        if detection_result.environment_type == EnvironmentType.CONTAINER:
            try:
                from utils.container import extract_container_id
                container_id = extract_container_id()
                if container_id:
                    metadata["container_id"] = container_id
            except Exception as e:
                logger.warning(f"Could not extract container ID: {e}")
        
        return metadata


# Global instance for easy access
runtime_context = EnvironmentContext()