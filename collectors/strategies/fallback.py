"""Fallback collection strategy for unknown or limited environments"""
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import CollectionStrategy, StrategyResult
from environment.capabilities import CollectionMethod

logger = logging.getLogger(__name__)


class FallbackStrategy(CollectionStrategy):
    """Fallback strategy using only basic, universally available methods"""
    
    def __init__(self):
        super().__init__(
            name="fallback",
            supported_methods=[
                CollectionMethod.PROC_FILESYSTEM,
            ]
        )
    
    def collect_memory(self) -> StrategyResult:
        """Collect basic memory metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read basic memory info from /proc/meminfo
            meminfo = self._parse_key_value_file("/proc/meminfo")
            if meminfo:
                # Only extract the most essential memory fields
                essential_fields = ["MemTotal", "MemFree", "MemAvailable"]
                
                for field in essential_fields:
                    if field in meminfo:
                        try:
                            # Remove 'kB' suffix and convert to bytes
                            kb_value = int(meminfo[field].split()[0])
                            data[f"{field.lower()}_bytes"] = self._kb_to_bytes(kb_value)
                        except (ValueError, IndexError):
                            errors.append(f"Could not parse {field} from /proc/meminfo")
            
            # Calculate used memory if possible
            if "memtotal_bytes" in data and "memfree_bytes" in data:
                data["memused_bytes"] = data["memtotal_bytes"] - data["memfree_bytes"]
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No memory data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Fallback memory collection failed: {e}"])
    
    def collect_cpu(self) -> StrategyResult:
        """Collect basic CPU metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read basic CPU info from /proc/stat
            stat_content = self._safe_read_file("/proc/stat")
            if stat_content:
                for line in stat_content.split('\n'):
                    if line.startswith("cpu "):
                        try:
                            values = line.split()[1:]
                            # Only extract basic fields to minimize parse errors
                            if len(values) >= 4:
                                data["user_time"] = int(values[0])
                                data["system_time"] = int(values[2])
                                data["idle_time"] = int(values[3])
                                data["total_time"] = sum(int(v) for v in values[:4])
                        except (ValueError, IndexError):
                            errors.append("Could not parse basic CPU stats from /proc/stat")
                        break
            
            # Read load average - this is usually very reliable
            loadavg = self._safe_read_file("/proc/loadavg")
            if loadavg:
                try:
                    values = loadavg.split()
                    data["load1"] = float(values[0])
                    data["load5"] = float(values[1])
                    data["load15"] = float(values[2])
                except (ValueError, IndexError):
                    errors.append("Could not parse /proc/loadavg")
            
            # Try to count CPU cores from /proc/cpuinfo
            cpuinfo_content = self._safe_read_file("/proc/cpuinfo")
            if cpuinfo_content:
                cpu_count = 0
                for line in cpuinfo_content.split('\n'):
                    if line.startswith("processor"):
                        cpu_count += 1
                
                if cpu_count > 0:
                    data["cpu_count"] = cpu_count
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No CPU data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Fallback CPU collection failed: {e}"])
    
    def collect_filesystem(self) -> StrategyResult:
        """Collect basic filesystem metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read basic mount information
            mounts_content = self._safe_read_file("/proc/mounts")
            if mounts_content:
                filesystems = []
                for line in mounts_content.split('\n'):
                    if line.strip():
                        try:
                            parts = line.split()
                            if len(parts) >= 3:
                                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                                # Only include basic, real filesystems
                                if (mountpoint in ["/", "/home", "/var", "/tmp"] or 
                                    fstype in ["ext4", "ext3", "xfs", "btrfs", "zfs"]):
                                    filesystems.append({
                                        "device": device,
                                        "mountpoint": mountpoint,
                                        "fstype": fstype
                                    })
                        except (ValueError, IndexError):
                            continue
                
                if filesystems:
                    data["filesystems"] = filesystems
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No filesystem data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Fallback filesystem collection failed: {e}"])
    
    def collect_network(self) -> StrategyResult:
        """Collect basic network metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read basic network interface info
            netdev_content = self._safe_read_file("/proc/net/dev")
            if netdev_content:
                interfaces = {}
                lines = netdev_content.split('\n')
                
                for line in lines[2:]:  # Skip header lines
                    if ':' in line:
                        try:
                            interface, stats = line.split(':', 1)
                            interface = interface.strip()
                            stats = stats.split()
                            
                            # Only extract essential network stats to avoid parse errors
                            if len(stats) >= 10 and interface not in ["lo"]:  # Skip loopback
                                interfaces[interface] = {
                                    "rx_bytes": int(stats[0]),
                                    "rx_packets": int(stats[1]),
                                    "tx_bytes": int(stats[8]),
                                    "tx_packets": int(stats[9])
                                }
                        except (ValueError, IndexError):
                            # Skip interfaces we can't parse
                            continue
                
                if interfaces:
                    data["interfaces"] = interfaces
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No network data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Fallback network collection failed: {e}"])
    
    def collect_process(self) -> StrategyResult:
        """Collect basic process metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Count processes - this is the most basic metric we can get
            process_count = 0
            try:
                proc_path = Path("/proc")
                for item in proc_path.iterdir():
                    if item.is_dir() and item.name.isdigit():
                        process_count += 1
                
                if process_count > 0:
                    data["process_count"] = process_count
            except Exception as e:
                errors.append(f"Could not count processes: {e}")
            
            # Try to get running/blocked process counts from /proc/stat
            stat_content = self._safe_read_file("/proc/stat")
            if stat_content:
                for line in stat_content.split('\n'):
                    if line.startswith("procs_running"):
                        try:
                            data["processes_running"] = int(line.split()[1])
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("procs_blocked"):
                        try:
                            data["processes_blocked"] = int(line.split()[1])
                        except (ValueError, IndexError):
                            pass
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No process data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Fallback process collection failed: {e}"])
    
    def collect_zfs(self) -> StrategyResult:
        """ZFS collection not available in fallback strategy"""
        return self._create_not_supported_result("ZFS not available in fallback environment")
    
    def collect_sensors_cpu(self) -> StrategyResult:
        """CPU sensors collection not available in fallback strategy"""
        return self._create_not_supported_result("CPU sensors not available in fallback environment")
    
    def collect_sensors_nvme(self) -> StrategyResult:
        """NVMe sensors collection not available in fallback strategy"""
        return self._create_not_supported_result("NVMe sensors not available in fallback environment")