"""Clean OTLP exporter using direct gRPC communication"""
import time
import grpc
from typing import List, Dict, Any
from opentelemetry.proto.metrics.v1 import metrics_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2_grpc
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from .base import BaseExporter
from metrics.models import MetricValue, MetricType
from metrics.transformer import MetricTransformer
from config import Config
from logging_config import get_logger


logger = get_logger(__name__)


class CleanOTLPExporter(BaseExporter):
    """Clean OTLP exporter using direct gRPC without OpenTelemetry SDK transformations"""
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.channel = None
        self.stub = None
        self._healthy = False
        self.transformer = MetricTransformer(config)
    
    async def start(self) -> None:
        """Initialize gRPC connection"""
        try:
            if self.config.otel_insecure:
                self.channel = grpc.aio.insecure_channel(self.config.otel_endpoint)
            else:
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.aio.secure_channel(self.config.otel_endpoint, credentials)
            
            self.stub = metrics_service_pb2_grpc.MetricsServiceStub(self.channel)
            self._healthy = True
            
            logger.info(
                "OTLP exporter started",
                endpoint=self.config.otel_endpoint,
                insecure=self.config.otel_insecure
            )
        except Exception as e:
            logger.error(f"Failed to start OTLP exporter: {e}")
            self._healthy = False
            raise
    
    async def export_metrics(self, metrics: List[MetricValue]) -> None:
        """Export metrics via OTLP gRPC"""
        if not self._healthy or not self.stub:
            return
        
        try:
            # Apply OpenTelemetry semantic transformations if enabled
            final_metrics = metrics
            if self.config.use_otel_semconv:
                transformed_metrics = self.transformer.transform_metrics(metrics)
                enhanced_metrics = self.transformer.add_calculated_metrics(transformed_metrics)
                final_metrics = self.transformer.remove_redundant_metrics(enhanced_metrics)
                logger.info(
                    "Applied OpenTelemetry transformations",
                    original_count=len(metrics),
                    final_count=len(final_metrics),
                    event_type="otlp_transform"
                )
            
            # Group metrics by name for proper OTLP structure
            grouped_metrics = self._group_metrics_by_name(final_metrics)
            
            # Create OTLP metrics
            otlp_metrics = []
            for metric_name, metric_list in grouped_metrics.items():
                otlp_metric = self._create_otlp_metric(metric_name, metric_list)
                if otlp_metric:
                    otlp_metrics.append(otlp_metric)
            
            if not otlp_metrics:
                return
            
            # Create resource
            resource = self._create_resource()
            
            # Create scope metrics
            scope_metrics = metrics_pb2.ScopeMetrics(
                scope=common_pb2.InstrumentationScope(
                    name=self.config.service_name,
                    version=self.config.service_version
                ),
                metrics=otlp_metrics
            )
            
            # Create resource metrics
            resource_metrics = metrics_pb2.ResourceMetrics(
                resource=resource,
                scope_metrics=[scope_metrics]
            )
            
            # Create export request
            request = metrics_service_pb2.ExportMetricsServiceRequest(
                resource_metrics=[resource_metrics]
            )
            
            # Send request
            response = await self.stub.Export(request, timeout=10.0)
            
            # Log sample metric names for debugging
            sample_names = [metric.name for metric in final_metrics[:5]]
            logger.info(
                "Exported metrics via OTLP",
                metric_count=len(final_metrics),
                grouped_metrics=len(otlp_metrics),
                endpoint=self.config.otel_endpoint,
                sample_metric_names=sample_names,
                grpc_response_code=response.partial_success.rejected_data_points if hasattr(response, 'partial_success') else "success",
                grpc_response_message=response.partial_success.error_message if hasattr(response, 'partial_success') and response.partial_success.error_message else "no_errors",
                event_type="otlp_export"
            )
            
        except grpc.RpcError as e:
            logger.error(
                "gRPC error during OTLP export",
                grpc_code=e.code().name if hasattr(e, 'code') else 'unknown',
                grpc_details=e.details() if hasattr(e, 'details') else str(e),
                endpoint=self.config.otel_endpoint,
                event_type="otlp_grpc_error"
            )
            self._healthy = False
        except Exception as e:
            logger.error(
                "Failed to export metrics via OTLP",
                error=str(e),
                error_type=type(e).__name__,
                endpoint=self.config.otel_endpoint,
                event_type="otlp_export_error"
            )
            self._healthy = False
    
    async def shutdown(self) -> None:
        """Cleanup gRPC resources"""
        if self.channel:
            await self.channel.close()
        self._healthy = False
        logger.info("OTLP exporter shutdown")
    
    def is_healthy(self) -> bool:
        """Check if exporter is healthy"""
        return self._healthy
    
    async def test_connection(self) -> dict:
        """Test the gRPC connection and return status"""
        if not self.channel:
            return {"connected": False, "error": "No channel established"}
        
        try:
            # Test channel connectivity
            connectivity = self.channel.get_state()
            
            # Try a simple health check if available
            status = {
                "connected": connectivity.name != "TRANSIENT_FAILURE",
                "state": connectivity.name,
                "endpoint": self.config.otel_endpoint,
                "healthy": self._healthy
            }
            
            return status
            
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def _group_metrics_by_name(self, metrics: List[MetricValue]) -> Dict[str, List[MetricValue]]:
        """Group metrics by name for OTLP structure"""
        grouped = {}
        for metric in metrics:
            if metric.name not in grouped:
                grouped[metric.name] = []
            grouped[metric.name].append(metric)
        return grouped
    
    def _create_otlp_metric(self, metric_name: str, metric_list: List[MetricValue]) -> metrics_pb2.Metric:
        """Create OTLP metric from grouped MetricValue list"""
        if not metric_list:
            return None
        
        # Use first metric for metadata (all should be the same)
        first_metric = metric_list[0]
        
        # Create metric based on type
        if first_metric.metric_type == MetricType.GAUGE:
            return self._create_gauge_metric(metric_name, metric_list, first_metric)
        elif first_metric.metric_type == MetricType.COUNTER:
            return self._create_counter_metric(metric_name, metric_list, first_metric)
        else:
            logger.warning(f"Unsupported metric type for OTLP: {first_metric.metric_type}")
            return None
    
    def _create_gauge_metric(self, metric_name: str, metric_list: List[MetricValue], template: MetricValue) -> metrics_pb2.Metric:
        """Create OTLP gauge metric"""
        data_points = []
        for metric in metric_list:
            data_point = metrics_pb2.NumberDataPoint(
                attributes=self._convert_labels_to_attributes(metric.labels),
                time_unix_nano=int((metric.timestamp or time.time()) * 1_000_000_000),
                as_double=float(metric.value)
            )
            data_points.append(data_point)
        
        return metrics_pb2.Metric(
            name=metric_name,
            description=template.help_text,
            unit=template.unit,
            gauge=metrics_pb2.Gauge(data_points=data_points)
        )
    
    def _create_counter_metric(self, metric_name: str, metric_list: List[MetricValue], template: MetricValue) -> metrics_pb2.Metric:
        """Create OTLP counter metric"""
        data_points = []
        for metric in metric_list:
            data_point = metrics_pb2.NumberDataPoint(
                attributes=self._convert_labels_to_attributes(metric.labels),
                time_unix_nano=int((metric.timestamp or time.time()) * 1_000_000_000),
                as_double=float(metric.value),
                start_time_unix_nano=int((metric.timestamp or time.time()) * 1_000_000_000)
            )
            data_points.append(data_point)
        
        return metrics_pb2.Metric(
            name=metric_name,
            description=template.help_text,
            unit=template.unit,
            sum=metrics_pb2.Sum(
                data_points=data_points,
                aggregation_temporality=metrics_pb2.AGGREGATION_TEMPORALITY_CUMULATIVE,
                is_monotonic=True
            )
        )
    
    def _convert_labels_to_attributes(self, labels: Dict[str, str]) -> List[common_pb2.KeyValue]:
        """Convert metric labels to OTLP attributes"""
        attributes = []
        for key, value in labels.items():
            attr = common_pb2.KeyValue(
                key=key,
                value=common_pb2.AnyValue(string_value=str(value))
            )
            attributes.append(attr)
        return attributes
    
    def _create_resource(self) -> resource_pb2.Resource:
        """Create OTLP resource"""
        resource_attrs = self.config.get_otel_resource_attributes()
        
        # Add transformer resource attributes if transformations are enabled
        if self.config.use_otel_semconv:
            resource_attrs.update(self.transformer.get_resource_attributes())
        
        attributes = []
        for key, value in resource_attrs.items():
            attr = common_pb2.KeyValue(
                key=key,
                value=common_pb2.AnyValue(string_value=str(value))
            )
            attributes.append(attr)
        
        return resource_pb2.Resource(attributes=attributes)