"""OpenTelemetry SDK exporter with connection pooling and batching"""
import asyncio
import time
from typing import List, Optional
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPMetricHTTPExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from ..models import MetricValue, MetricType
from .batch_exporter import BatchExporter
from ..transformer import MetricTransformer
from logging_config import get_logger


logger = get_logger(__name__)


class OpenTelemetryBatchExporter(BatchExporter):
    """Batched OpenTelemetry exporter"""
    
    def __init__(self, otel_exporter: 'OpenTelemetryExporter', **kwargs):
        super().__init__(**kwargs)
        self.otel_exporter = otel_exporter
    
    def _export_batch_sync(self, batch: List[MetricValue]):
        """Export batch of metrics synchronously"""
        if self.otel_exporter and self.otel_exporter.is_enabled():
            self.otel_exporter._export_metrics_sync(batch)


class OpenTelemetryExporter:
    """Export metrics using OpenTelemetry SDK with batching and connection pooling"""
    
    def __init__(self, config=None):
        self.config = config
        self.meter_provider: Optional[MeterProvider] = None
        self.meter = None
        self.instruments = {}
        self._batch_exporter = None
        self.transformer = MetricTransformer(config)
        
        if config and hasattr(config, 'otel_endpoint') and config.otel_endpoint:
            self._setup_otel()
            self._setup_batch_exporter()
    
    def _setup_otel(self):
        """Setup OpenTelemetry SDK"""
        try:
            # Create resource with enhanced attributes
            resource_attrs = self.config.get_otel_resource_attributes()
            resource_attrs.update(self.transformer.get_resource_attributes())
            resource = Resource.create(resource_attrs)
            
            # Determine if using HTTP or gRPC based on endpoint
            endpoint = self.config.otel_endpoint
            if endpoint.startswith('http://') or endpoint.startswith('https://'):
                # HTTP endpoint
                exporter = OTLPMetricHTTPExporter(
                    endpoint=endpoint,
                    headers=self.config.otel_headers,
                    insecure=self.config.otel_insecure
                )
            else:
                # gRPC endpoint
                exporter = OTLPMetricExporter(
                    endpoint=endpoint,
                    headers=list(self.config.otel_headers.items()),
                    insecure=self.config.otel_insecure
                )
            
            # Create metric reader
            reader = PeriodicExportingMetricReader(
                exporter=exporter,
                export_interval_millis=self.config.collection_interval * 1000
            )
            
            # Create meter provider
            self.meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[reader]
            )
            
            # Set global meter provider
            metrics.set_meter_provider(self.meter_provider)
            
            # Create meter
            self.meter = metrics.get_meter(
                self.config.otel_service_name,
                self.config.otel_service_version
            )
            
            logger.info("OpenTelemetry exporter configured", endpoint=endpoint, event_type="otel_setup")
            
        except Exception as e:
            logger.error("Failed to setup OpenTelemetry", error=str(e), event_type="otel_setup_error", exc_info=True)
            self.meter_provider = None
            self.meter = None
    
    def _setup_batch_exporter(self):
        """Setup batch exporter for improved performance"""
        if self.meter_provider:
            self._batch_exporter = OpenTelemetryBatchExporter(
                self,
                batch_size=getattr(self.config, 'otel_batch_size', 100),
                batch_timeout=getattr(self.config, 'otel_batch_timeout', 5.0),
                max_queue_size=getattr(self.config, 'otel_max_queue_size', 1000),
                worker_threads=getattr(self.config, 'otel_worker_threads', 2)
            )
    
    def _get_or_create_instrument(self, metric: MetricValue):
        """Get or create OpenTelemetry instrument for metric"""
        if not self.meter:
            return None
        
        instrument_key = f"{metric.name}_{metric.metric_type.value}"
        
        if instrument_key not in self.instruments:
            try:
                # Use the metric's unit if available, otherwise default to "1"
                unit = getattr(metric, 'unit', '1') or '1'
                
                if metric.metric_type == MetricType.COUNTER:
                    instrument = self.meter.create_counter(
                        name=metric.name,
                        description=metric.help_text,
                        unit=unit
                    )
                elif metric.metric_type == MetricType.GAUGE:
                    instrument = self.meter.create_gauge(
                        name=metric.name,
                        description=metric.help_text,
                        unit=unit
                    )
                elif metric.metric_type == MetricType.HISTOGRAM:
                    instrument = self.meter.create_histogram(
                        name=metric.name,
                        description=metric.help_text,
                        unit=unit
                    )
                else:
                    # Default to gauge for unsupported types
                    instrument = self.meter.create_gauge(
                        name=metric.name,
                        description=metric.help_text,
                        unit=unit
                    )
                
                self.instruments[instrument_key] = instrument
                logger.debug(f"Created OTel instrument: {metric.name} ({metric.metric_type.value}) unit={unit}")
                
            except Exception as e:
                logger.error(f"Failed to create instrument for {metric.name}: {e}")
                return None
        
        return self.instruments[instrument_key]
    
    async def export_metrics(self, metrics: List[MetricValue]):
        """Export metrics to OpenTelemetry using batch exporter"""
        if not self.is_enabled():
            return
        
        # Transform metrics to OpenTelemetry format
        transformed_metrics = self.transformer.transform_metrics(metrics)
        
        # Add calculated metrics
        enhanced_metrics = self.transformer.add_calculated_metrics(transformed_metrics)
        
        # Remove redundant metrics
        final_metrics = self.transformer.remove_redundant_metrics(enhanced_metrics)
        
        if self._batch_exporter:
            await self._batch_exporter.export_metrics(final_metrics)
        else:
            # Fallback to synchronous export
            self._export_metrics_sync(final_metrics)
    
    def _export_metrics_sync(self, metrics: List[MetricValue]):
        """Synchronous metrics export (used by batch exporter)"""
        if not self.meter or not (hasattr(self.config, 'otel_endpoint') and self.config.otel_endpoint):
            return
        
        try:
            for metric in metrics:
                instrument = self._get_or_create_instrument(metric)
                if instrument:
                    try:
                        if metric.metric_type == MetricType.COUNTER:
                            # For counters, we need to track the delta
                            instrument.add(metric.value, attributes=metric.labels)
                        elif metric.metric_type == MetricType.GAUGE:
                            instrument.set(metric.value, attributes=metric.labels)
                        elif metric.metric_type == MetricType.HISTOGRAM:
                            instrument.record(metric.value, attributes=metric.labels)
                        else:
                            # Default to gauge
                            instrument.set(metric.value, attributes=metric.labels)
                            
                    except Exception as e:
                        logger.error("Failed to record metric", metric_name=metric.name, error=str(e))
            
            logger.info("Exported metrics to OpenTelemetry", 
                       metrics_count=len(metrics), 
                       endpoint=self.config.otel_endpoint,
                       service_name=self.config.service_name,
                       event_type="otlp_export")
            
        except Exception as e:
            logger.error("Failed to export metrics to OpenTelemetry", error=str(e), exc_info=True)
    
    def is_enabled(self) -> bool:
        """Check if OpenTelemetry export is enabled and configured"""
        return self.meter_provider is not None and self.config.otel_enabled
    
    async def start(self):
        """Start the batch exporter"""
        if self._batch_exporter:
            await self._batch_exporter.start()
    
    async def shutdown(self):
        """Shutdown OpenTelemetry resources"""
        # Stop batch exporter first
        if self._batch_exporter:
            await self._batch_exporter.stop()
        
        # Shutdown meter provider
        if self.meter_provider:
            try:
                self.meter_provider.shutdown()
                logger.info("OpenTelemetry exporter shutdown", event_type="otel_shutdown")
            except Exception as e:
                logger.error("Error shutting down OpenTelemetry", error=str(e), event_type="otel_shutdown_error")