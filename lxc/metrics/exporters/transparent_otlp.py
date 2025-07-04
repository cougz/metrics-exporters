"""Transparent OTLP exporter that forwards Prometheus metrics without transformation"""
import time
from typing import List
import grpc
from opentelemetry.proto.metrics.v1 import metrics_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2_grpc
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from ..models import MetricValue, MetricType
from logging_config import get_logger


logger = get_logger(__name__)


class TransparentOTLPExporter:
    """Export metrics transparently via OTLP without SDK transformation"""
    
    def __init__(self, config=None):
        self.config = config
        self.enabled = config and config.otel_enabled
        self.endpoint = config.otel_endpoint if config else None
        self.insecure = config.otel_insecure if config else True
        self.headers = []
        
        if config and hasattr(config, 'otel_headers'):
            self.headers = [(k, v) for k, v in config.otel_headers.items()]
        
        # Create gRPC channel
        if self.enabled and self.endpoint:
            if self.insecure:
                self.channel = grpc.insecure_channel(self.endpoint)
            else:
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.secure_channel(self.endpoint, credentials)
            
            self.stub = metrics_service_pb2_grpc.MetricsServiceStub(self.channel)
            logger.info("Transparent OTLP exporter configured", endpoint=self.endpoint)
        else:
            self.channel = None
            self.stub = None
    
    def _create_resource(self):
        """Create OTLP resource"""
        resource_attributes = []
        if self.config:
            service_name = getattr(self.config, 'otel_service_name', 'lxc-metrics-exporter')
            service_version = getattr(self.config, 'otel_service_version', '1.0.0')
            
            resource_attributes.extend([
                common_pb2.KeyValue(
                    key="service.name",
                    value=common_pb2.AnyValue(string_value=service_name)
                ),
                common_pb2.KeyValue(
                    key="service.version", 
                    value=common_pb2.AnyValue(string_value=service_version)
                )
            ])
        
        return resource_pb2.Resource(attributes=resource_attributes)
    
    def _convert_metric_to_otlp(self, metric: MetricValue) -> metrics_pb2.Metric:
        """Convert MetricValue to OTLP Metric without transformation"""
        # Create metric labels as attributes
        attributes = []
        for key, value in metric.labels.items():
            attributes.append(common_pb2.KeyValue(
                key=key,
                value=common_pb2.AnyValue(string_value=str(value))
            ))
        
        # Create data point
        data_point = metrics_pb2.NumberDataPoint(
            attributes=attributes,
            time_unix_nano=int(time.time() * 1_000_000_000),
            as_double=float(metric.value)
        )
        
        # Create gauge (all our metrics are gauges)
        gauge = metrics_pb2.Gauge(data_points=[data_point])
        
        # Create metric
        otlp_metric = metrics_pb2.Metric(
            name=metric.name,
            description=metric.help_text,
            unit=metric.unit,
            gauge=gauge
        )
        
        return otlp_metric
    
    async def export_metrics(self, metrics: List[MetricValue]):
        """Export metrics transparently via OTLP"""
        if not self.enabled or not self.stub:
            return
        
        try:
            # Convert metrics to OTLP format
            otlp_metrics = []
            for metric in metrics:
                otlp_metric = self._convert_metric_to_otlp(metric)
                otlp_metrics.append(otlp_metric)
            
            # Create scope metrics
            scope_metrics = metrics_pb2.ScopeMetrics(
                scope=common_pb2.InstrumentationScope(
                    name="lxc-metrics-exporter",
                    version="1.0.0"
                ),
                metrics=otlp_metrics
            )
            
            # Create resource metrics
            resource_metrics = metrics_pb2.ResourceMetrics(
                resource=self._create_resource(),
                scope_metrics=[scope_metrics]
            )
            
            # Create export request
            request = metrics_service_pb2.ExportMetricsServiceRequest(
                resource_metrics=[resource_metrics]
            )
            
            # Send to collector
            metadata = self.headers if self.headers else None
            response = self.stub.Export(request, metadata=metadata, timeout=10)
            
            logger.debug("Exported metrics transparently via OTLP", 
                        metrics_count=len(metrics), 
                        response=response)
            
        except Exception as e:
            logger.error("Failed to export metrics via transparent OTLP", 
                        error=str(e), exc_info=True)
    
    def is_enabled(self) -> bool:
        """Check if transparent OTLP export is enabled"""
        return self.enabled and self.stub is not None
    
    async def start(self):
        """Start the transparent exporter (no-op for this implementation)"""
        if self.enabled:
            logger.info("Transparent OTLP exporter started")
    
    async def shutdown(self):
        """Shutdown the exporter"""
        if self.channel:
            self.channel.close()
            logger.info("Transparent OTLP exporter shutdown")