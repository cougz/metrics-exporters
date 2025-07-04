"""Enhanced utility functions for LXC container identification and resource detection"""
import re
import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class CgroupVersion(Enum):
    """Cgroup version enumeration"""
    V1 = "v1"
    V2 = "v2"
    UNKNOWN = "unknown"


@dataclass
class LXCContainerInfo:
    """Comprehensive LXC container information"""
    container_id: Optional[str] = None
    is_lxc_container: bool = False
    cgroup_version: CgroupVersion = CgroupVersion.UNKNOWN
    hostname: Optional[str] = None
    detection_method: Optional[str] = None
    resource_limits: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.resource_limits is None:
            self.resource_limits = {}


class LXCDetector:
    """Enhanced LXC container detection with caching and comprehensive methods"""
    
    _cache: Optional[LXCContainerInfo] = None
    _cache_timestamp: float = 0
    _cache_ttl: float = 300  # 5 minutes cache TTL
    
    @classmethod
    def get_container_info(cls) -> LXCContainerInfo:
        """Get cached or detect LXC container information"""
        current_time = time.time()
        
        # Return cached result if still valid
        if (cls._cache is not None and 
            current_time - cls._cache_timestamp < cls._cache_ttl):
            return cls._cache
        
        # Perform fresh detection
        info = cls._detect_container_info()
        
        # Cache the result
        cls._cache = info
        cls._cache_timestamp = current_time
        
        return info
    
    @classmethod
    def _detect_container_info(cls) -> LXCContainerInfo:
        """Comprehensive LXC container detection"""
        info = LXCContainerInfo()
        
        # Get hostname
        try:
            info.hostname = socket.gethostname()
        except Exception:
            pass
        
        # Detect cgroup version first
        info.cgroup_version = cls._detect_cgroup_version()
        
        # Try multiple detection methods
        detection_methods = [
            cls._detect_from_proxmox_device,
            cls._detect_from_cgroup_path,
            cls._detect_from_systemd_machined,
            cls._detect_from_hostname,
            cls._detect_from_environment
        ]
        
        for method in detection_methods:
            try:
                result = method()
                if result:
                    info.container_id = result
                    info.is_lxc_container = True
                    info.detection_method = method.__name__
                    break
            except Exception as e:
                logger.debug(f"Detection method {method.__name__} failed: {e}")
                continue
        
        # Detect resource limits if we found a container
        if info.is_lxc_container:
            info.resource_limits = cls._detect_resource_limits(info.cgroup_version)
        
        return info
    
    @classmethod
    def _detect_cgroup_version(cls) -> CgroupVersion:
        """Detect cgroup version (v1 or v2)"""
        try:
            # Check for cgroup v2 (unified hierarchy)
            if os.path.exists("/sys/fs/cgroup/cgroup.controllers"):
                return CgroupVersion.V2
            
            # Check for cgroup v1 (legacy hierarchy)
            if os.path.exists("/sys/fs/cgroup/cpuacct"):
                return CgroupVersion.V1
            
            # Fallback: check /proc/filesystems
            with open("/proc/filesystems", "r") as f:
                content = f.read()
                if "cgroup2" in content:
                    return CgroupVersion.V2
                elif "cgroup" in content:
                    return CgroupVersion.V1
        
        except Exception as e:
            logger.debug(f"Cgroup version detection failed: {e}")
        
        return CgroupVersion.UNKNOWN
    
    @classmethod
    def _detect_from_proxmox_device(cls) -> Optional[str]:
        """Detect container ID from Proxmox VE device pattern"""
        try:
            result = subprocess.run(
                ["df", "/"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    device = lines[1].split()[0]
                    # Proxmox pattern: subvol-XXXXX-disk-X
                    match = re.search(r'subvol-(\d+)-disk-\d+', device)
                    if match:
                        return match.group(1)
                    
                    # Alternative patterns
                    match = re.search(r'/(\d+)/', device)
                    if match:
                        return match.group(1)
        
        except Exception as e:
            logger.debug(f"Proxmox device detection failed: {e}")
        
        return None
    
    @classmethod
    def _detect_from_cgroup_path(cls) -> Optional[str]:
        """Detect container ID from cgroup path"""
        try:
            with open("/proc/self/cgroup", "r") as f:
                for line in f:
                    line = line.strip()
                    
                    # LXC patterns in cgroup paths
                    patterns = [
                        r'/lxc/(\d+)',           # /lxc/12345
                        r'/lxc\.payload\.(\d+)', # /lxc.payload.12345
                        r'/machine\.slice/lxc-(\d+)\.scope',  # systemd-machined
                        r'/(\d+)\.scope',        # Generic container scope
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, line)
                        if match:
                            return match.group(1)
        
        except Exception as e:
            logger.debug(f"Cgroup path detection failed: {e}")
        
        return None
    
    @classmethod
    def _detect_from_systemd_machined(cls) -> Optional[str]:
        """Detect container ID from systemd-machined"""
        try:
            # Check systemd machine ID
            if os.path.exists("/run/systemd/container"):
                with open("/run/systemd/container", "r") as f:
                    container_type = f.read().strip()
                    if container_type == "lxc":
                        # Try to get machine name
                        result = subprocess.run(
                            ["systemctl", "show", "--property=Id", "--value"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            machine_id = result.stdout.strip()
                            match = re.search(r'(\d+)', machine_id)
                            if match:
                                return match.group(1)
        
        except Exception as e:
            logger.debug(f"Systemd-machined detection failed: {e}")
        
        return None
    
    @classmethod
    def _detect_from_hostname(cls) -> Optional[str]:
        """Detect container ID from hostname pattern"""
        try:
            hostname = socket.gethostname()
            
            # Common LXC hostname patterns
            patterns = [
                r'^(\d+)$',              # Pure numeric hostname
                r'^lxc-(\d+)$',          # lxc-12345
                r'^ct-(\d+)$',           # ct-12345
                r'(\d{3,})$',            # Ends with 3+ digits
            ]
            
            for pattern in patterns:
                match = re.search(pattern, hostname)
                if match:
                    container_id = match.group(1)
                    # Validate it looks like a container ID (3+ digits)
                    if len(container_id) >= 3:
                        return container_id
        
        except Exception as e:
            logger.debug(f"Hostname detection failed: {e}")
        
        return None
    
    @classmethod
    def _detect_from_environment(cls) -> Optional[str]:
        """Detect container ID from environment variables"""
        try:
            # Check common LXC environment variables
            env_vars = [
                "LXC_NAME",
                "CONTAINER_ID", 
                "PROXMOX_VMID",
                "SYSTEMD_MACHINE_ID"
            ]
            
            for var in env_vars:
                value = os.environ.get(var)
                if value:
                    match = re.search(r'(\d+)', value)
                    if match:
                        return match.group(1)
        
        except Exception as e:
            logger.debug(f"Environment detection failed: {e}")
        
        return None
    
    @classmethod
    def _detect_resource_limits(cls, cgroup_version: CgroupVersion) -> Dict[str, Any]:
        """Detect container resource limits"""
        limits = {}
        
        try:
            if cgroup_version == CgroupVersion.V2:
                limits.update(cls._get_cgroup_v2_limits())
            elif cgroup_version == CgroupVersion.V1:
                limits.update(cls._get_cgroup_v1_limits())
        except Exception as e:
            logger.debug(f"Resource limit detection failed: {e}")
        
        return limits
    
    @classmethod
    def _get_cgroup_v2_limits(cls) -> Dict[str, Any]:
        """Get resource limits from cgroup v2"""
        limits = {}
        
        # Memory limits
        try:
            with open("/sys/fs/cgroup/memory.max", "r") as f:
                memory_max = f.read().strip()
                if memory_max != "max":
                    limits["memory_limit_bytes"] = int(memory_max)
        except (FileNotFoundError, ValueError):
            pass
        
        # CPU limits
        try:
            with open("/sys/fs/cgroup/cpu.max", "r") as f:
                cpu_max = f.read().strip()
                if cpu_max != "max":
                    parts = cpu_max.split()
                    if len(parts) == 2:
                        quota, period = parts
                        limits["cpu_quota"] = int(quota)
                        limits["cpu_period"] = int(period)
                        limits["cpu_limit_cores"] = int(quota) / int(period)
        except (FileNotFoundError, ValueError):
            pass
        
        return limits
    
    @classmethod
    def _get_cgroup_v1_limits(cls) -> Dict[str, Any]:
        """Get resource limits from cgroup v1"""
        limits = {}
        
        # Memory limits
        try:
            with open("/sys/fs/cgroup/memory/memory.limit_in_bytes", "r") as f:
                memory_limit = int(f.read().strip())
                # Check if it's a real limit (not the max value)
                if memory_limit < (1 << 63) - 1:
                    limits["memory_limit_bytes"] = memory_limit
        except (FileNotFoundError, ValueError):
            pass
        
        # CPU limits
        try:
            with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "r") as f:
                quota = int(f.read().strip())
            with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", "r") as f:
                period = int(f.read().strip())
            
            if quota > 0:
                limits["cpu_quota"] = quota
                limits["cpu_period"] = period
                limits["cpu_limit_cores"] = quota / period
        except (FileNotFoundError, ValueError):
            pass
        
        return limits


# Backward compatibility functions
def extract_container_id() -> Optional[str]:
    """Extract LXC container ID - backward compatibility function"""
    info = LXCDetector.get_container_info()
    return info.container_id


def get_container_info() -> LXCContainerInfo:
    """Get comprehensive container information"""
    return LXCDetector.get_container_info()


def is_lxc_container() -> bool:
    """Check if running in LXC container"""
    info = LXCDetector.get_container_info()
    return info.is_lxc_container


def get_cgroup_version() -> CgroupVersion:
    """Get cgroup version"""
    info = LXCDetector.get_container_info()
    return info.cgroup_version