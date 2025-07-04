"""Environment detection logic for LXC containers vs Proxmox hosts"""
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class EnvironmentType(Enum):
    """Environment types that can be detected"""
    LXC_CONTAINER = "lxc_container"
    PROXMOX_HOST = "proxmox_host"
    GENERIC_HOST = "generic_host"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    """Result of environment detection"""
    environment_type: EnvironmentType
    confidence: float  # 0.0 to 1.0
    detection_methods: List[str]
    metadata: Dict[str, Any]
    reason: str


class EnvironmentDetector:
    """Detect whether running in LXC container or Proxmox host"""
    
    def __init__(self):
        self._detection_cache: Optional[DetectionResult] = None
        self._force_environment: Optional[EnvironmentType] = None
    
    def detect(self, force_redetect: bool = False) -> DetectionResult:
        """Detect current environment with comprehensive checks"""
        if self._force_environment:
            return DetectionResult(
                environment_type=self._force_environment,
                confidence=1.0,
                detection_methods=["manual_override"],
                metadata={"forced": True},
                reason="Manual environment override"
            )
        
        if not force_redetect and self._detection_cache:
            return self._detection_cache
        
        # Run all detection methods
        detectors = [
            self._detect_lxc_container,
            self._detect_proxmox_host,
            self._detect_generic_host
        ]
        
        results = []
        for detector in detectors:
            try:
                result = detector()
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Detection method {detector.__name__} failed: {e}")
        
        # Select best result based on confidence
        if results:
            best_result = max(results, key=lambda r: r.confidence)
            self._detection_cache = best_result
            logger.info(f"Environment detected: {best_result.environment_type.value} "
                       f"(confidence: {best_result.confidence:.2f}) - {best_result.reason}")
            return best_result
        
        # Fallback to unknown
        fallback = DetectionResult(
            environment_type=EnvironmentType.UNKNOWN,
            confidence=0.0,
            detection_methods=["fallback"],
            metadata={},
            reason="No environment could be detected"
        )
        self._detection_cache = fallback
        logger.warning("Could not detect environment, using fallback")
        return fallback
    
    def force_environment(self, env_type: EnvironmentType) -> None:
        """Force a specific environment type (for testing/override)"""
        self._force_environment = env_type
        self._detection_cache = None
    
    def _detect_lxc_container(self) -> Optional[DetectionResult]:
        """Detect LXC container environment"""
        detection_methods = []
        metadata = {}
        confidence = 0.0
        
        # Check 1: Cgroup paths for container indicators
        if self._check_cgroup_container():
            detection_methods.append("cgroup_paths")
            confidence += 0.3
            metadata["cgroup_container"] = True
        
        # Check 2: Container-specific environment markers
        if self._check_container_env_markers():
            detection_methods.append("env_markers")
            confidence += 0.2
            metadata["env_markers"] = True
        
        # Check 3: Virtualized filesystem indicators
        if self._check_virtualized_filesystem():
            detection_methods.append("virtualized_fs")
            confidence += 0.2
            metadata["virtualized_fs"] = True
        
        # Check 4: Container resource limits
        limits = self._check_container_limits()
        if limits:
            detection_methods.append("resource_limits")
            confidence += 0.2
            metadata["resource_limits"] = limits
        
        # Check 5: PID namespace indicators
        if self._check_pid_namespace():
            detection_methods.append("pid_namespace")
            confidence += 0.1
            metadata["pid_namespace"] = True
        
        if confidence >= 0.5:
            return DetectionResult(
                environment_type=EnvironmentType.LXC_CONTAINER,
                confidence=min(confidence, 1.0),
                detection_methods=detection_methods,
                metadata=metadata,
                reason=f"LXC container detected via {', '.join(detection_methods)}"
            )
        
        return None
    
    def _detect_proxmox_host(self) -> Optional[DetectionResult]:
        """Detect Proxmox host environment"""
        detection_methods = []
        metadata = {}
        confidence = 0.0
        
        # Check 1: PVE directory structure
        if Path("/etc/pve").exists():
            detection_methods.append("pve_directory")
            confidence += 0.4
            metadata["pve_config"] = True
        
        # Check 2: PVE services
        pve_services = self._check_pve_services()
        if pve_services:
            detection_methods.append("pve_services")
            confidence += 0.3
            metadata["pve_services"] = pve_services
        
        # Check 3: PVE packages
        pve_packages = self._check_pve_packages()
        if pve_packages:
            detection_methods.append("pve_packages")
            confidence += 0.2
            metadata["pve_packages"] = pve_packages
        
        # Check 4: PVE cluster status
        cluster_info = self._check_pve_cluster()
        if cluster_info:
            detection_methods.append("pve_cluster")
            confidence += 0.1
            metadata["cluster_info"] = cluster_info
        
        if confidence >= 0.5:
            return DetectionResult(
                environment_type=EnvironmentType.PROXMOX_HOST,
                confidence=min(confidence, 1.0),
                detection_methods=detection_methods,
                metadata=metadata,
                reason=f"Proxmox host detected via {', '.join(detection_methods)}"
            )
        
        return None
    
    def _detect_generic_host(self) -> Optional[DetectionResult]:
        """Detect generic host environment (fallback)"""
        detection_methods = []
        metadata = {}
        confidence = 0.1  # Low confidence fallback
        
        # Check if we have root privileges and full system access
        if os.geteuid() == 0:
            detection_methods.append("root_privileges")
            confidence += 0.1
            metadata["root_access"] = True
        
        # Check for full /proc access
        if self._check_full_proc_access():
            detection_methods.append("full_proc_access")
            confidence += 0.1
            metadata["full_proc"] = True
        
        # Check for hardware access
        if self._check_hardware_access():
            detection_methods.append("hardware_access")
            confidence += 0.1
            metadata["hardware_access"] = True
        
        return DetectionResult(
            environment_type=EnvironmentType.GENERIC_HOST,
            confidence=confidence,
            detection_methods=detection_methods,
            metadata=metadata,
            reason="Generic host environment (fallback detection)"
        )
    
    def _check_cgroup_container(self) -> bool:
        """Check cgroup paths for container indicators"""
        try:
            # Check cgroup v1 and v2 paths
            cgroup_paths = ["/proc/self/cgroup", "/proc/1/cgroup"]
            
            for path in cgroup_paths:
                if Path(path).exists():
                    content = Path(path).read_text()
                    # Look for container-specific cgroup paths
                    container_indicators = [
                        "/lxc/",
                        "/docker/",
                        "/system.slice/",
                        "machine.slice"
                    ]
                    
                    for indicator in container_indicators:
                        if indicator in content:
                            return True
            
            return False
        except Exception:
            return False
    
    def _check_container_env_markers(self) -> bool:
        """Check for container-specific environment markers"""
        try:
            # Check for container-specific environment variables
            container_vars = ["container", "CONTAINER", "LXC_NAME"]
            for var in container_vars:
                if os.environ.get(var):
                    return True
            
            # Check for container-specific files
            container_files = [
                "/.dockerenv",
                "/run/systemd/container",
                "/proc/vz"
            ]
            
            for file_path in container_files:
                if Path(file_path).exists():
                    return True
            
            return False
        except Exception:
            return False
    
    def _check_virtualized_filesystem(self) -> bool:
        """Check for virtualized filesystem indicators"""
        try:
            # Check mount points for container-specific filesystems
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
            
            # Container-specific mount indicators
            container_mounts = [
                "overlay",
                "aufs",
                "tmpfs /dev/shm",
                "proc /proc/sys/fs/binfmt_misc"
            ]
            
            for mount in container_mounts:
                if mount in mounts:
                    return True
            
            return False
        except Exception:
            return False
    
    def _check_container_limits(self) -> Optional[Dict[str, Any]]:
        """Check for container resource limits"""
        try:
            limits = {}
            
            # Check memory limits
            cgroup_paths = [
                "/sys/fs/cgroup/memory/memory.limit_in_bytes",
                "/sys/fs/cgroup/memory.max"
            ]
            
            for path in cgroup_paths:
                if Path(path).exists():
                    try:
                        limit = int(Path(path).read_text().strip())
                        if limit < (1 << 63) - 1:  # Not max value
                            limits["memory_limit"] = limit
                            break
                    except (ValueError, OSError):
                        pass
            
            # Check CPU limits
            cpu_paths = [
                "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
                "/sys/fs/cgroup/cpu.max"
            ]
            
            for path in cpu_paths:
                if Path(path).exists():
                    try:
                        content = Path(path).read_text().strip()
                        if content != "-1" and content != "max":
                            limits["cpu_limit"] = content
                            break
                    except OSError:
                        pass
            
            return limits if limits else None
        except Exception:
            return None
    
    def _check_pid_namespace(self) -> bool:
        """Check for PID namespace indicators"""
        try:
            # Check if PID 1 is not init/systemd
            with open("/proc/1/comm", "r") as f:
                pid1_comm = f.read().strip()
            
            # In containers, PID 1 is often not init/systemd
            if pid1_comm not in ["init", "systemd", "kernel"]:
                return True
            
            return False
        except Exception:
            return False
    
    def _check_pve_services(self) -> Optional[List[str]]:
        """Check for running PVE services"""
        try:
            pve_services = [
                "pve-cluster",
                "pveproxy",
                "pvedaemon", 
                "pvestatd",
                "pve-firewall"
            ]
            
            running_services = []
            for service in pve_services:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip() == "active":
                        running_services.append(service)
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    pass
            
            return running_services if running_services else None
        except Exception:
            return None
    
    def _check_pve_packages(self) -> Optional[List[str]]:
        """Check for installed PVE packages"""
        try:
            pve_packages = [
                "proxmox-ve",
                "pve-manager",
                "pve-kernel",
                "pve-qemu-kvm"
            ]
            
            installed_packages = []
            for package in pve_packages:
                try:
                    result = subprocess.run(
                        ["dpkg", "-l", package],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        installed_packages.append(package)
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    pass
            
            return installed_packages if installed_packages else None
        except Exception:
            return None
    
    def _check_pve_cluster(self) -> Optional[Dict[str, Any]]:
        """Check PVE cluster status"""
        try:
            cluster_info = {}
            
            # Check cluster status
            try:
                result = subprocess.run(
                    ["pvecm", "status"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    cluster_info["cluster_active"] = True
                    cluster_info["cluster_status"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                cluster_info["cluster_active"] = False
            
            # Check node list
            try:
                result = subprocess.run(
                    ["pvecm", "nodes"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    cluster_info["nodes"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
            
            return cluster_info if cluster_info else None
        except Exception:
            return None
    
    def _check_full_proc_access(self) -> bool:
        """Check if we have full /proc access"""
        try:
            # Check if we can read system-wide /proc entries
            test_files = [
                "/proc/meminfo",
                "/proc/cpuinfo", 
                "/proc/loadavg",
                "/proc/stat"
            ]
            
            for file_path in test_files:
                if not Path(file_path).exists():
                    return False
                
                try:
                    Path(file_path).read_text()
                except (OSError, PermissionError):
                    return False
            
            return True
        except Exception:
            return False
    
    def _check_hardware_access(self) -> bool:
        """Check if we have hardware access"""
        try:
            # Check for hardware-specific files
            hardware_files = [
                "/sys/class/dmi/id/product_name",
                "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq",
                "/dev/mem"
            ]
            
            for file_path in hardware_files:
                if Path(file_path).exists():
                    return True
            
            return False
        except Exception:
            return False