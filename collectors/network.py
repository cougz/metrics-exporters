"""Network I/O metrics collector for LXC containers"""
import re
from typing import List
from .base import BaseCollector
from metrics.models import MetricValue, MetricType
from utils.network import NetworkInterfaceDetector, NetworkRateCalculator
from logging_config import get_logger

logger = get_logger(__name__)


class NetworkCollector(BaseCollector):
    """Collect network interface statistics and per-second rates"""
    
    def __init__(self, config=None):
        super().__init__(config, "network", "LXC container network interface metrics")
        
        # Get network configuration from config
        include_interfaces = None
        exclude_interfaces = None
        
        if config:
            include_interfaces = getattr(config, 'network_interfaces', None)
            exclude_interfaces = getattr(config, 'network_exclude_interfaces', None)
        
        # Initialize interface detector with custom patterns if provided
        include_patterns = self._convert_interfaces_to_patterns(include_interfaces) if include_interfaces else None
        exclude_patterns = self._convert_interfaces_to_patterns(exclude_interfaces) if exclude_interfaces else None
        
        self.interface_detector = NetworkInterfaceDetector(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns
        )
        
        # Initialize rate calculator
        max_history = getattr(config, 'max_measurement_history', 10) if config else 10
        self.rate_calculator = NetworkRateCalculator(max_history=max_history)
        
    def collect(self) -> List[MetricValue]:
        """Collect network interface metrics"""
        metrics = []
        
        try:
            # Get all network interfaces
            interfaces = self.interface_detector.get_interfaces()
            
            if not interfaces:
                logger.debug("No network interfaces found for monitoring")
                return metrics
            
            # Calculate rates for all interfaces
            interface_rates = self.rate_calculator.update_and_calculate_rates(interfaces)
            
            # Create metrics for each interface
            for interface in interfaces:
                interface_metrics = self._create_interface_metrics(interface, interface_rates.get(interface.name, {}))
                metrics.extend(interface_metrics)
            
            logger.debug(f"Collected {len(metrics)} network metrics from {len(interfaces)} interfaces")
            
        except Exception as e:
            logger.error(f"Error collecting network metrics: {e}")
        
        return metrics
    
    def _create_interface_metrics(self, interface, rates: dict) -> List[MetricValue]:
        """Create metrics for a single network interface"""
        metrics = []
        
        # Get standard labels and add interface name
        interface_labels = self.get_standard_labels({
            "device": interface.name
        })
        
        # Interface operational state
        metrics.append(
            MetricValue(
                name="node_network_up",
                value=1.0 if interface.is_up else 0.0,
                labels=interface_labels,
                help_text="Network interface operational state",
                metric_type=MetricType.GAUGE
            )
        )
        
        # Interface speed (if available)
        if interface.speed_bytes is not None:
            metrics.append(
                MetricValue(
                    name="node_network_speed_bytes",
                    value=interface.speed_bytes,
                    labels=interface_labels,
                    help_text="Network interface speed in bytes per second",
                    metric_type=MetricType.GAUGE,
                    unit="bytes"
                )
            )
        
        # Interface information
        metrics.append(
            MetricValue(
                name="node_network_info",
                value=1.0,
                labels={
                    **interface_labels,
                    "is_loopback": str(interface.is_loopback).lower(),
                    "is_virtual": str(interface.is_virtual).lower()
                },
                help_text="Network interface information",
                metric_type=MetricType.GAUGE
            )
        )
        
        # Create metrics from interface statistics
        if interface.statistics:
            metrics.extend(self._create_counter_metrics(interface.statistics, interface_labels))
        
        # Create rate metrics
        if rates:
            metrics.extend(self._create_rate_metrics(rates, interface_labels))
        
        return metrics
    
    def _create_counter_metrics(self, statistics: dict, labels: dict) -> List[MetricValue]:
        """Create counter metrics from interface statistics"""
        metrics = []
        
        # Define counter metrics to create
        counter_mappings = [
            # Receive counters
            ('rx_bytes', 'node_network_receive_bytes_total', 'Total bytes received', 'bytes'),
            ('rx_packets', 'node_network_receive_packets_total', 'Total packets received', 'packets'),
            ('rx_errs', 'node_network_receive_errs_total', 'Total receive errors', 'errors'),
            ('rx_drop', 'node_network_receive_drop_total', 'Total receive packets dropped', 'packets'),
            ('rx_fifo', 'node_network_receive_fifo_total', 'Total receive FIFO errors', 'errors'),
            ('rx_frame', 'node_network_receive_frame_total', 'Total receive frame errors', 'errors'),
            ('rx_compressed', 'node_network_receive_compressed_total', 'Total compressed packets received', 'packets'),
            ('rx_multicast', 'node_network_receive_multicast_total', 'Total multicast packets received', 'packets'),
            
            # Transmit counters
            ('tx_bytes', 'node_network_transmit_bytes_total', 'Total bytes transmitted', 'bytes'),
            ('tx_packets', 'node_network_transmit_packets_total', 'Total packets transmitted', 'packets'),
            ('tx_errs', 'node_network_transmit_errs_total', 'Total transmit errors', 'errors'),
            ('tx_drop', 'node_network_transmit_drop_total', 'Total transmit packets dropped', 'packets'),
            ('tx_fifo', 'node_network_transmit_fifo_total', 'Total transmit FIFO errors', 'errors'),
            ('tx_colls', 'node_network_transmit_colls_total', 'Total transmit collisions', 'collisions'),
            ('tx_carrier', 'node_network_transmit_carrier_total', 'Total transmit carrier errors', 'errors'),
            ('tx_compressed', 'node_network_transmit_compressed_total', 'Total compressed packets transmitted', 'packets'),
        ]
        
        for stat_key, metric_name, help_text, unit in counter_mappings:
            if stat_key in statistics:
                metrics.append(
                    MetricValue(
                        name=metric_name,
                        value=statistics[stat_key],
                        labels=labels,
                        help_text=help_text,
                        metric_type=MetricType.COUNTER,
                        unit=unit
                    )
                )
        
        return metrics
    
    def _create_rate_metrics(self, rates: dict, labels: dict) -> List[MetricValue]:
        """Create rate metrics (per-second values)"""
        metrics = []
        
        # Define rate metrics to create
        rate_mappings = [
            # Receive rates
            ('rx_bytes_per_sec', 'node_network_receive_bytes_per_sec', 'Bytes received per second', 'bytes'),
            ('rx_packets_per_sec', 'node_network_receive_packets_per_sec', 'Packets received per second', 'packets'),
            ('rx_errs_per_sec', 'node_network_receive_errs_per_sec', 'Receive errors per second', 'errors'),
            ('rx_drop_per_sec', 'node_network_receive_drop_per_sec', 'Receive drops per second', 'packets'),
            
            # Transmit rates
            ('tx_bytes_per_sec', 'node_network_transmit_bytes_per_sec', 'Bytes transmitted per second', 'bytes'),
            ('tx_packets_per_sec', 'node_network_transmit_packets_per_sec', 'Packets transmitted per second', 'packets'),
            ('tx_errs_per_sec', 'node_network_transmit_errs_per_sec', 'Transmit errors per second', 'errors'),
            ('tx_drop_per_sec', 'node_network_transmit_drop_per_sec', 'Transmit drops per second', 'packets'),
        ]
        
        for rate_key, metric_name, help_text, unit in rate_mappings:
            if rate_key in rates:
                metrics.append(
                    MetricValue(
                        name=metric_name,
                        value=rates[rate_key],
                        labels=labels,
                        help_text=help_text,
                        metric_type=MetricType.GAUGE,
                        unit=f"{unit}_per_second"
                    )
                )
        
        return metrics
    
    def _convert_interfaces_to_patterns(self, interfaces: List[str]) -> List[str]:
        """Convert interface names to regex patterns"""
        patterns = []
        
        for interface in interfaces:
            # If it looks like a regex pattern, use as-is
            if any(char in interface for char in ['^', '$', '*', '+', '?', '[', ']', '(', ')', '|']):
                patterns.append(interface)
            else:
                # Convert exact interface name to regex pattern
                patterns.append(f"^{re.escape(interface)}$")
        
        return patterns
    
    def get_collection_interval_hint(self) -> float:
        """Suggest collection interval for network metrics"""
        # Network metrics benefit from regular collection for accurate rates
        return 30.0  # 30 seconds
    
    def requires_rate_calculation(self) -> bool:
        """Indicate that this collector needs rate calculations"""
        return True