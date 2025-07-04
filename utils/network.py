"""Network utilities for interface detection and statistics"""
import os
import re
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:
    """Network interface information"""
    name: str
    is_up: bool = False
    speed_bytes: Optional[int] = None
    is_loopback: bool = False
    is_virtual: bool = False
    statistics: Dict[str, int] = None
    
    def __post_init__(self):
        if self.statistics is None:
            self.statistics = {}


class NetworkInterfaceDetector:
    """Detect and filter network interfaces for LXC containers"""
    
    # Default interface patterns to exclude
    DEFAULT_EXCLUDE_PATTERNS = [
        r'^lo$',           # Loopback
        r'^docker\d*$',    # Docker interfaces
        r'^br-[a-f0-9]+$', # Docker bridge interfaces
        r'^veth[a-f0-9]+$', # Virtual ethernet pairs
        r'^virbr\d*$',     # Libvirt bridge
        r'^tun\d*$',       # TUN interfaces
        r'^tap\d*$',       # TAP interfaces
    ]
    
    # Common LXC interface patterns to include
    DEFAULT_INCLUDE_PATTERNS = [
        r'^eth\d+$',       # Standard ethernet
        r'^ens\d+$',       # Predictable network names
        r'^enp\d+s\d+$',   # PCI ethernet
        r'^wlan\d+$',      # Wireless
        r'^wlp\d+s\d+$',   # PCI wireless
    ]
    
    def __init__(self, 
                 include_patterns: Optional[List[str]] = None,
                 exclude_patterns: Optional[List[str]] = None):
        self.include_patterns = include_patterns or self.DEFAULT_INCLUDE_PATTERNS
        self.exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDE_PATTERNS
        
        # Compile regex patterns for performance
        self._include_regex = [re.compile(pattern) for pattern in self.include_patterns]
        self._exclude_regex = [re.compile(pattern) for pattern in self.exclude_patterns]
    
    def get_interfaces(self) -> List[NetworkInterface]:
        """Get list of network interfaces suitable for monitoring"""
        interfaces = []
        
        # Get all interfaces from /proc/net/dev
        interface_names = self._get_interface_names()
        
        for name in interface_names:
            if self._should_include_interface(name):
                interface = self._get_interface_info(name)
                if interface:
                    interfaces.append(interface)
        
        return interfaces
    
    def _get_interface_names(self) -> List[str]:
        """Get all network interface names"""
        interface_names = []
        
        try:
            with open("/proc/net/dev", "r") as f:
                # Skip first two header lines
                f.readline()
                f.readline()
                
                for line in f:
                    # Format: interface_name: rx_bytes rx_packets ...
                    if ':' in line:
                        name = line.split(':')[0].strip()
                        interface_names.append(name)
        
        except Exception as e:
            logger.debug(f"Error reading /proc/net/dev: {e}")
        
        return interface_names
    
    def _should_include_interface(self, interface_name: str) -> bool:
        """Check if interface should be included based on patterns"""
        # Check exclude patterns first
        for pattern in self._exclude_regex:
            if pattern.match(interface_name):
                return False
        
        # Check include patterns
        for pattern in self._include_regex:
            if pattern.match(interface_name):
                return True
        
        # If no explicit include pattern matches, include by default
        # unless it's obviously a virtual interface
        if any(virt in interface_name.lower() for virt in ['virt', 'bridge', 'dummy']):
            return False
        
        return True
    
    def _get_interface_info(self, interface_name: str) -> Optional[NetworkInterface]:
        """Get detailed information about a network interface"""
        try:
            interface = NetworkInterface(name=interface_name)
            
            # Check if interface is loopback
            interface.is_loopback = interface_name == 'lo'
            
            # Get interface state and speed
            self._get_interface_state(interface)
            
            # Get interface statistics
            interface.statistics = self._get_interface_statistics(interface_name)
            
            return interface
        
        except Exception as e:
            logger.debug(f"Error getting info for interface {interface_name}: {e}")
            return None
    
    def _get_interface_state(self, interface: NetworkInterface):
        """Get interface operational state and speed"""
        interface_path = f"/sys/class/net/{interface.name}"
        
        # Check if interface is up
        try:
            with open(f"{interface_path}/operstate", "r") as f:
                state = f.read().strip()
                interface.is_up = state == "up"
        except FileNotFoundError:
            # Fallback: check if interface exists in /sys/class/net
            interface.is_up = os.path.exists(interface_path)
        except Exception as e:
            logger.debug(f"Error reading operstate for {interface.name}: {e}")
        
        # Get interface speed (if available)
        try:
            with open(f"{interface_path}/speed", "r") as f:
                # Speed is in Mbps, convert to bytes per second
                speed_mbps = int(f.read().strip())
                interface.speed_bytes = speed_mbps * 1_000_000 // 8
        except (FileNotFoundError, ValueError):
            # Speed not available (wireless, virtual interfaces, etc.)
            pass
        except Exception as e:
            logger.debug(f"Error reading speed for {interface.name}: {e}")
        
        # Check if interface is virtual
        try:
            # Virtual interfaces often don't have a device symlink
            device_path = f"{interface_path}/device"
            interface.is_virtual = not os.path.exists(device_path)
        except Exception:
            pass
    
    def _get_interface_statistics(self, interface_name: str) -> Dict[str, int]:
        """Get interface statistics from /proc/net/dev"""
        statistics = {}
        
        try:
            with open("/proc/net/dev", "r") as f:
                # Skip header lines
                f.readline()
                f.readline()
                
                for line in f:
                    if f"{interface_name}:" in line:
                        parts = line.split()
                        if len(parts) >= 17:
                            # Parse /proc/net/dev format:
                            # Interface| Receive: bytes packets errs drop fifo frame compressed multicast
                            #          | Transmit: bytes packets errs drop fifo colls carrier compressed
                            statistics = {
                                'rx_bytes': int(parts[1]),
                                'rx_packets': int(parts[2]),
                                'rx_errs': int(parts[3]),
                                'rx_drop': int(parts[4]),
                                'rx_fifo': int(parts[5]),
                                'rx_frame': int(parts[6]),
                                'rx_compressed': int(parts[7]),
                                'rx_multicast': int(parts[8]),
                                'tx_bytes': int(parts[9]),
                                'tx_packets': int(parts[10]),
                                'tx_errs': int(parts[11]),
                                'tx_drop': int(parts[12]),
                                'tx_fifo': int(parts[13]),
                                'tx_colls': int(parts[14]),
                                'tx_carrier': int(parts[15]),
                                'tx_compressed': int(parts[16])
                            }
                        break
        
        except Exception as e:
            logger.debug(f"Error reading statistics for {interface_name}: {e}")
        
        return statistics


class NetworkRateCalculator:
    """Calculate per-second rates for network statistics"""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self._interface_history: Dict[str, List[Dict[str, Any]]] = {}
    
    def update_and_calculate_rates(self, interfaces: List[NetworkInterface]) -> Dict[str, Dict[str, float]]:
        """Update interface statistics and calculate per-second rates"""
        current_time = time.time()
        rates = {}
        
        for interface in interfaces:
            interface_name = interface.name
            current_stats = interface.statistics.copy()
            current_stats['timestamp'] = current_time
            
            # Initialize history for new interfaces
            if interface_name not in self._interface_history:
                self._interface_history[interface_name] = []
            
            # Calculate rates if we have previous data
            history = self._interface_history[interface_name]
            if history:
                last_stats = history[-1]
                time_delta = current_time - last_stats['timestamp']
                
                if time_delta > 0:
                    interface_rates = {}
                    
                    # Calculate rates for key statistics
                    rate_stats = ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets', 
                                 'rx_errs', 'tx_errs', 'rx_drop', 'tx_drop']
                    
                    for stat in rate_stats:
                        current_val = current_stats.get(stat, 0)
                        last_val = last_stats.get(stat, 0)
                        
                        # Handle counter resets (current < last)
                        if current_val >= last_val:
                            rate = (current_val - last_val) / time_delta
                            interface_rates[f"{stat}_per_sec"] = rate
                        else:
                            # Counter reset, use current value as rate
                            interface_rates[f"{stat}_per_sec"] = current_val / time_delta
                    
                    rates[interface_name] = interface_rates
            
            # Add current stats to history
            history.append(current_stats)
            
            # Limit history size
            if len(history) > self.max_history:
                history.pop(0)
        
        return rates
    
    def get_interface_history(self, interface_name: str) -> List[Dict[str, Any]]:
        """Get historical data for an interface"""
        return self._interface_history.get(interface_name, [])
    
    def clear_history(self, interface_name: Optional[str] = None):
        """Clear history for a specific interface or all interfaces"""
        if interface_name:
            self._interface_history.pop(interface_name, None)
        else:
            self._interface_history.clear()