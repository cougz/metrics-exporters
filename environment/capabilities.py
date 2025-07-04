"""Environment capability mapping for different deployment contexts"""
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from enum import Enum
from .detection import EnvironmentType


class CollectionMethod(Enum):
    """Available collection methods for metrics"""
    CGROUP_V1 = "cgroup_v1"
    CGROUP_V2 = "cgroup_v2"
    PROC_FILESYSTEM = "proc_filesystem"
    HARDWARE_ACCESS = "hardware_access"
    SYSTEMD_SERVICES = "systemd_services"
    CONTAINER_LIMITS = "container_limits"
    NETWORK_NAMESPACES = "network_namespaces"
    FILESYSTEM_FULL = "filesystem_full"
    PROCESS_TREE_FULL = "process_tree_full"
    PROXMOX_API = "proxmox_api"
    LXC_COMMANDS = "lxc_commands"


@dataclass
class EnvironmentCapability:
    """Capability definition for an environment"""
    available_methods: Set[CollectionMethod]
    preferred_methods: List[CollectionMethod]
    fallback_methods: List[CollectionMethod]
    restrictions: List[str]
    special_features: List[str]


class EnvironmentCapabilities:
    """Maps environment types to their collection capabilities"""
    
    _capabilities: Dict[EnvironmentType, EnvironmentCapability] = {
        EnvironmentType.CONTAINER: EnvironmentCapability(
            available_methods={
                CollectionMethod.CGROUP_V1,
                CollectionMethod.CGROUP_V2,
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.CONTAINER_LIMITS,
                CollectionMethod.NETWORK_NAMESPACES,
            },
            preferred_methods=[
                CollectionMethod.CGROUP_V2,
                CollectionMethod.CGROUP_V1,
                CollectionMethod.CONTAINER_LIMITS,
            ],
            fallback_methods=[
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.NETWORK_NAMESPACES,
            ],
            restrictions=[
                "limited_proc_access",
                "container_scoped_metrics",
                "no_hardware_access",
                "restricted_filesystem_view"
            ],
            special_features=[
                "container_resource_limits",
                "cgroup_statistics",
                "namespace_isolation"
            ]
        ),
        
        EnvironmentType.HOST: EnvironmentCapability(
            available_methods={
                CollectionMethod.CGROUP_V1,
                CollectionMethod.CGROUP_V2,
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.HARDWARE_ACCESS,
                CollectionMethod.SYSTEMD_SERVICES,
                CollectionMethod.FILESYSTEM_FULL,
                CollectionMethod.PROCESS_TREE_FULL,
            },
            preferred_methods=[
                CollectionMethod.HARDWARE_ACCESS,
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.SYSTEMD_SERVICES,
            ],
            fallback_methods=[
                CollectionMethod.CGROUP_V2,
                CollectionMethod.CGROUP_V1,
            ],
            restrictions=[],
            special_features=[
                "full_hardware_access",
                "system_wide_metrics"
            ]
        ),
        
        EnvironmentType.UNKNOWN: EnvironmentCapability(
            available_methods={
                CollectionMethod.PROC_FILESYSTEM,
            },
            preferred_methods=[
                CollectionMethod.PROC_FILESYSTEM,
            ],
            fallback_methods=[],
            restrictions=[
                "limited_functionality",
                "basic_metrics_only"
            ],
            special_features=[]
        )
    }
    
    @classmethod
    def get_capabilities(cls, env_type: EnvironmentType) -> EnvironmentCapability:
        """Get capabilities for a specific environment type"""
        return cls._capabilities.get(env_type, cls._capabilities[EnvironmentType.UNKNOWN])
    
    @classmethod
    def has_method(cls, env_type: EnvironmentType, method: CollectionMethod) -> bool:
        """Check if an environment supports a specific collection method"""
        capabilities = cls.get_capabilities(env_type)
        return method in capabilities.available_methods
    
    @classmethod
    def get_preferred_methods(cls, env_type: EnvironmentType) -> List[CollectionMethod]:
        """Get preferred collection methods for an environment"""
        capabilities = cls.get_capabilities(env_type)
        return capabilities.preferred_methods
    
    @classmethod
    def get_fallback_methods(cls, env_type: EnvironmentType) -> List[CollectionMethod]:
        """Get fallback collection methods for an environment"""
        capabilities = cls.get_capabilities(env_type)
        return capabilities.fallback_methods
    
    @classmethod
    def get_restrictions(cls, env_type: EnvironmentType) -> List[str]:
        """Get restrictions for an environment"""
        capabilities = cls.get_capabilities(env_type)
        return capabilities.restrictions
    
    @classmethod
    def get_special_features(cls, env_type: EnvironmentType) -> List[str]:
        """Get special features available in an environment"""
        capabilities = cls.get_capabilities(env_type)
        return capabilities.special_features
    
    @classmethod
    def supports_hardware_access(cls, env_type: EnvironmentType) -> bool:
        """Check if environment supports hardware access"""
        return "full_hardware_access" in cls.get_special_features(env_type)
    
    @classmethod
    def get_optimal_collection_strategy(cls, env_type: EnvironmentType, 
                                       collector_type: str) -> List[CollectionMethod]:
        """Get optimal collection strategy for a specific collector type"""
        capabilities = cls.get_capabilities(env_type)
        
        # Define collector-specific method preferences
        collector_preferences = {
            "memory": {
                EnvironmentType.CONTAINER: [
                    CollectionMethod.CGROUP_V2,
                    CollectionMethod.CGROUP_V1,
                    CollectionMethod.CONTAINER_LIMITS,
                    CollectionMethod.PROC_FILESYSTEM
                ],
                EnvironmentType.HOST: [
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.HARDWARE_ACCESS,
                    CollectionMethod.CGROUP_V2
                ]
            },
            "cpu": {
                EnvironmentType.CONTAINER: [
                    CollectionMethod.CGROUP_V2,
                    CollectionMethod.CGROUP_V1,
                    CollectionMethod.PROC_FILESYSTEM
                ],
                EnvironmentType.HOST: [
                    CollectionMethod.HARDWARE_ACCESS,
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.CGROUP_V2
                ]
            },
            "disk": {
                EnvironmentType.CONTAINER: [
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.CGROUP_V2,
                    CollectionMethod.CGROUP_V1
                ],
                EnvironmentType.HOST: [
                    CollectionMethod.FILESYSTEM_FULL,
                    CollectionMethod.HARDWARE_ACCESS,
                    CollectionMethod.PROC_FILESYSTEM
                ]
            },
            "network": {
                EnvironmentType.CONTAINER: [
                    CollectionMethod.NETWORK_NAMESPACES,
                    CollectionMethod.PROC_FILESYSTEM
                ],
                EnvironmentType.HOST: [
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.HARDWARE_ACCESS,
                    CollectionMethod.NETWORK_NAMESPACES
                ]
            },
            "process": {
                EnvironmentType.CONTAINER: [
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.CGROUP_V2,
                    CollectionMethod.CGROUP_V1
                ],
                EnvironmentType.HOST: [
                    CollectionMethod.PROCESS_TREE_FULL,
                    CollectionMethod.PROC_FILESYSTEM,
                    CollectionMethod.SYSTEMD_SERVICES
                ]
            }
        }
        
        # Get collector-specific preferences
        env_preferences = collector_preferences.get(collector_type, {})
        preferred_methods = env_preferences.get(env_type, capabilities.preferred_methods)
        
        # Filter by available methods
        available_methods = []
        for method in preferred_methods:
            if method in capabilities.available_methods:
                available_methods.append(method)
        
        # Add fallback methods if needed
        if not available_methods:
            for method in capabilities.fallback_methods:
                if method in capabilities.available_methods:
                    available_methods.append(method)
        
        return available_methods