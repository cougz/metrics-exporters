"""Cgroup utilities for reading container resource statistics"""
import os
import time
from typing import Dict, Optional, Any
from enum import Enum
import logging
from .container import CgroupVersion, get_cgroup_version

logger = logging.getLogger(__name__)


class CgroupReader:
    """Utility class for reading cgroup statistics with version detection"""
    
    def __init__(self):
        self.cgroup_version = get_cgroup_version()
        self._last_cpu_stats = {}
        self._last_network_stats = {}
        
    def get_cpu_stats(self) -> Dict[str, Any]:
        """Get CPU statistics from cgroup with rate calculations"""
        current_time = time.time()
        
        if self.cgroup_version == CgroupVersion.V2:
            stats = self._get_cpu_stats_v2()
        elif self.cgroup_version == CgroupVersion.V1:
            stats = self._get_cpu_stats_v1()
        else:
            stats = self._get_cpu_stats_fallback()
        
        # Calculate rates if we have previous measurements
        if stats and self._last_cpu_stats:
            time_delta = current_time - self._last_cpu_stats.get('timestamp', current_time)
            if time_delta > 0:
                stats.update(self._calculate_cpu_rates(stats, time_delta))
        
        # Store current stats for next calculation
        if stats:
            stats['timestamp'] = current_time
            self._last_cpu_stats = stats.copy()
        
        return stats
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics from cgroup"""
        if self.cgroup_version == CgroupVersion.V2:
            return self._get_memory_stats_v2()
        elif self.cgroup_version == CgroupVersion.V1:
            return self._get_memory_stats_v1()
        else:
            return self._get_memory_stats_fallback()
    
    def _get_cpu_stats_v2(self) -> Dict[str, Any]:
        """Get CPU stats from cgroup v2"""
        stats = {}
        
        try:
            # Read cpu.stat file
            with open("/sys/fs/cgroup/cpu.stat", "r") as f:
                for line in f:
                    if line.startswith("usage_usec"):
                        # Convert microseconds to nanoseconds for consistency
                        stats['cpu_usage_ns'] = int(line.split()[1]) * 1000
                    elif line.startswith("user_usec"):
                        stats['cpu_user_ns'] = int(line.split()[1]) * 1000
                    elif line.startswith("system_usec"):
                        stats['cpu_system_ns'] = int(line.split()[1]) * 1000
        except FileNotFoundError:
            logger.debug("cgroup v2 cpu.stat not found")
        except Exception as e:
            logger.debug(f"Error reading cgroup v2 CPU stats: {e}")
        
        return stats
    
    def _get_cpu_stats_v1(self) -> Dict[str, Any]:
        """Get CPU stats from cgroup v1"""
        stats = {}
        
        try:
            # Read cpuacct.usage (total CPU time in nanoseconds)
            with open("/sys/fs/cgroup/cpuacct/cpuacct.usage", "r") as f:
                stats['cpu_usage_ns'] = int(f.read().strip())
            
            # Read cpuacct.stat (user and system time)
            with open("/sys/fs/cgroup/cpuacct/cpuacct.stat", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        if parts[0] == "user":
                            # Convert USER_HZ to nanoseconds (USER_HZ is typically 100)
                            stats['cpu_user_ns'] = int(parts[1]) * 10_000_000
                        elif parts[0] == "system":
                            stats['cpu_system_ns'] = int(parts[1]) * 10_000_000
        except FileNotFoundError:
            logger.debug("cgroup v1 cpuacct files not found")
        except Exception as e:
            logger.debug(f"Error reading cgroup v1 CPU stats: {e}")
        
        return stats
    
    def _get_cpu_stats_fallback(self) -> Dict[str, Any]:
        """Fallback CPU stats from /proc/stat"""
        stats = {}
        
        try:
            with open("/proc/stat", "r") as f:
                first_line = f.readline()
                if first_line.startswith("cpu "):
                    # Parse: cpu user nice system idle iowait irq softirq steal guest guest_nice
                    values = [int(x) for x in first_line.split()[1:]]
                    if len(values) >= 4:
                        # Convert jiffies to nanoseconds (assuming USER_HZ=100)
                        user_ns = values[0] * 10_000_000
                        system_ns = values[2] * 10_000_000
                        idle_ns = values[3] * 10_000_000
                        
                        stats['cpu_user_ns'] = user_ns
                        stats['cpu_system_ns'] = system_ns
                        stats['cpu_idle_ns'] = idle_ns
                        stats['cpu_usage_ns'] = user_ns + system_ns
        except Exception as e:
            logger.debug(f"Error reading /proc/stat fallback: {e}")
        
        return stats
    
    def _calculate_cpu_rates(self, current_stats: Dict[str, Any], time_delta: float) -> Dict[str, Any]:
        """Calculate CPU usage rates"""
        rates = {}
        
        try:
            current_usage = current_stats.get('cpu_usage_ns', 0)
            last_usage = self._last_cpu_stats.get('cpu_usage_ns', 0)
            
            if current_usage >= last_usage and time_delta > 0:
                # Calculate usage delta in nanoseconds
                usage_delta_ns = current_usage - last_usage
                # Convert to percentage (time_delta is in seconds)
                usage_percent = (usage_delta_ns / (time_delta * 1_000_000_000)) * 100
                rates['cpu_usage_percent'] = min(usage_percent, 100.0)
            
            # Calculate user and system percentages
            for stat_type in ['cpu_user_ns', 'cpu_system_ns']:
                current_val = current_stats.get(stat_type, 0)
                last_val = self._last_cpu_stats.get(stat_type, 0)
                
                if current_val >= last_val and time_delta > 0:
                    delta_ns = current_val - last_val
                    percent = (delta_ns / (time_delta * 1_000_000_000)) * 100
                    rates[stat_type.replace('_ns', '_percent')] = min(percent, 100.0)
        
        except Exception as e:
            logger.debug(f"Error calculating CPU rates: {e}")
        
        return rates
    
    def _get_memory_stats_v2(self) -> Dict[str, Any]:
        """Get memory stats from cgroup v2"""
        stats = {}
        
        try:
            # Read memory.current (current usage)
            with open("/sys/fs/cgroup/memory.current", "r") as f:
                stats['memory_usage_bytes'] = int(f.read().strip())
            
            # Read memory.max (limit)
            with open("/sys/fs/cgroup/memory.max", "r") as f:
                max_val = f.read().strip()
                if max_val != "max":
                    stats['memory_limit_bytes'] = int(max_val)
            
            # Read memory.stat for detailed statistics
            with open("/sys/fs/cgroup/memory.stat", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        key, value = parts
                        if key in ['cache', 'rss', 'mapped_file']:
                            stats[f'memory_{key}_bytes'] = int(value)
        
        except FileNotFoundError:
            logger.debug("cgroup v2 memory files not found")
        except Exception as e:
            logger.debug(f"Error reading cgroup v2 memory stats: {e}")
        
        return stats
    
    def _get_memory_stats_v1(self) -> Dict[str, Any]:
        """Get memory stats from cgroup v1"""
        stats = {}
        
        try:
            # Read memory.usage_in_bytes
            with open("/sys/fs/cgroup/memory/memory.usage_in_bytes", "r") as f:
                stats['memory_usage_bytes'] = int(f.read().strip())
            
            # Read memory.limit_in_bytes
            with open("/sys/fs/cgroup/memory/memory.limit_in_bytes", "r") as f:
                limit = int(f.read().strip())
                # Check if it's a real limit (not the max value)
                if limit < (1 << 63) - 1:
                    stats['memory_limit_bytes'] = limit
            
            # Read memory.stat for detailed statistics
            with open("/sys/fs/cgroup/memory/memory.stat", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        key, value = parts
                        if key in ['cache', 'rss', 'mapped_file']:
                            stats[f'memory_{key}_bytes'] = int(value)
        
        except FileNotFoundError:
            logger.debug("cgroup v1 memory files not found")
        except Exception as e:
            logger.debug(f"Error reading cgroup v1 memory stats: {e}")
        
        return stats
    
    def _get_memory_stats_fallback(self) -> Dict[str, Any]:
        """Fallback memory stats from /proc/meminfo"""
        stats = {}
        
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        # Convert kB to bytes
                        stats['memory_total_bytes'] = int(line.split()[1]) * 1024
                    elif line.startswith("MemFree:"):
                        stats['memory_free_bytes'] = int(line.split()[1]) * 1024
                    elif line.startswith("MemAvailable:"):
                        stats['memory_available_bytes'] = int(line.split()[1]) * 1024
                    elif line.startswith("Cached:"):
                        stats['memory_cache_bytes'] = int(line.split()[1]) * 1024
        
        except Exception as e:
            logger.debug(f"Error reading /proc/meminfo fallback: {e}")
        
        return stats
    
    def get_load_averages(self) -> Dict[str, float]:
        """Get system load averages"""
        try:
            with open("/proc/loadavg", "r") as f:
                line = f.read().strip()
                values = line.split()
                
                return {
                    'load1': float(values[0]),
                    'load5': float(values[1]),
                    'load15': float(values[2])
                }
        except Exception as e:
            logger.debug(f"Error reading load averages: {e}")
            return {}
    
    def get_cpu_count(self) -> int:
        """Get number of CPU cores"""
        try:
            # Try to get from nproc first
            import subprocess
            result = subprocess.run(['nproc'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        
        try:
            # Fallback to /proc/cpuinfo
            cpu_count = 0
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("processor"):
                        cpu_count += 1
            return cpu_count
        except Exception as e:
            logger.debug(f"Error getting CPU count: {e}")
            return 1  # Default fallback