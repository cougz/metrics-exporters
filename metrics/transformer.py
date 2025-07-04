"""Metric transformer for converting between Prometheus and OpenTelemetry formats"""
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from .models import MetricValue, MetricType
from .semantic_conventions import SemanticConventions
from logging_config import get_logger

logger = get_logger(__name__)


class MetricTransformer:
    """Transforms metrics between Prometheus and OpenTelemetry formats"""
    
    def __init__(self, config=None):
        self.config = config
        self.use_otel_semconv = config.use_otel_semconv if config else True
        self.resource_attributes = self._get_resource_attributes()
    
    def _get_resource_attributes(self) -> Dict[str, str]:
        """Get resource attributes from config"""
        if not self.config:
            return {}
        
        return self.config.get_otel_resource_attributes()
    
    def transform_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Transform metrics according to configuration"""
        if not self.use_otel_semconv:
            return metrics
        
        logger.debug(f"Transforming {len(metrics)} metrics to OpenTelemetry format")
        
        # First pass: convert names and units
        transformed_metrics = []
        for metric in metrics:
            transformed_metric = self._transform_single_metric(metric)
            if transformed_metric:
                transformed_metrics.append(transformed_metric)
        
        # Second pass: consolidate metrics that should be combined with labels
        consolidated_metrics = self._consolidate_metrics(transformed_metrics)
        
        logger.debug(f"Transformed to {len(consolidated_metrics)} OpenTelemetry metrics")
        return consolidated_metrics
    
    def _transform_single_metric(self, metric: MetricValue) -> Optional[MetricValue]:
        """Transform a single metric to OpenTelemetry format"""
        # Get OpenTelemetry name
        otel_name = SemanticConventions.get_otel_metric_name(metric.name)
        
        # Get OpenTelemetry unit
        otel_unit = SemanticConventions.get_otel_unit(metric.name)
        
        # Get OpenTelemetry description
        otel_description = SemanticConventions.get_otel_description(metric.name)
        if not otel_description:
            otel_description = metric.help_text
        
        # Transform labels
        new_labels = self._transform_labels(metric.labels.copy(), metric.name)
        
        # Convert percentage values to ratios
        new_value = SemanticConventions.convert_percentage_to_ratio(metric.value, metric.name)
        
        # Create transformed metric
        return MetricValue(
            name=otel_name,
            value=new_value,
            labels=new_labels,
            help_text=otel_description,
            metric_type=metric.metric_type,
            unit=otel_unit,
            timestamp=metric.timestamp
        )
    
    def _transform_labels(self, labels: Dict[str, str], metric_name: str) -> Dict[str, str]:
        """Transform metric labels"""
        # Add consolidation labels if needed
        consolidation_labels = SemanticConventions.get_consolidation_labels(metric_name)
        if consolidation_labels:
            labels.update(consolidation_labels)
        
        # Remove labels that should be resource attributes
        resource_labels = {}
        metric_labels = {}
        
        for key, value in labels.items():
            if SemanticConventions.is_resource_attribute(key):
                resource_labels[key] = value
            else:
                metric_labels[key] = value
        
        # Store resource attributes for later use
        if resource_labels:
            logger.debug(f"Moving labels to resource attributes: {resource_labels}")
        
        return metric_labels
    
    def _consolidate_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Consolidate metrics that should be combined with state/direction labels"""
        # Group metrics by name
        grouped_metrics = defaultdict(list)
        standalone_metrics = []
        
        for metric in metrics:
            # Check if this metric should be consolidated
            if self._should_consolidate_metric(metric):
                grouped_metrics[metric.name].append(metric)
            else:
                standalone_metrics.append(metric)
        
        # Process grouped metrics
        consolidated_metrics = []
        for metric_name, metric_group in grouped_metrics.items():
            if len(metric_group) == 1:
                # Single metric, no consolidation needed
                consolidated_metrics.extend(metric_group)
            else:
                # Multiple metrics with same name, they should already have
                # appropriate state/direction labels from transformation
                consolidated_metrics.extend(metric_group)
        
        # Add standalone metrics
        consolidated_metrics.extend(standalone_metrics)
        
        return consolidated_metrics
    
    def _should_consolidate_metric(self, metric: MetricValue) -> bool:
        """Check if metric should be part of consolidation"""
        # Metrics with state, direction, or similar labels are candidates for consolidation
        consolidation_labels = ['state', 'direction', 'type', 'status']
        return any(label in metric.labels for label in consolidation_labels)
    
    def add_calculated_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Add calculated utilization metrics where appropriate"""
        if not self.use_otel_semconv:
            return metrics
        
        enhanced_metrics = metrics.copy()
        
        # Add memory utilization
        memory_utilization = self._calculate_memory_utilization(metrics)
        if memory_utilization:
            enhanced_metrics.append(memory_utilization)
        
        # Add filesystem utilization
        filesystem_utilizations = self._calculate_filesystem_utilization(metrics)
        enhanced_metrics.extend(filesystem_utilizations)
        
        # Add CPU utilization (if not already present)
        cpu_utilization = self._calculate_cpu_utilization(metrics)
        if cpu_utilization:
            enhanced_metrics.append(cpu_utilization)
        
        return enhanced_metrics
    
    def _calculate_memory_utilization(self, metrics: List[MetricValue]) -> Optional[MetricValue]:
        """Calculate memory utilization from usage metrics"""
        used_memory = None
        total_memory = None
        
        for metric in metrics:
            if metric.name == "system.memory.usage":
                if metric.labels.get("state") == "used":
                    used_memory = metric.value
                elif metric.labels.get("state") == "total":
                    total_memory = metric.value
        
        if used_memory is not None and total_memory is not None and total_memory > 0:
            utilization = used_memory / total_memory
            return MetricValue(
                name="system.memory.utilization",
                value=utilization,
                labels={k: v for k, v in metrics[0].labels.items() if k != "state"},
                help_text="Memory utilization as a fraction",
                metric_type=MetricType.GAUGE,
                unit="1"
            )
        
        return None
    
    def _calculate_filesystem_utilization(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Calculate filesystem utilization from usage metrics"""
        utilizations = []
        
        # Group filesystem metrics by mountpoint/device
        fs_metrics = defaultdict(dict)
        
        for metric in metrics:
            if metric.name == "system.filesystem.usage":
                key = (metric.labels.get("mountpoint", ""), metric.labels.get("device", ""))
                state = metric.labels.get("state")
                if state in ["used", "total"]:
                    fs_metrics[key][state] = metric
        
        # Calculate utilization for each filesystem
        for (mountpoint, device), states in fs_metrics.items():
            if "used" in states and "total" in states:
                used = states["used"].value
                total = states["total"].value
                
                if total > 0:
                    utilization = used / total
                    base_labels = {k: v for k, v in states["used"].labels.items() if k != "state"}
                    
                    utilizations.append(MetricValue(
                        name="system.filesystem.utilization",
                        value=utilization,
                        labels=base_labels,
                        help_text="Filesystem utilization as a fraction",
                        metric_type=MetricType.GAUGE,
                        unit="1"
                    ))
        
        return utilizations
    
    def _calculate_cpu_utilization(self, metrics: List[MetricValue]) -> Optional[MetricValue]:
        """Calculate CPU utilization from CPU time metrics"""
        cpu_times = {}
        
        for metric in metrics:
            if metric.name == "system.cpu.time":
                state = metric.labels.get("state")
                if state:
                    cpu_times[state] = metric.value
        
        # Calculate utilization as 1 - idle_ratio
        if "idle" in cpu_times:
            idle_ratio = cpu_times["idle"]
            utilization = 1.0 - idle_ratio
            
            # Get base labels (excluding state)
            base_labels = {}
            for metric in metrics:
                if metric.name == "system.cpu.time":
                    base_labels = {k: v for k, v in metric.labels.items() if k != "state"}
                    break
            
            return MetricValue(
                name="system.cpu.utilization",
                value=utilization,
                labels=base_labels,
                help_text="CPU utilization as a fraction",
                metric_type=MetricType.GAUGE,
                unit="1"
            )
        
        return None
    
    def get_resource_attributes(self) -> Dict[str, str]:
        """Get resource attributes that should be attached to all metrics"""
        return self.resource_attributes.copy()
    
    def remove_redundant_metrics(self, metrics: List[MetricValue]) -> List[MetricValue]:
        """Remove metrics that are redundant after consolidation"""
        if not self.use_otel_semconv:
            return metrics
        
        # Remove percentage metrics where we now have ratios
        redundant_patterns = [
            "node_zfs_pool_capacity_percent",  # Replaced by utilization calculation
        ]
        
        filtered_metrics = []
        for metric in metrics:
            if not any(pattern in metric.name for pattern in redundant_patterns):
                filtered_metrics.append(metric)
            else:
                logger.debug(f"Removing redundant metric: {metric.name}")
        
        return filtered_metrics