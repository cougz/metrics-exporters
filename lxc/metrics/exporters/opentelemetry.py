"""OpenTelemetry SDK exporter"""
import logging
import time
from typing import List, Optional
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPMetricHTTPExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from ..models import MetricValue, MetricType


logger = logging.getLogger(__name__)


class OpenTelemetryExporter:
    """Export metrics using OpenTelemetry SDK"""
    
    def __init__(self, config=None):
        self.config = config
        self.meter_provider: Optional[MeterProvider] = None
        self.meter = None
        self.instruments = {}
        
        if config and config.otel_enabled:
            self._setup_otel()
    
    def _setup_otel(self):
        """Setup OpenTelemetry SDK"""
        try:
            # Create resource
            resource = Resource.create(self.config.get_otel_resource_attributes())
            
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
            
            logger.info(f"OpenTelemetry exporter configured for endpoint: {endpoint}")
            
        except Exception as e:
            logger.error(f"Failed to setup OpenTelemetry: {e}")
            self.meter_provider = None
            self.meter = None
    
    def _get_or_create_instrument(self, metric: MetricValue):
        """Get or create OpenTelemetry instrument for metric"""
        if not self.meter:
            return None
        
        instrument_key = f"{metric.name}_{metric.metric_type.value}"
        
        if instrument_key not in self.instruments:
            try:
                if metric.metric_type == MetricType.COUNTER:
                    instrument = self.meter.create_counter(
                        name=metric.name,
                        description=metric.help_text,
                        unit="1"
                    )
                elif metric.metric_type == MetricType.GAUGE:
                    instrument = self.meter.create_gauge(
                        name=metric.name,
                        description=metric.help_text,
                        unit="1"
                    )
                elif metric.metric_type == MetricType.HISTOGRAM:
                    instrument = self.meter.create_histogram(
                        name=metric.name,
                        description=metric.help_text,
                        unit="1"
                    )
                else:
                    # Default to gauge for unsupported types
                    instrument = self.meter.create_gauge(
                        name=metric.name,
                        description=metric.help_text,
                        unit="1"
                    )
                
                self.instruments[instrument_key] = instrument
                logger.debug(f"Created OTel instrument: {metric.name} ({metric.metric_type.value})")
                
            except Exception as e:
                logger.error(f"Failed to create instrument for {metric.name}: {e}")
                return None
        
        return self.instruments[instrument_key]
    
    def export_metrics(self, metrics: List[MetricValue]):
        """Export metrics to OpenTelemetry"""
        if not self.meter or not self.config.otel_enabled:
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
                        logger.error(f"Failed to record metric {metric.name}: {e}")
            
            logger.debug(f"Exported {len(metrics)} metrics to OpenTelemetry")
            
        except Exception as e:
            logger.error(f"Failed to export metrics to OpenTelemetry: {e}")
    
    def is_enabled(self) -> bool:
        """Check if OpenTelemetry export is enabled and configured"""
        return self.meter_provider is not None and self.config.otel_enabled
    
    def shutdown(self):
        """Shutdown OpenTelemetry resources"""
        if self.meter_provider:
            try:
                self.meter_provider.shutdown()
                logger.info("OpenTelemetry exporter shutdown")
            except Exception as e:
                logger.error(f"Error shutting down OpenTelemetry: {e}")