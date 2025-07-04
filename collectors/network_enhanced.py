"""Enhanced network metrics collector with environment-aware strategies"""
import logging
import time
from typing import List, Dict, Any, Optional
from .base_enhanced import EnvironmentAwareCollector
from metrics.models import MetricValue, MetricType

logger = logging.getLogger(__name__)


class NetworkCollector(EnvironmentAwareCollector):
    """Environment-aware network metrics collector"""
    
    def __init__(self, config=None):
        super().__init__(config, "network", "Network metrics with environment-aware collection")
        self._last_network_stats: Optional[Dict[str, Dict[str, int]]] = None
        self._last_collection_time: Optional[float] = None
    
    def collect(self) -> List[MetricValue]:
        """Collect network metrics using environment-appropriate strategy"""
        try:
            current_time = time.time()
            
            # Use strategy to collect network data
            result = self.collect_with_strategy("network")
            
            if not result.is_success:
                logger.warning(f"Network collection failed: {result.errors}")
                return []
            
            metrics = []
            labels = self.get_standard_labels()
            data = result.data
            
            # Process interface statistics
            if "interfaces" in data:
                current_stats = {}
                
                for interface_name, stats in data["interfaces"].items():
                    if isinstance(stats, dict):
                        current_stats[interface_name] = stats
                        
                        interface_labels = labels.copy()
                        interface_labels["device"] = interface_name
                        
                        # Basic interface metrics
                        basic_metrics = [
                            ("rx_bytes", "node_network_receive_bytes_total", "Total bytes received"),
                            ("rx_packets", "node_network_receive_packets_total", "Total packets received"),
                            ("rx_errs", "node_network_receive_errs_total", "Total receive errors"),
                            ("rx_drop", "node_network_receive_drop_total", "Total receive packets dropped"),
                            ("tx_bytes", "node_network_transmit_bytes_total", "Total bytes transmitted"),
                            ("tx_packets", "node_network_transmit_packets_total", "Total packets transmitted"),
                            ("tx_errs", "node_network_transmit_errs_total", "Total transmit errors"),
                            ("tx_drop", "node_network_transmit_drop_total", "Total transmit packets dropped"),
                        ]
                        
                        for stat_key, metric_name, help_text in basic_metrics:
                            if stat_key in stats:
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=float(stats[stat_key]),
                                    labels=interface_labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.COUNTER,
                                    unit="bytes" if "bytes" in stat_key else None
                                ))
                        
                        # Extended metrics (host environments)
                        extended_metrics = [
                            ("rx_fifo", "node_network_receive_fifo_total", "Total receive FIFO errors"),
                            ("rx_frame", "node_network_receive_frame_total", "Total receive frame errors"),
                            ("rx_compressed", "node_network_receive_compressed_total", "Total compressed packets received"),
                            ("rx_multicast", "node_network_receive_multicast_total", "Total multicast packets received"),
                            ("tx_fifo", "node_network_transmit_fifo_total", "Total transmit FIFO errors"),
                            ("tx_colls", "node_network_transmit_colls_total", "Total transmit collisions"),
                            ("tx_carrier", "node_network_transmit_carrier_total", "Total transmit carrier errors"),
                            ("tx_compressed", "node_network_transmit_compressed_total", "Total compressed packets transmitted"),
                        ]
                        
                        for stat_key, metric_name, help_text in extended_metrics:
                            if stat_key in stats:
                                metrics.append(MetricValue(
                                    name=metric_name,
                                    value=float(stats[stat_key]),
                                    labels=interface_labels.copy(),
                                    help_text=help_text,
                                    metric_type=MetricType.COUNTER
                                ))
                        
                        # Interface information
                        metrics.append(MetricValue(
                            name="node_network_up",
                            value=1.0,  # Assume interface is up if we have stats
                            labels=interface_labels.copy(),
                            help_text="Network interface operational state",
                            metric_type=MetricType.GAUGE
                        ))
                        
                        # Interface info with additional labels
                        info_labels = interface_labels.copy()
                        info_labels["is_loopback"] = "true" if interface_name == "lo" else "false"
                        info_labels["is_virtual"] = "true" if any(prefix in interface_name for prefix in ["veth", "docker", "br-", "virbr"]) else "false"
                        
                        metrics.append(MetricValue(
                            name="node_network_info",
                            value=1.0,
                            labels=info_labels,
                            help_text="Network interface information",
                            metric_type=MetricType.GAUGE
                        ))
                        
                        # Try to get interface speed (best effort)
                        try:
                            speed_file = f"/sys/class/net/{interface_name}/speed"
                            with open(speed_file, 'r') as f:
                                speed_mbps = int(f.read().strip())
                                if speed_mbps > 0:
                                    speed_bps = speed_mbps * 1000000  # Convert Mbps to bps
                                    metrics.append(MetricValue(
                                        name="node_network_speed_bytes",
                                        value=float(speed_bps // 8),  # Convert to bytes per second
                                        labels=interface_labels.copy(),
                                        help_text="Network interface speed in bytes per second",
                                        metric_type=MetricType.GAUGE,
                                        unit="bytes"
                                    ))
                        except (OSError, ValueError):
                            # Default speed for virtual interfaces
                            if "eth" in interface_name or "ens" in interface_name:
                                metrics.append(MetricValue(
                                    name="node_network_speed_bytes",
                                    value=1250000000.0,  # 10 Gbps default
                                    labels=interface_labels.copy(),
                                    help_text="Network interface speed in bytes per second",
                                    metric_type=MetricType.GAUGE,
                                    unit="bytes"
                                ))
                
                # Calculate rate metrics if we have previous data
                if (self._last_network_stats and self._last_collection_time and 
                    current_time > self._last_collection_time):
                    
                    time_delta = current_time - self._last_collection_time
                    rate_metrics = self._calculate_network_rates(current_stats, time_delta)
                    metrics.extend(rate_metrics)
                
                # Store current stats for next calculation
                self._last_network_stats = current_stats
                self._last_collection_time = current_time
            
            logger.debug(f"Collected {len(metrics)} network metrics using {result.method_used}")
            return metrics
        
        except Exception as e:
            logger.error(f"Network collection failed: {e}")
            return []
    
    def _calculate_network_rates(self, current_stats: Dict[str, Dict[str, int]], 
                                time_delta: float) -> List[MetricValue]:
        """Calculate network rate metrics"""
        metrics = []
        labels = self.get_standard_labels()
        
        try:
            for interface_name, current_data in current_stats.items():
                if interface_name in self._last_network_stats:
                    last_data = self._last_network_stats[interface_name]
                    
                    interface_labels = labels.copy()
                    interface_labels["device"] = interface_name
                    
                    # Calculate rates for key metrics
                    rate_metrics = [
                        ("rx_bytes", "node_network_receive_bytes_per_sec", "Bytes received per second"),
                        ("rx_packets", "node_network_receive_packets_per_sec", "Packets received per second"),
                        ("rx_errs", "node_network_receive_errs_per_sec", "Receive errors per second"),
                        ("rx_drop", "node_network_receive_drop_per_sec", "Receive drops per second"),
                        ("tx_bytes", "node_network_transmit_bytes_per_sec", "Bytes transmitted per second"),
                        ("tx_packets", "node_network_transmit_packets_per_sec", "Packets transmitted per second"),
                        ("tx_errs", "node_network_transmit_errs_per_sec", "Transmit errors per second"),
                        ("tx_drop", "node_network_transmit_drop_per_sec", "Transmit drops per second"),
                    ]
                    
                    for stat_key, metric_name, help_text in rate_metrics:
                        if stat_key in current_data and stat_key in last_data:
                            current_value = current_data[stat_key]
                            last_value = last_data[stat_key]
                            
                            # Handle counter wraparound (assume 32-bit counters)
                            if current_value < last_value:
                                current_value += 2**32
                            
                            delta = current_value - last_value
                            rate = delta / time_delta if time_delta > 0 else 0.0
                            
                            metrics.append(MetricValue(
                                name=metric_name,
                                value=max(0.0, rate),
                                labels=interface_labels.copy(),
                                help_text=help_text,
                                metric_type=MetricType.GAUGE,
                                unit="bytes" if "bytes" in stat_key else None
                            ))
        
        except Exception as e:
            logger.warning(f"Failed to calculate network rates: {e}")
        
        return metrics