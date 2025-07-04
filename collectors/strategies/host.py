"""Host collection strategy for Proxmox and generic hosts"""
import logging
import subprocess
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import CollectionStrategy, StrategyResult
from environment.capabilities import CollectionMethod

logger = logging.getLogger(__name__)


class HostStrategy(CollectionStrategy):
    """Collection strategy optimized for host environments"""
    
    def __init__(self):
        super().__init__(
            name="host",
            supported_methods=[
                CollectionMethod.HARDWARE_ACCESS,
                CollectionMethod.PROC_FILESYSTEM,
                CollectionMethod.SYSTEMD_SERVICES,
                CollectionMethod.FILESYSTEM_FULL,
                CollectionMethod.PROCESS_TREE_FULL,
                CollectionMethod.PROXMOX_API,
                CollectionMethod.LXC_COMMANDS,
            ]
        )
    
    def collect_memory(self) -> StrategyResult:
        """Collect memory metrics with full host access"""
        return self._collect_memory_full()
    
    def collect_cpu(self) -> StrategyResult:
        """Collect CPU metrics with hardware access"""
        return self._collect_cpu_full()
    
    def collect_disk(self) -> StrategyResult:
        """Collect disk metrics with full filesystem access"""
        return self._collect_disk_full()
    
    def collect_network(self) -> StrategyResult:
        """Collect network metrics with full host access"""
        return self._collect_network_full()
    
    def collect_process(self) -> StrategyResult:
        """Collect process metrics with full system access"""
        return self._collect_process_full()
    
    def collect_proxmox_system(self) -> StrategyResult:
        """Collect Proxmox-specific system metrics"""
        return self._collect_proxmox_system()
    
    def collect_container_inventory(self) -> StrategyResult:
        """Collect inventory of containers on the host"""
        return self._collect_container_inventory()
    
    def _collect_memory_full(self) -> StrategyResult:
        """Collect comprehensive memory metrics"""
        try:
            data = {}
            errors = []
            
            # Read /proc/meminfo
            meminfo = self._parse_key_value_file("/proc/meminfo")
            if meminfo:
                # Parse all memory values (in kB)
                memory_fields = [
                    "MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
                    "SwapCached", "SwapTotal", "SwapFree", "Dirty", "Writeback",
                    "AnonPages", "Mapped", "Shmem", "Slab", "SReclaimable",
                    "SUnreclaim", "PageTables", "NFS_Unstable", "Bounce",
                    "WritebackTmp", "CommitLimit", "Committed_AS", "VmallocTotal",
                    "VmallocUsed", "VmallocChunk", "HugePages_Total", "HugePages_Free"
                ]
                
                for field in memory_fields:
                    if field in meminfo:
                        try:
                            # Remove 'kB' suffix and convert to bytes
                            kb_value = int(meminfo[field].split()[0])
                            data[f"{field.lower()}_bytes"] = self._kb_to_bytes(kb_value)
                        except (ValueError, IndexError):
                            errors.append(f"Could not parse {field} from /proc/meminfo")
            
            # Add calculated fields
            if "memtotal_bytes" in data and "memfree_bytes" in data:
                data["memused_bytes"] = data["memtotal_bytes"] - data["memfree_bytes"]
            
            if "swaptotal_bytes" in data and "swapfree_bytes" in data:
                data["swapused_bytes"] = data["swaptotal_bytes"] - data["swapfree_bytes"]
            
            # Read /proc/vmstat for additional VM statistics
            vmstat = self._parse_key_value_file("/proc/vmstat")
            if vmstat:
                vm_fields = [
                    "pgfault", "pgmajfault", "pgpgin", "pgpgout",
                    "pswpin", "pswpout", "pgalloc_dma", "pgalloc_normal"
                ]
                
                for field in vm_fields:
                    if field in vmstat:
                        try:
                            data[f"vm_{field}"] = int(vmstat[field])
                        except ValueError:
                            errors.append(f"Could not parse {field} from /proc/vmstat")
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No memory data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Full memory collection failed: {e}"])
    
    def _collect_cpu_full(self) -> StrategyResult:
        """Collect comprehensive CPU metrics"""
        try:
            data = {}
            errors = []
            
            # Read /proc/stat for CPU times
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
                            data["iowait_time"] = int(values[4])
                            data["irq_time"] = int(values[5])
                            data["softirq_time"] = int(values[6])
                            data["steal_time"] = int(values[7]) if len(values) > 7 else 0
                            data["guest_time"] = int(values[8]) if len(values) > 8 else 0
                            data["total_time"] = sum(int(v) for v in values[:9])
                        except (ValueError, IndexError):
                            errors.append("Could not parse /proc/stat")
                        break
            
            # Read /proc/cpuinfo for CPU details
            cpuinfo_content = self._safe_read_file("/proc/cpuinfo")
            if cpuinfo_content:
                cpu_count = 0
                for line in cpuinfo_content.split('\n'):
                    if line.startswith("processor"):
                        cpu_count += 1
                
                data["cpu_count"] = cpu_count
            
            # Read load average
            loadavg = self._safe_read_file("/proc/loadavg")
            if loadavg:
                try:
                    values = loadavg.split()
                    data["load1"] = float(values[0])
                    data["load5"] = float(values[1])
                    data["load15"] = float(values[2])
                    data["running_processes"] = int(values[3].split('/')[0])
                    data["total_processes"] = int(values[3].split('/')[1])
                except (ValueError, IndexError):
                    errors.append("Could not parse /proc/loadavg")
            
            # Try to get CPU frequency information
            try:
                cpu_freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq")
                if cpu_freq_path.exists():
                    max_freq = self._safe_read_int(cpu_freq_path / "cpuinfo_max_freq")
                    min_freq = self._safe_read_int(cpu_freq_path / "cpuinfo_min_freq")
                    cur_freq = self._safe_read_int(cpu_freq_path / "scaling_cur_freq")
                    
                    if max_freq:
                        data["max_frequency_khz"] = max_freq
                    if min_freq:
                        data["min_frequency_khz"] = min_freq
                    if cur_freq:
                        data["current_frequency_khz"] = cur_freq
            except Exception:
                pass  # CPU frequency is optional
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No CPU data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Full CPU collection failed: {e}"])
    
    def _collect_disk_full(self) -> StrategyResult:
        """Collect comprehensive disk metrics"""
        try:
            data = {}
            errors = []
            
            # Read /proc/mounts for all mounted filesystems
            mounts_content = self._safe_read_file("/proc/mounts")
            if mounts_content:
                filesystems = []
                for line in mounts_content.split('\n'):
                    if line.strip():
                        try:
                            parts = line.split()
                            if len(parts) >= 3:
                                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                                # Include more filesystem types for host monitoring
                                if fstype not in ["tmpfs", "devtmpfs", "proc", "sysfs", "devpts", "cgroup", "cgroup2"]:
                                    filesystems.append({
                                        "device": device,
                                        "mountpoint": mountpoint,
                                        "fstype": fstype
                                    })
                        except (ValueError, IndexError):
                            continue
                
                data["filesystems"] = filesystems
            
            # Read /proc/diskstats for disk I/O statistics
            diskstats_content = self._safe_read_file("/proc/diskstats")
            if diskstats_content:
                disk_stats = {}
                for line in diskstats_content.split('\n'):
                    if line.strip():
                        try:
                            parts = line.split()
                            if len(parts) >= 14:
                                device_name = parts[2]
                                disk_stats[device_name] = {
                                    "reads_completed": int(parts[3]),
                                    "reads_merged": int(parts[4]),
                                    "sectors_read": int(parts[5]),
                                    "read_time_ms": int(parts[6]),
                                    "writes_completed": int(parts[7]),
                                    "writes_merged": int(parts[8]),
                                    "sectors_written": int(parts[9]),
                                    "write_time_ms": int(parts[10]),
                                    "io_in_progress": int(parts[11]),
                                    "io_time_ms": int(parts[12]),
                                    "weighted_io_time_ms": int(parts[13])
                                }
                        except (ValueError, IndexError):
                            continue
                
                data["disk_stats"] = disk_stats
            
            if data:
                return self._create_success_result(data, CollectionMethod.FILESYSTEM_FULL)
            else:
                return self._create_failure_result(errors or ["No disk data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Full disk collection failed: {e}"])
    
    def _collect_network_full(self) -> StrategyResult:
        """Collect comprehensive network metrics"""
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
                                    "rx_fifo": int(stats[4]),
                                    "rx_frame": int(stats[5]),
                                    "rx_compressed": int(stats[6]),
                                    "rx_multicast": int(stats[7]),
                                    "tx_bytes": int(stats[8]),
                                    "tx_packets": int(stats[9]),
                                    "tx_errs": int(stats[10]),
                                    "tx_drop": int(stats[11]),
                                    "tx_fifo": int(stats[12]),
                                    "tx_colls": int(stats[13]),
                                    "tx_carrier": int(stats[14]),
                                    "tx_compressed": int(stats[15])
                                }
                        except (ValueError, IndexError):
                            errors.append(f"Could not parse interface {interface}")
                
                data["interfaces"] = interfaces
            
            # Read additional network statistics
            netstat_files = [
                "/proc/net/netstat",
                "/proc/net/snmp",
                "/proc/net/sockstat"
            ]
            
            for file_path in netstat_files:
                content = self._safe_read_file(file_path)
                if content:
                    # Parse network statistics (simplified)
                    data[f"netstat_{Path(file_path).name}"] = content
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No network data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Full network collection failed: {e}"])
    
    def _collect_process_full(self) -> StrategyResult:
        """Collect comprehensive process metrics"""
        try:
            data = {}
            errors = []
            
            # Count processes in /proc
            process_count = 0
            zombie_count = 0
            
            try:
                proc_path = Path("/proc")
                for item in proc_path.iterdir():
                    if item.is_dir() and item.name.isdigit():
                        process_count += 1
                        
                        # Check for zombie processes
                        try:
                            stat_file = item / "stat"
                            if stat_file.exists():
                                stat_content = stat_file.read_text()
                                if " Z " in stat_content:  # Zombie state
                                    zombie_count += 1
                        except Exception:
                            pass
                
                data["process_count"] = process_count
                data["zombie_count"] = zombie_count
            except Exception as e:
                errors.append(f"Could not count processes: {e}")
            
            # Read /proc/stat for process statistics
            stat_content = self._safe_read_file("/proc/stat")
            if stat_content:
                for line in stat_content.split('\n'):
                    if line.startswith("processes"):
                        try:
                            data["processes_created"] = int(line.split()[1])
                        except (ValueError, IndexError):
                            errors.append("Could not parse processes from /proc/stat")
                    elif line.startswith("procs_running"):
                        try:
                            data["processes_running"] = int(line.split()[1])
                        except (ValueError, IndexError):
                            errors.append("Could not parse procs_running from /proc/stat")
                    elif line.startswith("procs_blocked"):
                        try:
                            data["processes_blocked"] = int(line.split()[1])
                        except (ValueError, IndexError):
                            errors.append("Could not parse procs_blocked from /proc/stat")
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROCESS_TREE_FULL)
            else:
                return self._create_failure_result(errors or ["No process data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Full process collection failed: {e}"])
    
    def _collect_proxmox_system(self) -> StrategyResult:
        """Collect Proxmox-specific system metrics"""
        try:
            data = {}
            errors = []
            
            # Check if we're on a Proxmox system
            if not Path("/etc/pve").exists():
                return self._create_not_supported_result("Not a Proxmox system")
            
            # Get PVE version
            try:
                result = subprocess.run(
                    ["pveversion", "--verbose"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    data["pve_version"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                errors.append(f"Could not get PVE version: {e}")
            
            # Get cluster status
            try:
                result = subprocess.run(
                    ["pvecm", "status"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    data["cluster_status"] = result.stdout.strip()
                else:
                    data["cluster_status"] = "standalone"
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                errors.append(f"Could not get cluster status: {e}")
            
            # Get node status
            try:
                result = subprocess.run(
                    ["pvesh", "get", "/nodes/localhost/status"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    data["node_status"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                errors.append(f"Could not get node status: {e}")
            
            if data:
                return self._create_success_result(data, CollectionMethod.PROXMOX_API)
            else:
                return self._create_failure_result(errors or ["No Proxmox data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Proxmox system collection failed: {e}"])
    
    def _collect_container_inventory(self) -> StrategyResult:
        """Collect inventory of LXC containers"""
        try:
            data = {}
            errors = []
            
            # Get LXC container list
            try:
                result = subprocess.run(
                    ["pct", "list"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode == 0:
                    containers = []
                    lines = result.stdout.strip().split('\n')
                    
                    # Skip header line
                    for line in lines[1:]:
                        if line.strip():
                            try:
                                parts = line.split()
                                if len(parts) >= 3:
                                    container_id = parts[0]
                                    status = parts[1]
                                    name = parts[2] if len(parts) > 2 else f"container-{container_id}"
                                    
                                    containers.append({
                                        "id": container_id,
                                        "status": status,
                                        "name": name
                                    })
                            except (ValueError, IndexError):
                                errors.append(f"Could not parse container line: {line}")
                    
                    data["containers"] = containers
                    data["container_count"] = len(containers)
                    data["running_containers"] = len([c for c in containers if c["status"] == "running"])
                    data["stopped_containers"] = len([c for c in containers if c["status"] == "stopped"])
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                errors.append(f"Could not get container list: {e}")
            
            # Get VM list as well
            try:
                result = subprocess.run(
                    ["qm", "list"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode == 0:
                    vms = []
                    lines = result.stdout.strip().split('\n')
                    
                    # Skip header line
                    for line in lines[1:]:
                        if line.strip():
                            try:
                                parts = line.split()
                                if len(parts) >= 3:
                                    vm_id = parts[0]
                                    status = parts[2]
                                    name = parts[1] if len(parts) > 1 else f"vm-{vm_id}"
                                    
                                    vms.append({
                                        "id": vm_id,
                                        "status": status,
                                        "name": name
                                    })
                            except (ValueError, IndexError):
                                errors.append(f"Could not parse VM line: {line}")
                    
                    data["vms"] = vms
                    data["vm_count"] = len(vms)
                    data["running_vms"] = len([v for v in vms if v["status"] == "running"])
                    data["stopped_vms"] = len([v for v in vms if v["status"] == "stopped"])
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                errors.append(f"Could not get VM list: {e}")
            
            if data:
                return self._create_success_result(data, CollectionMethod.LXC_COMMANDS)
            else:
                return self._create_failure_result(errors or ["No container inventory available"])
        
        except Exception as e:
            return self._create_failure_result([f"Container inventory collection failed: {e}"])