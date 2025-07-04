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
        """Get collectors based on environment and available hardware/software"""
        collectors = ["memory", "cpu", "filesystem", "network", "process"]  # Always available
        
        if self.is_host:
            # Check for ZFS availability
            if self._has_zfs():
                collectors.append("zfs")
                logger.info("ZFS detected, enabling zfs collector")
            else:
                logger.info("ZFS not detected, skipping zfs collector")
            
            # Check for CPU temperature sensors
            if self._has_cpu_sensors():
                collectors.append("sensors_cpu")
                logger.info("CPU sensors detected, enabling sensors_cpu collector")
            else:
                logger.info("CPU sensors not detected, skipping sensors_cpu collector")
            
            # Check for NVMe/disk temperature capability
            if self._has_nvme_sensors():
                collectors.append("sensors_nvme")
                logger.info("NVMe/disk sensors detected, enabling sensors_nvme collector")
            else:
                logger.info("NVMe/disk sensors not detected, skipping sensors_nvme collector")
        
        logger.info(f"Auto-detected collectors for {self.environment_type.value}: {collectors}")
        return collectors
    
    def get_collection_interval(self) -> int:
        """Get recommended collection interval for the environment"""
        return 30  # Standard interval for all environments
    
    def _has_zfs(self) -> bool:
        """Check if ZFS pools are available"""
        try:
            import subprocess
            
            # Check if zpool command exists
            result = subprocess.run(
                ["which", "zpool"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("zpool command not found")
                return False
            
            # Check if there are actual pools
            result = subprocess.run(
                ["zpool", "list"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.debug("zpool list failed or no pools")
                return False
            
            # Parse output to see if there are pools (more than just header)
            lines = result.stdout.strip().split('\n')
            has_pools = len(lines) > 1 and not any('no pools available' in line.lower() for line in lines)
            logger.debug(f"ZFS pools detected: {has_pools}")
            return has_pools
            
        except Exception as e:
            logger.debug(f"ZFS detection failed: {e}")
            return False
    
    def _has_cpu_sensors(self) -> bool:
        """Check if CPU temperature sensors are available"""
        try:
            import subprocess
            
            # Check if sensors command exists
            result = subprocess.run(
                ["which", "sensors"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("sensors command not found")
                return False
            
            # Test if sensors actually work and find temperature data
            result = subprocess.run(
                ["sensors", "-A"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.debug("sensors command failed")
                return False
            
            # Check if output contains temperature readings
            has_temps = "°C" in result.stdout or "temp" in result.stdout.lower()
            logger.debug(f"CPU temperature sensors detected: {has_temps}")
            return has_temps
            
        except Exception as e:
            logger.debug(f"CPU sensors detection failed: {e}")
            return False
    
    def _has_nvme_sensors(self) -> bool:
        """Check if NVMe/disk temperature monitoring is available"""
        try:
            import subprocess
            from pathlib import Path
            
            # Check if smartctl is available
            result = subprocess.run(
                ["which", "smartctl"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("smartctl command not found")
                return False
            
            # Check if there are any NVMe or SATA drives
            dev_path = Path("/dev")
            # Match NVMe character devices (nvme0, nvme1, etc.) for temperature access
            nvme_drives = list(dev_path.glob("nvme[0-9]"))
            sata_drives = list(dev_path.glob("sd[a-z]"))
            
            has_drives = bool(nvme_drives or sata_drives)
            if has_drives:
                logger.debug(f"Storage drives detected: NVMe={len(nvme_drives)}, SATA={len(sata_drives)}")
            else:
                logger.debug("No compatible storage drives found")
            
            return has_drives
            
        except Exception as e:
            logger.debug(f"NVMe/disk sensors detection failed: {e}")
            return False
    
    def _debug_zfs_detection(self) -> dict:
        """Debug ZFS detection with detailed results"""
        debug_info = {"steps": [], "final_result": False}
        
        try:
            import subprocess
            
            # Step 1: Check if zpool command exists
            result = subprocess.run(
                ["which", "zpool"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            debug_info["steps"].append({
                "step": "zpool_command_check",
                "command": "which zpool",
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            })
            
            if result.returncode != 0:
                debug_info["final_result"] = False
                return debug_info
            
            # Step 2: Check if there are actual pools
            result = subprocess.run(
                ["zpool", "list"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            debug_info["steps"].append({
                "step": "zpool_list_check", 
                "command": "zpool list",
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            })
            
            if result.returncode != 0:
                debug_info["final_result"] = False
                return debug_info
            
            # Step 3: Parse output
            lines = result.stdout.strip().split('\n')
            has_pools = len(lines) > 1 and not any('no pools available' in line.lower() for line in lines)
            debug_info["steps"].append({
                "step": "parse_pools",
                "line_count": len(lines),
                "lines": lines,
                "has_pools": has_pools
            })
            
            # Step 4: Test actual ZFS data collection
            if has_pools:
                zfs_test_results = []
                try:
                    # Test zpool list with parseable output
                    result = subprocess.run(
                        ["zpool", "list", "-H", "-p"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    pools_data = []
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                try:
                                    parts = line.split('\t')
                                    if len(parts) >= 10:
                                        pool_name = parts[0]
                                        size_bytes = int(parts[1])
                                        alloc_bytes = int(parts[2])
                                        free_bytes = int(parts[3])
                                        capacity_percent = float(parts[7])
                                        health = parts[9]
                                        
                                        pools_data.append({
                                            "name": pool_name,
                                            "size_bytes": size_bytes,
                                            "allocated_bytes": alloc_bytes,
                                            "free_bytes": free_bytes,
                                            "capacity_percent": capacity_percent,
                                            "health": health
                                        })
                                except (ValueError, IndexError):
                                    continue
                    
                    zfs_test_results.append({
                        "command": "zpool list -H -p",
                        "returncode": result.returncode,
                        "success": result.returncode == 0,
                        "pools_found": len(pools_data),
                        "pools_data": pools_data,
                        "stderr": result.stderr.strip()
                    })
                    
                except Exception as e:
                    zfs_test_results.append({
                        "command": "zpool list -H -p",
                        "error": str(e),
                        "success": False
                    })
                
                debug_info["steps"].append({
                    "step": "zfs_data_collection_test",
                    "results": zfs_test_results
                })
            
            debug_info["final_result"] = has_pools
            
        except Exception as e:
            debug_info["steps"].append({
                "step": "exception",
                "error": str(e)
            })
            debug_info["final_result"] = False
        
        return debug_info
    
    def _debug_cpu_sensors_detection(self) -> dict:
        """Debug CPU sensors detection with detailed results"""
        debug_info = {"steps": [], "final_result": False}
        
        try:
            import subprocess
            
            # Step 1: Check if sensors command exists
            result = subprocess.run(
                ["which", "sensors"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            debug_info["steps"].append({
                "step": "sensors_command_check",
                "command": "which sensors",
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            })
            
            if result.returncode != 0:
                debug_info["final_result"] = False
                return debug_info
            
            # Step 2: Test sensors output
            result = subprocess.run(
                ["sensors", "-A"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            debug_info["steps"].append({
                "step": "sensors_output_check",
                "command": "sensors -A",
                "returncode": result.returncode,
                "stdout": result.stdout.strip()[:1000],  # Limit output size
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            })
            
            if result.returncode != 0:
                debug_info["final_result"] = False
                return debug_info
            
            # Step 3: Check for temperature data
            has_temps = "°C" in result.stdout or "temp" in result.stdout.lower()
            debug_info["steps"].append({
                "step": "temperature_check",
                "has_celsius": "°C" in result.stdout,
                "has_temp_keyword": "temp" in result.stdout.lower(),
                "has_temperatures": has_temps
            })
            
            debug_info["final_result"] = has_temps
            
        except Exception as e:
            debug_info["steps"].append({
                "step": "exception",
                "error": str(e)
            })
            debug_info["final_result"] = False
        
        return debug_info
    
    def _debug_nvme_sensors_detection(self) -> dict:
        """Debug NVMe sensors detection with detailed results"""
        debug_info = {"steps": [], "final_result": False}
        
        try:
            import subprocess
            from pathlib import Path
            
            # Step 1: Check if smartctl is available
            result = subprocess.run(
                ["which", "smartctl"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            debug_info["steps"].append({
                "step": "smartctl_command_check",
                "command": "which smartctl",
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "success": result.returncode == 0
            })
            
            if result.returncode != 0:
                debug_info["final_result"] = False
                return debug_info
            
            # Step 2: Check for drives
            dev_path = Path("/dev")
            # Match NVMe character devices (nvme0, nvme1, etc.) for temperature access
            nvme_drives = list(dev_path.glob("nvme[0-9]"))
            sata_drives = list(dev_path.glob("sd[a-z]"))
            
            debug_info["steps"].append({
                "step": "drive_detection",
                "nvme_drives": [str(d) for d in nvme_drives],
                "sata_drives": [str(d) for d in sata_drives],
                "total_drives": len(nvme_drives) + len(sata_drives)
            })
            
            # Step 3: Test actual temperature collection from first few drives
            temp_test_results = []
            test_drives = (nvme_drives + sata_drives)[:3]  # Test first 3 drives max
            
            for drive in test_drives:
                try:
                    result = subprocess.run(
                        ["smartctl", "-A", "-j", str(drive)],
                        capture_output=True,
                        text=True,
                        timeout=15
                    )
                    
                    temp_found = False
                    temp_value = None
                    
                    if result.returncode in [0, 4]:  # 0 = success, 4 = some SMART errors but data available
                        try:
                            import json
                            smart_data = json.loads(result.stdout)
                            
                            # Try to extract temperature
                            ata_smart_attrs = smart_data.get("ata_smart_attributes", {}).get("table", [])
                            for attr in ata_smart_attrs:
                                if attr.get("name") in ["Temperature_Celsius", "Airflow_Temperature_Cel"]:
                                    temp_value = attr.get("raw", {}).get("value", 0)
                                    temp_found = True
                                    break
                            
                            # For NVMe disks, check different location
                            if not temp_found:
                                nvme_smart = smart_data.get("nvme_smart_health_information_log", {})
                                if "temperature" in nvme_smart:
                                    temp_value = nvme_smart["temperature"]
                                    temp_found = True
                                
                                # Debug: show what we actually found
                                debug_info[f"drive_{drive}_nvme_data"] = {
                                    "has_nvme_log": "nvme_smart_health_information_log" in smart_data,
                                    "nvme_keys": list(nvme_smart.keys()) if nvme_smart else [],
                                    "temperature_in_log": "temperature" in nvme_smart if nvme_smart else False,
                                    "temp_value": nvme_smart.get("temperature") if nvme_smart else None
                                }
                            
                        except json.JSONDecodeError:
                            pass  # Will try text parsing
                    
                    temp_test_results.append({
                        "drive": str(drive),
                        "command": f"smartctl -A -j {drive}",
                        "returncode": result.returncode,
                        "success": result.returncode in [0, 4],
                        "temperature_found": temp_found,
                        "temperature_celsius": temp_value,
                        "stdout_length": len(result.stdout),
                        "stderr": result.stderr.strip()[:200]  # Limit stderr
                    })
                    
                except Exception as e:
                    temp_test_results.append({
                        "drive": str(drive),
                        "command": f"smartctl -A -j {drive}",
                        "error": str(e),
                        "success": False
                    })
            
            debug_info["steps"].append({
                "step": "temperature_collection_test",
                "tested_drives": len(temp_test_results),
                "results": temp_test_results
            })
            
            has_drives = bool(nvme_drives or sata_drives)
            has_temp_data = any(r.get("temperature_found", False) for r in temp_test_results)
            debug_info["final_result"] = has_drives and (has_temp_data or len(temp_test_results) == 0)
            
        except Exception as e:
            debug_info["steps"].append({
                "step": "exception", 
                "error": str(e)
            })
            debug_info["final_result"] = False
        
        return debug_info


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