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
    
    def collect_filesystem(self) -> StrategyResult:
        """Collect filesystem metrics with full filesystem access"""
        return self._collect_filesystem_full()
    
    def collect_zfs(self) -> StrategyResult:
        """Collect ZFS pool metrics with full access"""
        # Check if ZFS is actually available first
        if not self._has_zfs():
            return self._create_not_supported_result("ZFS not available on this system")
        return self._collect_zfs_full()
    
    def collect_network(self) -> StrategyResult:
        """Collect network metrics with full host access"""
        return self._collect_network_full()
    
    def collect_process(self) -> StrategyResult:
        """Collect process metrics with full system access"""
        return self._collect_process_full()
    
    def collect_sensors_cpu(self) -> StrategyResult:
        """Collect CPU sensor metrics with full access"""
        logger.info("Strategy: collect_sensors_cpu called")
        # Check if CPU sensors are actually available first
        if not self._has_cpu_sensors():
            logger.info("Strategy: _has_cpu_sensors returned False")
            return self._create_not_supported_result("CPU sensors not available on this system")
        logger.info("Strategy: _has_cpu_sensors returned True, calling _collect_sensors_cpu_full")
        return self._collect_sensors_cpu_full()
    
    def collect_sensors_nvme(self) -> StrategyResult:
        """Collect NVMe/disk sensor metrics with full access"""
        # Check if NVMe/disk sensors are actually available first
        if not self._has_nvme_sensors():
            return self._create_not_supported_result("NVMe/disk sensors not available on this system")
        return self._collect_sensors_nvme_full()
    
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
    
    def _collect_filesystem_full(self) -> StrategyResult:
        """Collect comprehensive filesystem metrics"""
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
                return self._create_failure_result(errors or ["No filesystem data available"])
        
        except Exception as e:
            return self._create_failure_result([f"Filesystem collection failed: {e}"])
    
    def _collect_zfs_full(self) -> StrategyResult:
        """Collect comprehensive ZFS pool metrics"""
        try:
            data = {}
            errors = []
            
            # Collect ZFS pool information if ZFS is available
            zfs_pools = self._collect_zfs_pools()
            if zfs_pools:
                data["zfs_pools"] = zfs_pools
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No ZFS pools available"])
        
        except Exception as e:
            return self._create_failure_result([f"ZFS collection failed: {e}"])
    
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
    
    def _collect_zfs_pools(self) -> Optional[List[Dict[str, Any]]]:
        """Collect ZFS pool information"""
        try:
            # Check if ZFS is available
            result = subprocess.run(
                ["which", "zpool"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("ZFS tools not available")
                return None
            
            pools = []
            
            # Get basic pool list and status
            try:
                result = subprocess.run(
                    ["zpool", "list", "-H", "-p"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
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
                                    
                                    pool_info = {
                                        "name": pool_name,
                                        "size_bytes": size_bytes,
                                        "allocated_bytes": alloc_bytes,
                                        "free_bytes": free_bytes,
                                        "capacity_percent": capacity_percent,
                                        "health": health
                                    }
                                    
                                    # Get additional pool properties
                                    pool_props = self._get_zfs_pool_properties(pool_name)
                                    if pool_props:
                                        pool_info.update(pool_props)
                                    
                                    # Get pool I/O statistics
                                    pool_iostat = self._get_zfs_pool_iostat(pool_name)
                                    if pool_iostat:
                                        pool_info.update(pool_iostat)
                                    
                                    pools.append(pool_info)
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Could not parse zpool list line: {line} - {e}")
                                continue
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.warning(f"Could not get ZFS pool list: {e}")
                return None
            
            return pools if pools else None
            
        except Exception as e:
            logger.warning(f"ZFS pool collection failed: {e}")
            return None
    
    def _get_zfs_pool_properties(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """Get additional ZFS pool properties"""
        try:
            result = subprocess.run(
                ["zpool", "get", "-H", "-p", "fragmentation,readonly,feature@async_destroy", pool_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                props = {}
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            parts = line.split('\t')
                            if len(parts) >= 3:
                                prop_name = parts[1]
                                prop_value = parts[2]
                                
                                if prop_name == "fragmentation" and prop_value != "-":
                                    props["fragmentation_percent"] = float(prop_value.rstrip('%'))
                                elif prop_name == "readonly":
                                    props["readonly"] = prop_value == "on"
                                elif prop_name.startswith("feature@"):
                                    feature_name = prop_name.replace("feature@", "")
                                    props[f"feature_{feature_name}"] = prop_value
                        except (ValueError, IndexError):
                            continue
                return props
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
        return None
    
    def _get_zfs_pool_iostat(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """Get ZFS pool I/O statistics"""
        try:
            result = subprocess.run(
                ["zpool", "iostat", "-H", "-p", pool_name, "1", "2"],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # Take the last line (second sample) for current stats
                if len(lines) >= 2:
                    last_line = lines[-1]
                    try:
                        parts = last_line.split()
                        if len(parts) >= 7:
                            return {
                                "read_operations_per_sec": float(parts[1]),
                                "write_operations_per_sec": float(parts[2]),
                                "read_bandwidth_bytes_per_sec": int(parts[3]),
                                "write_bandwidth_bytes_per_sec": int(parts[4])
                            }
                    except (ValueError, IndexError):
                        pass
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass
        return None
    
    def _collect_sensors_cpu_full(self) -> StrategyResult:
        """Collect comprehensive CPU sensor metrics"""
        try:
            data = {}
            errors = []
            
            # Collect CPU and system temperatures using sensors command
            cpu_temps = self._collect_cpu_temperatures()
            logger.info(f"CPU temperatures collected: {len(cpu_temps) if cpu_temps else 0} sensors")
            if cpu_temps:
                data["cpu_temperatures"] = cpu_temps
                logger.debug(f"First temperature sensor: {cpu_temps[0] if cpu_temps else 'None'}")
            else:
                logger.info("No CPU temperature sensors found")
            
            # Collect additional thermal sensors (fans, voltage, etc.)
            thermal_sensors = self._collect_thermal_sensors()
            logger.debug(f"Thermal sensors collected: {len(thermal_sensors) if thermal_sensors else 0} sensors")
            if thermal_sensors:
                data["thermal_sensors"] = thermal_sensors
            
            logger.debug(f"Final sensor data keys: {list(data.keys())}")
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No CPU sensor data available"])
        
        except Exception as e:
            logger.error(f"CPU sensors collection failed: {e}", exc_info=True)
            return self._create_failure_result([f"CPU sensors collection failed: {e}"])
    
    def _collect_sensors_nvme_full(self) -> StrategyResult:
        """Collect comprehensive NVMe/disk sensor metrics"""
        try:
            data = {}
            errors = []
            
            # Collect disk temperatures using smartctl
            disk_temps = self._collect_disk_temperatures()
            if disk_temps:
                data["disk_temperatures"] = disk_temps
            
            if data:
                return self._create_success_result(data, CollectionMethod.HARDWARE_ACCESS)
            else:
                return self._create_failure_result(errors or ["No NVMe sensor data available"])
        
        except Exception as e:
            return self._create_failure_result([f"NVMe sensors collection failed: {e}"])
    
    def _collect_cpu_temperatures(self) -> Optional[List[Dict[str, Any]]]:
        """Collect CPU temperature sensors using sensors command"""
        try:
            # Check if sensors command is available
            result = subprocess.run(
                ["which", "sensors"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("sensors command not available")
                return None
            
            logger.info("sensors command found, attempting to collect temperature data")
            
            # Run sensors command to get temperature data
            result = subprocess.run(
                ["sensors", "-A", "-j"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            logger.info(f"sensors -A -j result: returncode={result.returncode}, stdout_len={len(result.stdout)}, stderr={result.stderr}")
            
            if result.returncode != 0:
                logger.info("JSON sensors failed, trying text output")
                # Try without JSON output
                result = subprocess.run(
                    ["sensors", "-A"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                logger.info(f"sensors -A result: returncode={result.returncode}, stdout_len={len(result.stdout)}")
                if result.returncode == 0:
                    logger.info("Calling text parser")
                    parsed_result = self._parse_sensors_text_output(result.stdout)
                    logger.info(f"Text parser returned: {len(parsed_result) if parsed_result else 0} sensors")
                    return parsed_result
                return None
            
            # Parse JSON output
            try:
                import json
                sensors_data = json.loads(result.stdout)
                logger.info("Calling JSON parser")
                parsed_result = self._parse_sensors_json_output(sensors_data)
                logger.info(f"JSON parser returned: {len(parsed_result) if parsed_result else 0} sensors")
                return parsed_result
            except json.JSONDecodeError:
                # Fallback to text parsing
                return self._parse_sensors_text_output(result.stdout)
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Could not collect CPU temperatures: {e}")
            return None
        except Exception as e:
            logger.warning(f"CPU temperature collection failed: {e}")
            return None
    
    def _parse_sensors_json_output(self, sensors_data: dict) -> List[Dict[str, Any]]:
        """Parse JSON output from sensors command"""
        temperatures = []
        
        for chip_name, chip_data in sensors_data.items():
            if isinstance(chip_data, dict):
                for feature_name, feature_data in chip_data.items():
                    if isinstance(feature_data, dict):
                        # Look for temperature input data (temp*_input keys)
                        temp_input_key = None
                        temp_input_value = None
                        
                        # Find the temperature input key and value
                        for key, value in feature_data.items():
                            if isinstance(value, (int, float)) and key.endswith("_input") and "temp" in key:
                                temp_input_key = key
                                temp_input_value = value
                                break
                        
                        if temp_input_key and temp_input_value is not None:
                            temp_info = {
                                "chip": chip_name,
                                "feature": feature_name,
                                "sensor_name": f"{chip_name}_{feature_name}",
                                "temp_celsius": temp_input_value
                            }
                            
                            # Extract max and critical temperatures
                            temp_prefix = temp_input_key.replace("_input", "")
                            
                            max_key = f"{temp_prefix}_max"
                            if max_key in feature_data and isinstance(feature_data[max_key], (int, float)):
                                temp_info["temp_max_celsius"] = feature_data[max_key]
                            
                            crit_key = f"{temp_prefix}_crit"
                            if crit_key in feature_data and isinstance(feature_data[crit_key], (int, float)):
                                temp_info["temp_crit_celsius"] = feature_data[crit_key]
                            
                            temperatures.append(temp_info)
        
        return temperatures
    
    def _parse_sensors_text_output(self, sensors_output: str) -> List[Dict[str, Any]]:
        """Parse text output from sensors command"""
        temperatures = []
        current_chip = "unknown"
        
        logger.debug(f"Parsing sensors text output, {len(sensors_output)} characters")
        
        for line in sensors_output.split('\n'):
            line = line.strip()
            
            # Detect chip name
            if line and not line.startswith(' ') and ':' not in line and '°C' not in line:
                current_chip = line
                logger.debug(f"Found chip: {current_chip}")
                continue
            
            # Parse temperature lines
            if '°C' in line and ':' in line:
                logger.debug(f"Processing temperature line: {line}")
                try:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        feature_name = parts[0].strip()
                        temp_part = parts[1].strip()
                        
                        # Extract current temperature
                        import re
                        temp_match = re.search(r'([-+]?\d+\.?\d*)°C', temp_part)
                        if temp_match:
                            temp_celsius = float(temp_match.group(1))
                            
                            temp_info = {
                                "chip": current_chip,
                                "feature": feature_name,
                                "sensor_name": f"{current_chip}_{feature_name}",
                                "temp_celsius": temp_celsius
                            }
                            
                            # Extract critical and max temperatures
                            crit_match = re.search(r'crit\s*=\s*([-+]?\d+\.?\d*)°C', temp_part)
                            if crit_match:
                                temp_info["temp_crit_celsius"] = float(crit_match.group(1))
                            
                            # Look for both "high" and "max" temperature thresholds
                            max_match = re.search(r'(?:high|max)\s*=\s*([-+]?\d+\.?\d*)°C', temp_part)
                            if max_match:
                                temp_info["temp_max_celsius"] = float(max_match.group(1))
                            
                            temperatures.append(temp_info)
                            logger.debug(f"Added temperature sensor: {temp_info}")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Could not parse temperature line: {line} - {e}")
                    continue
        
        logger.debug(f"Total temperatures parsed: {len(temperatures)}")
        return temperatures
    
    def _collect_disk_temperatures(self) -> Optional[List[Dict[str, Any]]]:
        """Collect disk temperatures using smartctl"""
        try:
            # Check if smartctl is available
            result = subprocess.run(
                ["which", "smartctl"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.debug("smartctl command not available")
                return None
            
            disk_temps = []
            
            # Get list of available disks
            disks = self._get_available_disks()
            
            for disk_device in disks:
                try:
                    # Get SMART data for the disk
                    result = subprocess.run(
                        ["sudo", "smartctl", "-A", "-j", disk_device],
                        capture_output=True,
                        text=True,
                        timeout=20
                    )
                    
                    if result.returncode in [0, 4]:  # 0 = success, 4 = some SMART errors but data available
                        try:
                            import json
                            smart_data = json.loads(result.stdout)
                            disk_info = self._parse_smartctl_output(smart_data, disk_device)
                            if disk_info:
                                disk_temps.append(disk_info)
                        except json.JSONDecodeError:
                            # Try text parsing as fallback
                            disk_info = self._parse_smartctl_text_output(result.stdout, disk_device)
                            if disk_info:
                                disk_temps.append(disk_info)
                except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                    logger.debug(f"Could not get SMART data for {disk_device}: {e}")
                    continue
            
            return disk_temps if disk_temps else None
            
        except Exception as e:
            logger.warning(f"Disk temperature collection failed: {e}")
            return None
    
    def _get_available_disks(self) -> List[str]:
        """Get list of available disk devices"""
        disks = []
        
        try:
            # Check common disk device patterns
            from pathlib import Path
            dev_path = Path("/dev")
            
            # SATA/SCSI disks (sda, sdb, etc.)
            for item in dev_path.glob("sd[a-z]"):
                if item.is_block_device():
                    disks.append(str(item))
            
            # NVMe disks (nvme0, nvme1, etc.) - use character devices for temperature access
            for item in dev_path.glob("nvme[0-9]"):
                if item.is_char_device():
                    disks.append(str(item))
            
            # IDE disks (hda, hdb, etc.) - less common but still possible
            for item in dev_path.glob("hd[a-z]"):
                if item.is_block_device():
                    disks.append(str(item))
            
        except Exception as e:
            logger.debug(f"Could not enumerate disk devices: {e}")
        
        return disks[:10]  # Limit to first 10 disks to avoid excessive queries
    
    def _parse_smartctl_output(self, smart_data: dict, device: str) -> Optional[Dict[str, Any]]:
        """Parse JSON output from smartctl"""
        try:
            disk_info = {
                "device": device,
                "model": smart_data.get("model_name", "unknown"),
                "interface": smart_data.get("device", {}).get("type", "unknown")
            }
            
            # Get SMART health
            smart_status = smart_data.get("smart_status", {})
            if "passed" in smart_status:
                disk_info["smart_health"] = "PASSED" if smart_status["passed"] else "FAILED"
            
            # Get temperature from SMART attributes
            ata_smart_attrs = smart_data.get("ata_smart_attributes", {}).get("table", [])
            for attr in ata_smart_attrs:
                if attr.get("name") in ["Temperature_Celsius", "Airflow_Temperature_Cel"]:
                    disk_info["temperature_celsius"] = attr.get("raw", {}).get("value", 0)
                    break
            
            # For NVMe disks, check temperature in different location
            nvme_smart = smart_data.get("nvme_smart_health_information_log", {})
            if "temperature" in nvme_smart:
                disk_info["temperature_celsius"] = nvme_smart["temperature"]
            
            # Set default thresholds if not available from SMART
            if "temperature_celsius" in disk_info:
                # Typical safe operating temperatures for SSDs/HDDs
                if "nvme" in device.lower():
                    disk_info["temp_warning_celsius"] = 70  # NVMe typically warmer
                    disk_info["temp_critical_celsius"] = 85
                else:
                    disk_info["temp_warning_celsius"] = 50  # Traditional drives
                    disk_info["temp_critical_celsius"] = 60
            
            return disk_info if "temperature_celsius" in disk_info else None
            
        except Exception as e:
            logger.debug(f"Could not parse SMART data for {device}: {e}")
            return None
    
    def _parse_smartctl_text_output(self, smart_output: str, device: str) -> Optional[Dict[str, Any]]:
        """Parse text output from smartctl as fallback"""
        try:
            import re
            
            disk_info = {
                "device": device,
                "model": "unknown",
                "interface": "unknown"
            }
            
            # Extract model name
            model_match = re.search(r'Device Model:\s*(.+)', smart_output)
            if model_match:
                disk_info["model"] = model_match.group(1).strip()
            
            # Extract temperature
            temp_match = re.search(r'Temperature_Celsius\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)', smart_output)
            if temp_match:
                disk_info["temperature_celsius"] = int(temp_match.group(1))
                
                # Set default thresholds
                if "nvme" in device.lower():
                    disk_info["temp_warning_celsius"] = 70
                    disk_info["temp_critical_celsius"] = 85
                else:
                    disk_info["temp_warning_celsius"] = 50
                    disk_info["temp_critical_celsius"] = 60
            
            # Extract SMART health
            if "SMART overall-health self-assessment test result: PASSED" in smart_output:
                disk_info["smart_health"] = "PASSED"
            elif "SMART overall-health self-assessment test result: FAILED" in smart_output:
                disk_info["smart_health"] = "FAILED"
            
            return disk_info if "temperature_celsius" in disk_info else None
            
        except Exception as e:
            logger.debug(f"Could not parse SMART text output for {device}: {e}")
            return None
    
    def _collect_thermal_sensors(self) -> Optional[List[Dict[str, Any]]]:
        """Collect additional thermal sensors (fans, voltage, power)"""
        try:
            # Check if sensors command is available
            result = subprocess.run(
                ["which", "sensors"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None
            
            # Run sensors command to get all sensor data
            result = subprocess.run(
                ["sensors", "-A"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                return None
            
            thermal_sensors = []
            current_chip = "unknown"
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                # Detect chip name
                if line and not line.startswith(' ') and ':' not in line and not any(unit in line for unit in ['°C', 'RPM', 'V', 'W']):
                    current_chip = line
                    continue
                
                # Parse fan speed lines
                if 'RPM' in line and ':' in line:
                    try:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            sensor_name = parts[0].strip()
                            import re
                            rpm_match = re.search(r'(\d+)\s*RPM', parts[1])
                            if rpm_match:
                                thermal_sensors.append({
                                    "chip": current_chip,
                                    "sensor_name": f"{current_chip}_{sensor_name}",
                                    "sensor_type": "fan",
                                    "fan_rpm": int(rpm_match.group(1))
                                })
                    except (ValueError, AttributeError):
                        continue
                
                # Parse voltage lines
                elif 'V' in line and ':' in line and '°C' not in line:
                    try:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            sensor_name = parts[0].strip()
                            import re
                            voltage_match = re.search(r'([\d.]+)\s*V', parts[1])
                            if voltage_match:
                                thermal_sensors.append({
                                    "chip": current_chip,
                                    "sensor_name": f"{current_chip}_{sensor_name}",
                                    "sensor_type": "voltage",
                                    "voltage_volts": float(voltage_match.group(1))
                                })
                    except (ValueError, AttributeError):
                        continue
                
                # Parse power lines
                elif 'W' in line and ':' in line:
                    try:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            sensor_name = parts[0].strip()
                            import re
                            power_match = re.search(r'([\d.]+)\s*W', parts[1])
                            if power_match:
                                thermal_sensors.append({
                                    "chip": current_chip,
                                    "sensor_name": f"{current_chip}_{sensor_name}",
                                    "sensor_type": "power",
                                    "power_watts": float(power_match.group(1))
                                })
                    except (ValueError, AttributeError):
                        continue
            
            return thermal_sensors if thermal_sensors else None
            
        except Exception as e:
            logger.warning(f"Thermal sensors collection failed: {e}")
            return None
    
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
                return False
            
            # Check if there are actual pools
            result = subprocess.run(
                ["zpool", "list"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return False
            
            # Parse output to see if there are pools (more than just header)
            lines = result.stdout.strip().split('\n')
            return len(lines) > 1 and not any('no pools available' in line.lower() for line in lines)
            
        except Exception:
            return False
    
    def _has_cpu_sensors(self) -> bool:
        """Check if CPU temperature sensors are available"""
        try:
            import subprocess
            
            logger.info("Strategy: Checking if CPU sensors are available")
            
            # Check if sensors command exists
            result = subprocess.run(
                ["which", "sensors"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.info("Strategy: sensors command not found")
                return False
            
            logger.info("Strategy: sensors command found, testing output")
            # Test if sensors actually work and find temperature data
            result = subprocess.run(
                ["sensors", "-A"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.info(f"Strategy: sensors command failed with returncode {result.returncode}")
                return False
            
            # Check if output contains temperature readings
            has_temps = "°C" in result.stdout or "temp" in result.stdout.lower()
            logger.info(f"Strategy: sensors output check - has temps: {has_temps}, output length: {len(result.stdout)}")
            return has_temps
            
        except Exception:
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
                return False
            
            # Check if there are any NVMe or SATA drives
            dev_path = Path("/dev")
            nvme_drives = list(dev_path.glob("nvme*n*"))
            sata_drives = list(dev_path.glob("sd[a-z]"))
            
            return bool(nvme_drives or sata_drives)
            
        except Exception:
            return False