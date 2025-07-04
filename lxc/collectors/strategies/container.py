"""Container collection strategy for LXC environments"""
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import CollectionStrategy, StrategyResult
from environment.capabilities import CollectionMethod

logger = logging.getLogger(__name__)


class ContainerStrategy(CollectionStrategy):
    """Collection strategy optimized for LXC containers"""
    
    def __init__(self):
        super().__init__(
            name="container",
            supported_methods=[
                CollectionMethod.CGROUP_V1,
                CollectionMethod.CGROUP_V2,
                CollectionMethod.CONTAINER_LIMITS,
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.NETWORK_NAMESPACES,
            ]
        )
        self._cgroup_version = self._detect_cgroup_version()
        self._cgroup_mount = self._find_cgroup_mount()
    
    def collect_memory(self) -> StrategyResult:
        """Collect memory metrics using cgroup or proc filesystem"""
        # Try cgroup first (more accurate for containers)
        if self._cgroup_version == 2:
            result = self._collect_memory_cgroup_v2()
            if result.is_success:
                return result
        
        if self._cgroup_version == 1:
            result = self._collect_memory_cgroup_v1()
            if result.is_success:
                return result
        
        # Fallback to proc filesystem
        return self._collect_memory_proc()
    
    def collect_cpu(self) -> StrategyResult:
        """Collect CPU metrics using cgroup or proc filesystem"""
        # Try cgroup first
        if self._cgroup_version == 2:
            result = self._collect_cpu_cgroup_v2()
            if result.is_success:
                return result
        
        if self._cgroup_version == 1:
            result = self._collect_cpu_cgroup_v1()
            if result.is_success:
                return result
        
        # Fallback to proc filesystem
        return self._collect_cpu_proc()
    
    def collect_disk(self) -> StrategyResult:
        """Collect disk metrics using proc filesystem"""
        # In containers, we primarily use proc filesystem for disk metrics
        return self._collect_disk_proc()
    
    def collect_network(self) -> StrategyResult:
        """Collect network metrics using proc filesystem"""
        # Use proc filesystem for network stats
        return self._collect_network_proc()
    
    def collect_process(self) -> StrategyResult:
        """Collect process metrics using proc filesystem"""
        # Use proc filesystem for process count
        return self._collect_process_proc()
    
    def _detect_cgroup_version(self) -> int:
        """Detect cgroup version (1 or 2)"""
        try:
            # Check for cgroup v2
            if Path("/sys/fs/cgroup/cgroup.controllers").exists():
                return 2
            
            # Check for cgroup v1
            if Path("/sys/fs/cgroup/memory").exists():
                return 1
            
            return 0
        except Exception:
            return 0
    
    def _find_cgroup_mount(self) -> Optional[str]:
        """Find cgroup mount point"""
        try:
            if self._cgroup_version == 2:
                return "/sys/fs/cgroup"
            elif self._cgroup_version == 1:
                return "/sys/fs/cgroup"
            return None
        except Exception:
            return None
    
    def _collect_memory_cgroup_v2(self) -> StrategyResult:
        """Collect memory metrics from cgroup v2"""
        try:
            data = {}
            errors = []
            
            # Memory current usage
            current = self._safe_read_int("/sys/fs/cgroup/memory.current")
            if current is not None:
                data["usage_bytes"] = current
            else:
                errors.append("Could not read memory.current")
            
            # Memory max limit
            max_limit = self._safe_read_file("/sys/fs/cgroup/memory.max")
            if max_limit and max_limit != "max":
                try:
                    data["limit_bytes"] = int(max_limit)
                except ValueError:
                    errors.append("Could not parse memory.max")
            
            # Memory statistics
            stat_data = self._parse_key_value_file("/sys/fs/cgroup/memory.stat")
            if stat_data:
                # Parse relevant stats
                for key, value in stat_data.items():
                    if key in ["cache", "rss", "swap", "mapped_file"]:
                        try:
                            data[f"{key}_bytes"] = int(value)
                        except ValueError:
                            errors.append(f"Could not parse {key} from memory.stat")
            
            if data:
                return self._create_success_result(data, CollectionMethod.CGROUP_V2)
            else:
                return self._create_failure_result(errors or ["No memory data available"])
        
        except Exception as e:
            return self._create_failure_result([f"cgroup v2 memory collection failed: {e}"])
    
    def _collect_memory_cgroup_v1(self) -> StrategyResult:
        """Collect memory metrics from cgroup v1"""
        try:
            data = {}
            errors = []
            
            # Memory usage
            usage = self._safe_read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            if usage is not None:
                data["usage_bytes"] = usage
            else:
                errors.append("Could not read memory.usage_in_bytes")
            
            # Memory limit
            limit = self._safe_read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            if limit is not None and limit < (1 << 63) - 1:
                data["limit_bytes"] = limit
            
            # Memory statistics
            stat_data = self._parse_key_value_file("/sys/fs/cgroup/memory/memory.stat")
            if stat_data:
                for key, value in stat_data.items():
                    if key in ["cache", "rss", "swap", "mapped_file"]:
                        try:
                            data[f"{key}_bytes"] = int(value)
                        except ValueError:
                            errors.append(f"Could not parse {key} from memory.stat")
            
            if data:
                return self._create_success_result(data, CollectionMethod.CGROUP_V1)
            else:
                return self._create_failure_result(errors or ["No memory data available"])
        
        except Exception as e:
            return self._create_failure_result([f"cgroup v1 memory collection failed: {e}"])
    
    def _collect_memory_proc(self) -> StrategyResult:
        """Collect memory metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read /proc/meminfo
            meminfo = self._parse_key_value_file("/proc/meminfo")
            if meminfo:
                # Parse memory values (in kB)
                for key, value in meminfo.items():
                    if key in ["MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached"]:
                        try:
                            # Remove 'kB' suffix and convert to bytes
                            kb_value = int(value.split()[0])
                            data[f"{key.lower()}_bytes"] = self._kb_to_bytes(kb_value)
                        except (ValueError, IndexError):
                            errors.append(f"Could not parse {key} from /proc/meminfo")
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No memory data available"])
        
        except Exception as e:
            return self._create_failure_result([f"proc filesystem memory collection failed: {e}"])
    
    def _collect_cpu_cgroup_v2(self) -> StrategyResult:
        """Collect CPU metrics from cgroup v2"""
        try:
            data = {}
            errors = []
            
            # CPU usage
            usage = self._safe_read_int("/sys/fs/cgroup/cpu.stat")
            if usage is not None:
                # Parse cpu.stat file
                stat_content = self._safe_read_file("/sys/fs/cgroup/cpu.stat")
                if stat_content:
                    for line in stat_content.split('\n'):
                        if line.startswith("usage_usec"):
                            try:
                                value = int(line.split()[1])
                                data["usage_microseconds"] = value
                                data["usage_seconds"] = value / 1_000_000
                            except (ValueError, IndexError):
                                errors.append("Could not parse usage_usec from cpu.stat")
            
            # CPU limits
            max_limit = self._safe_read_file("/sys/fs/cgroup/cpu.max")
            if max_limit and max_limit != "max":
                try:
                    quota, period = max_limit.split()
                    if quota != "max":
                        data["quota_microseconds"] = int(quota)
                        data["period_microseconds"] = int(period)
                except (ValueError, IndexError):
                    errors.append("Could not parse cpu.max")
            
            if data:
                return self._create_success_result(data, CollectionMethod.CGROUP_V2)
            else:
                return self._create_failure_result(errors or ["No CPU data available"])
        
        except Exception as e:
            return self._create_failure_result([f"cgroup v2 CPU collection failed: {e}"])
    
    def _collect_cpu_cgroup_v1(self) -> StrategyResult:
        """Collect CPU metrics from cgroup v1"""
        try:
            data = {}
            errors = []
            
            # CPU usage
            usage = self._safe_read_int("/sys/fs/cgroup/cpuacct/cpuacct.usage")
            if usage is not None:
                data["usage_nanoseconds"] = usage
                data["usage_seconds"] = usage / 1_000_000_000
            else:
                errors.append("Could not read cpuacct.usage")
            
            # CPU limits
            quota = self._safe_read_int("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
            period = self._safe_read_int("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
            
            if quota and quota != -1:
                data["quota_microseconds"] = quota
            if period:
                data["period_microseconds"] = period
            
            if data:
                return self._create_success_result(data, CollectionMethod.CGROUP_V1)
            else:
                return self._create_failure_result(errors or ["No CPU data available"])
        
        except Exception as e:
            return self._create_failure_result([f"cgroup v1 CPU collection failed: {e}"])
    
    def _collect_cpu_proc(self) -> StrategyResult:
        """Collect CPU metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read /proc/stat
            stat_content = self._safe_read_file("/proc/stat")
            if stat_content:
                for line in stat_content.split('\n'):
                    if line.startswith("cpu "):
                        try:
                            values = line.split()[1:]
                            data["user_time"] = int(values[0])
                            data["nice_time"] = int(values[1])
                            data["system_time"] = int(values[2])
                            data["idle_time"] = int(values[3])
                            data["total_time"] = sum(int(v) for v in values[:4])
                        except (ValueError, IndexError):
                            errors.append("Could not parse /proc/stat")
                        break
            
            # Read load average
            loadavg = self._safe_read_file("/proc/loadavg")
            if loadavg:
                try:
                    values = loadavg.split()
                    data["load1"] = float(values[0])
                    data["load5"] = float(values[1])
                    data["load15"] = float(values[2])
                except (ValueError, IndexError):
                    errors.append("Could not parse /proc/loadavg")
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No CPU data available"])
        
        except Exception as e:
            return self._create_failure_result([f"proc filesystem CPU collection failed: {e}"])
    
    def _collect_disk_proc(self) -> StrategyResult:
        """Collect disk metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read /proc/mounts to get mounted filesystems
            mounts_content = self._safe_read_file("/proc/mounts")
            if mounts_content:
                filesystems = []
                for line in mounts_content.split('\n'):
                    if line.strip():
                        try:
                            parts = line.split()
                            if len(parts) >= 3:
                                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                                # Skip special filesystems
                                if not mountpoint.startswith(('/proc', '/sys', '/dev', '/run')):
                                    filesystems.append({
                                        "device": device,
                                        "mountpoint": mountpoint,
                                        "fstype": fstype
                                    })
                        except (ValueError, IndexError):
                            continue
                
                data["filesystems"] = filesystems
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No disk data available"])
        
        except Exception as e:
            return self._create_failure_result([f"proc filesystem disk collection failed: {e}"])
    
    def _collect_network_proc(self) -> StrategyResult:
        """Collect network metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Read /proc/net/dev
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
                            
                            if len(stats) >= 16:
                                interfaces[interface] = {
                                    "rx_bytes": int(stats[0]),
                                    "rx_packets": int(stats[1]),
                                    "rx_errs": int(stats[2]),
                                    "rx_drop": int(stats[3]),
                                    "tx_bytes": int(stats[8]),
                                    "tx_packets": int(stats[9]),
                                    "tx_errs": int(stats[10]),
                                    "tx_drop": int(stats[11])
                                }
                        except (ValueError, IndexError):
                            errors.append(f"Could not parse interface {interface}")
                
                data["interfaces"] = interfaces
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No network data available"])
        
        except Exception as e:
            return self._create_failure_result([f"proc filesystem network collection failed: {e}"])
    
    def _collect_process_proc(self) -> StrategyResult:
        """Collect process metrics from proc filesystem"""
        try:
            data = {}
            errors = []
            
            # Count processes in /proc
            process_count = 0
            try:
                proc_path = Path("/proc")
                for item in proc_path.iterdir():
                    if item.is_dir() and item.name.isdigit():
                        process_count += 1
                
                data["process_count"] = process_count
            except Exception as e:
                errors.append(f"Could not count processes: {e}")
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROC_FILESYSTEM)
            else:
                return self._create_failure_result(errors or ["No process data available"])
        
        except Exception as e:
            return self._create_failure_result([f"proc filesystem process collection failed: {e}"])