"""FastAPI server setup and routes"""
import asyncio
import time
import os
from typing import Dict, Any
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse
from config import Config
from metrics.registry_enhanced import EnvironmentAwareMetricsRegistry
from metrics.exporter import OTLPExporter
from logging_config import get_logger, log_metrics_collection, log_error
from middleware.security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    HealthCheckMiddleware
)


logger = get_logger(__name__)


class MetricsServer:
    """FastAPI server for metrics exporter"""
    
    def __init__(self, config: Config):
        self.config = config
        self.app = FastAPI(
            title="Metrics Exporter",
            version="1.0.0",
            docs_url=None,  # Disable docs for security
            redoc_url=None,  # Disable redoc for security
            openapi_url=None  # Disable OpenAPI schema for security
        )
        self.registry = EnvironmentAwareMetricsRegistry(config)
        
        # Initialize OTLP exporter
        self.exporter = OTLPExporter(config)
        
        # Collection state
        self.last_collection_time = 0
        self.collection_count = 0
        self.collection_errors = 0
        self.current_metrics = ""
        self.collection_task = None
        
        # Setup security middleware
        self._setup_middleware()
        
        # Setup routes
        self._setup_routes()
        
        # Setup startup/shutdown events
        self._setup_events()
    
    def _setup_middleware(self):
        """Setup security middleware"""
        # Add middleware in reverse order (last added is executed first)
        
        # Health check middleware (fastest path)
        self.app.add_middleware(HealthCheckMiddleware)
        
        # Request logging middleware
        if self.config.enable_request_logging:
            self.app.add_middleware(RequestLoggingMiddleware)
        
        # Rate limiting middleware (simplified)
        self.app.add_middleware(
            RateLimitMiddleware,
            max_requests=100,  # Default value
            window_seconds=60   # Default value
        )
        
        # Security headers middleware (simplified)
        self.app.add_middleware(
            SecurityHeadersMiddleware,
            trusted_hosts=["*"]  # Default to allow all
        )
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get('/metrics', response_class=Response)
        def get_metrics():
            """Metrics endpoint - OTLP only (no Prometheus support)"""
            return Response("# Metrics endpoint not available - OTLP export only\n", media_type='text/plain')
        
        @self.app.get('/health')
        def health_check():
            """Health check endpoint"""
            age = time.time() - self.last_collection_time if self.last_collection_time > 0 else float('inf')
            is_healthy = age < self.config.collection_interval * 2
            
            health_data = {
                "status": "healthy" if is_healthy else "unhealthy",
                "last_collection_seconds_ago": round(age, 1) if age != float('inf') else None,
                "collection_interval": self.config.collection_interval,
                "total_collections": self.collection_count,
                "collection_errors": self.collection_errors,
                "export_format": "otlp",
                "exporter_healthy": self.exporter.is_healthy()
            }
            
            if not is_healthy:
                raise HTTPException(status_code=503, detail=health_data)
            
            return health_data
        
        @self.app.get('/status')
        def get_status():
            """Detailed status information"""
            age = time.time() - self.last_collection_time if self.last_collection_time > 0 else float('inf')
            
            return {
                "service": {
                    "name": self.config.service_name,
                    "version": self.config.service_version,
                    "uptime_seconds": round(time.time() - self.app.state.start_time, 1),
                    "hostname": os.uname().nodename
                },
                "collection": {
                    "interval_seconds": self.config.collection_interval,
                    "last_collection_seconds_ago": round(age, 1) if age != float('inf') else None,
                    "total_collections": self.collection_count,
                    "collection_errors": self.collection_errors,
                    "success_rate": round((self.collection_count - self.collection_errors) / max(self.collection_count, 1) * 100, 1)
                },
                "collectors": self.registry.get_collector_status(),
                "exporter": {
                    "format": "otlp",
                    "healthy": self.exporter.is_healthy(),
                    "otlp_endpoint": self.config.otlp_endpoint
                }
            }
        
        @self.app.get('/collectors')
        def list_collectors():
            """List all available collectors"""
            return {
                "collectors": self.registry.get_collector_status(),
                "enabled_collectors": self.config.enabled_collectors
            }
        
        @self.app.get('/debug/detection')
        def debug_detection():
            """Debug hardware detection"""
            runtime_env = self.registry.get_runtime_environment()
            
            # Test hardware detection manually for debugging
            debug_info = {
                "environment_type": runtime_env.environment_type.value,
                "is_host": runtime_env.is_host,
                "is_container": runtime_env.is_container,
                "hardware_detection": {}
            }
            
            if runtime_env.is_host:
                debug_info["hardware_detection"] = {
                    "zfs": {
                        "detected": runtime_env._has_zfs(),
                        "test_results": runtime_env._debug_zfs_detection()
                    },
                    "cpu_sensors": {
                        "detected": runtime_env._has_cpu_sensors(), 
                        "test_results": runtime_env._debug_cpu_sensors_detection()
                    },
                    "nvme_sensors": {
                        "detected": runtime_env._has_nvme_sensors(),
                        "test_results": runtime_env._debug_nvme_sensors_detection()
                    }
                }
            
            return debug_info
        
        @self.app.get('/debug/collectors')
        def debug_collectors():
            """Debug collector data collection"""
            debug_info = {
                "collectors": {},
                "collection_summary": {
                    "total_collectors": len(self.registry.collectors),
                    "enabled_collectors": 0,
                    "sample_data_collected": 0
                }
            }
            
            # Test each registered collector
            for name, collector in self.registry.collectors.items():
                collector_debug = {
                    "name": name,
                    "enabled": collector.is_enabled(),
                    "class": collector.__class__.__name__,
                    "strategy": getattr(collector.get_collection_strategy(), 'name', 'unknown'),
                    "sample_collection": {}
                }
                
                if collector.is_enabled():
                    debug_info["collection_summary"]["enabled_collectors"] += 1
                    
                    # Try to collect sample data
                    try:
                        import time
                        start_time = time.time()
                        sample_metrics = collector.collect()
                        collection_time = time.time() - start_time
                        
                        collector_debug["sample_collection"] = {
                            "success": True,
                            "metrics_count": len(sample_metrics),
                            "collection_time_seconds": round(collection_time, 3),
                            "sample_metrics": [
                                {
                                    "name": m.name,
                                    "value": m.value,
                                    "labels": m.labels,
                                    "type": m.metric_type.value
                                } for m in sample_metrics[:5]  # First 5 metrics
                            ]
                        }
                        
                        if sample_metrics:
                            debug_info["collection_summary"]["sample_data_collected"] += 1
                            
                    except Exception as e:
                        collector_debug["sample_collection"] = {
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                
                debug_info["collectors"][name] = collector_debug
            
            return debug_info
        
        @self.app.get('/debug/metrics')
        def debug_metrics():
            """Debug endpoint showing metric structure (raw and transformed)"""
            try:
                # Collect raw metrics
                raw_metrics = self.registry.collect_all()
                
                # Apply transformation if OpenTelemetry conventions are enabled
                # Transform metrics using the exporter's transformer (always-on)
                from metrics.transformer import MetricTransformer
                transformer = MetricTransformer(self.config)
                transformed_metrics = transformer.transform_all(raw_metrics)
                transformation_applied = True
                
                def group_metrics(metrics_list):
                    """Group metrics by name for analysis"""
                    metric_groups = {}
                    for metric in metrics_list:
                        if metric.name not in metric_groups:
                            metric_groups[metric.name] = {
                                "name": metric.name,
                                "type": metric.metric_type.value,
                                "help": metric.help_text,
                                "unit": getattr(metric, 'unit', None),
                                "label_keys": set(),
                                "sample_count": 0,
                                "collectors": set(),
                                "sample_values": []
                            }
                        
                        # Add label keys
                        metric_groups[metric.name]["label_keys"].update(metric.labels.keys())
                        metric_groups[metric.name]["sample_count"] += 1
                        
                        # Add sample values (first few)
                        if len(metric_groups[metric.name]["sample_values"]) < 3:
                            metric_groups[metric.name]["sample_values"].append({
                                "value": metric.value,
                                "labels": dict(metric.labels)
                            })
                        
                        # Track which collector produced this metric
                        if hasattr(metric, 'collector_name'):
                            metric_groups[metric.name]["collectors"].add(metric.collector_name)
                    
                    # Convert sets to lists for JSON serialization
                    for group in metric_groups.values():
                        group["label_keys"] = sorted(list(group["label_keys"]))
                        group["collectors"] = sorted(list(group["collectors"]))
                    
                    return metric_groups
                
                # Group both raw and transformed metrics
                raw_groups = group_metrics(raw_metrics)
                transformed_groups = group_metrics(transformed_metrics)
                
                # Get export format info
                export_info = {
                    "format": "otlp",
                    "use_otel_semconv": True,
                    "transformation_applied": transformation_applied,
                    "otlp_endpoint": self.config.otlp_endpoint,
                    "prometheus_file": None
                }
                
                result = {
                    "export_info": export_info,
                    "collection_timestamp": time.time()
                }
                
                if transformation_applied:
                    # Show both raw and transformed when transformation is applied
                    result.update({
                        "raw_metrics": {
                            "count": len(raw_metrics),
                            "unique_metrics": len(raw_groups),
                            "metrics": sorted(raw_groups.values(), key=lambda x: x["name"])
                        },
                        "transformed_metrics": {
                            "count": len(transformed_metrics),
                            "unique_metrics": len(transformed_groups),
                            "metrics": sorted(transformed_groups.values(), key=lambda x: x["name"])
                        },
                        "transformation_summary": {
                            "metrics_before": len(raw_metrics),
                            "metrics_after": len(transformed_metrics),
                            "reduction_count": len(raw_metrics) - len(transformed_metrics),
                            "reduction_percentage": round((len(raw_metrics) - len(transformed_metrics)) / len(raw_metrics) * 100, 1) if raw_metrics else 0,
                            "new_calculated_metrics": [m["name"] for m in transformed_groups.values() if m["name"].endswith(".utilization")]
                        }
                    })
                else:
                    # Show only raw metrics when no transformation
                    result.update({
                        "metrics": {
                            "count": len(raw_metrics),
                            "unique_metrics": len(raw_groups),
                            "metrics": sorted(raw_groups.values(), key=lambda x: x["name"])
                        }
                    })
                
                return result
                
            except Exception as e:
                logger.error(f"Error in debug metrics endpoint: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get('/debug/metrics/otel')
        def debug_otel_metrics():
            """Debug endpoint showing OpenTelemetry transformed metrics in Prometheus format"""
            # OpenTelemetry semantic conventions are always enabled
            
            try:
                # Collect and transform metrics
                raw_metrics = self.registry.collect_all()
                from metrics.transformer import MetricTransformer
                transformer = MetricTransformer(self.config)
                
                transformed_metrics = transformer.transform_metrics(raw_metrics)
                enhanced_metrics = transformer.add_calculated_metrics(transformed_metrics)
                final_metrics = transformer.remove_redundant_metrics(enhanced_metrics)
                
                # Convert to Prometheus format
                lines = []
                lines.append("# OpenTelemetry Semantic Conventions Preview")
                lines.append(f"# Transformed {len(raw_metrics)} raw metrics into {len(final_metrics)} semantic metrics")
                lines.append(f"# Collection time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
                lines.append("")
                
                # Group by metric name for better organization
                metric_groups = {}
                for metric in final_metrics:
                    if metric.name not in metric_groups:
                        metric_groups[metric.name] = []
                    metric_groups[metric.name].append(metric)
                
                # Generate Prometheus format output
                for metric_name in sorted(metric_groups.keys()):
                    metrics_in_group = metric_groups[metric_name]
                    
                    # Add TYPE and HELP comments
                    first_metric = metrics_in_group[0]
                    lines.append(f"# TYPE {metric_name} {first_metric.metric_type.value}")
                    lines.append(f"# HELP {metric_name} {first_metric.help_text}")
                    if hasattr(first_metric, 'unit') and first_metric.unit:
                        lines.append(f"# UNIT {metric_name} {first_metric.unit}")
                    
                    # Add metric values
                    for metric in metrics_in_group:
                        lines.append(metric.to_prometheus_line())
                    
                    lines.append("")  # Empty line between metric groups
                
                return Response('\n'.join(lines), media_type='text/plain')
                
            except Exception as e:
                logger.error(f"Error in debug OTel metrics endpoint: {e}")
                error_content = f"# Error generating OpenTelemetry metrics preview: {str(e)}\n"
                return Response(error_content, media_type='text/plain')
        
        @self.app.get('/debug/sensors')
        def debug_sensors():
            """Debug sensor collection specifically"""
            runtime_env = self.registry.get_runtime_environment()
            
            if not runtime_env.is_host:
                return {"error": "Sensors debugging only available on host environments"}
            
            debug_info = {
                "sensor_collection_test": {}
            }
            
            # Test the actual strategy methods directly
            try:
                from collectors.strategies.host import HostStrategy
                strategy = HostStrategy()
                
                # Test CPU sensors
                cpu_temps = strategy._collect_cpu_temperatures()
                debug_info["sensor_collection_test"]["cpu_temperatures"] = {
                    "result": cpu_temps,
                    "count": len(cpu_temps) if cpu_temps else 0,
                    "first_sensor": cpu_temps[0] if cpu_temps else None
                }
                
                # Test thermal sensors
                thermal_sensors = strategy._collect_thermal_sensors()
                debug_info["sensor_collection_test"]["thermal_sensors"] = {
                    "result": thermal_sensors,
                    "count": len(thermal_sensors) if thermal_sensors else 0,
                    "first_sensor": thermal_sensors[0] if thermal_sensors else None
                }
                
                # Test NVMe sensors
                nvme_sensors = strategy._collect_disk_temperatures()
                debug_info["sensor_collection_test"]["nvme_sensors"] = {
                    "result": nvme_sensors,
                    "count": len(nvme_sensors) if nvme_sensors else 0,
                    "first_sensor": nvme_sensors[0] if nvme_sensors else None
                }
                
                # Test full strategy result
                cpu_result = strategy.collect_sensors_cpu()
                debug_info["sensor_collection_test"]["full_cpu_strategy"] = {
                    "status": cpu_result.status.value,
                    "data_keys": list(cpu_result.data.keys()),
                    "errors": cpu_result.errors,
                    "has_data": cpu_result.has_data
                }
                
            except Exception as e:
                debug_info["sensor_collection_test"]["error"] = str(e)
                debug_info["sensor_collection_test"]["error_type"] = type(e).__name__
            
            return debug_info
        
        @self.app.post('/collect')
        async def manual_collect():
            """Manually trigger metrics collection"""
            try:
                await self._collect_metrics()
                return {
                    "success": True,
                    "message": "Metrics collection triggered",
                    "collection_count": self.collection_count
                }
            except Exception as e:
                log_error(logger, e, {"component": "manual_collection", "endpoint": "/collect"})
                raise HTTPException(status_code=500, detail={"error": str(e)})
        
        @self.app.get('/debug/otlp/connection')
        async def debug_otlp_connection():
            """Debug OTLP connection status"""
            try:
                if hasattr(self.exporter, 'test_connection'):
                    connection_status = await self.exporter.test_connection()
                else:
                    connection_status = {"error": "Connection test not available"}
                
                return {
                    "exporter_type": type(self.exporter).__name__,
                    "endpoint": self.config.otlp_endpoint,
                    "service_name": self.config.service_name,
                    "insecure": self.config.otlp_insecure,
                    "exporter_healthy": self.exporter.is_healthy(),
                    "connection_status": connection_status,
                    "last_export_logs": "Check /debug/logs for recent OTLP export logs"
                }
            except Exception as e:
                logger.error(f"Error testing OTLP connection: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get('/debug/otlp')
        def debug_otlp_export():
            """Debug OTLP export - show exactly what would be sent"""
            try:
                # Collect raw metrics
                raw_metrics = self.registry.collect_all()
                
                # Apply transformations (always-on)
                from metrics.transformer import MetricTransformer
                transformer = MetricTransformer(self.config)
                final_metrics = transformer.transform_all(raw_metrics)
                
                # Simulate what the OTLP exporter would send
                grouped_metrics = {}
                for metric in final_metrics:
                    if metric.name not in grouped_metrics:
                        grouped_metrics[metric.name] = []
                    grouped_metrics[metric.name].append({
                        "value": metric.value,
                        "labels": dict(metric.labels),
                        "type": metric.metric_type.value,
                        "unit": getattr(metric, 'unit', '1'),
                        "help": metric.help_text,
                        "timestamp": metric.timestamp
                    })
                
                # Get resource attributes that would be sent
                resource_attrs = self.config.get_otlp_resource_attributes()
                
                return {
                    "otlp_endpoint": self.config.otlp_endpoint,
                    "service_name": self.config.service_name,
                    "service_version": self.config.service_version,
                    "transformation_enabled": True,
                    "raw_metric_count": len(raw_metrics),
                    "final_metric_count": len(final_metrics),
                    "grouped_metric_count": len(grouped_metrics),
                    "resource_attributes": resource_attrs,
                    "metrics_to_send": grouped_metrics,
                    "sample_metric_names": list(grouped_metrics.keys())[:10],
                    "exporter_healthy": self.exporter.is_healthy(),
                    "timestamp": time.time()
                }
                
            except Exception as e:
                logger.error(f"Error in debug OTLP endpoint: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get('/debug/otlp/raw')
        def debug_otlp_raw():
            """Debug OTLP raw data structure that would be sent to endpoint"""
            try:
                return self._simulate_otlp_export()
            except Exception as e:
                logger.error(f"Error in debug OTLP raw endpoint: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get('/debug/config')
        def debug_config():
            """Show current configuration affecting metric naming and export"""
            try:
                return {
                    "export_format": "otlp",
                    "use_otel_semconv": True,
                    "otlp_endpoint": self.config.otlp_endpoint,
                    "service_name": self.config.service_name,
                    "service_version": self.config.service_version,
                    "enabled_collectors": self.config.enabled_collectors,
                    "collection_interval": self.config.collection_interval,
                    "environment": {
                        "type": self.registry.get_runtime_environment().environment_type.value,
                        "is_host": self.registry.get_runtime_environment().is_host,
                        "is_container": self.registry.get_runtime_environment().is_container
                    },
                    "naming_strategy": "OpenTelemetry semantic conventions",
                    "expected_metric_prefix": "system.",
                    "timestamp": time.time()
                }
            except Exception as e:
                logger.error(f"Error in debug config endpoint: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get('/', response_class=HTMLResponse)
        def index():
            """Web interface"""
            return self._generate_html_interface()
    
    def _setup_events(self):
        """Setup FastAPI startup/shutdown events"""
        
        @self.app.on_event("startup")
        async def startup_event():
            """Initialize the application"""
            self.app.state.start_time = time.time()
            logger.info(
                "Application startup initiated",
                service_name=self.config.service_name,
                service_version=self.config.service_version,
                collection_interval=self.config.collection_interval,
                enabled_collectors=self.config.enabled_collectors,
                event_type="server_startup"
            )
            
            # Start exporter
            await self.exporter.start()
            
            # Start collection task
            self.collection_task = asyncio.create_task(self._collection_loop())
        
        @self.app.on_event("shutdown")
        async def shutdown_event():
            """Cleanup on shutdown"""
            logger.info("Shutting down metrics exporter", event_type="server_shutdown")
            
            if self.collection_task:
                self.collection_task.cancel()
                try:
                    await self.collection_task
                except asyncio.CancelledError:
                    pass
            
            # Cleanup exporter
            await self.exporter.shutdown()
            
            # Cleanup collectors
            self.registry.cleanup()
    
    async def _collection_loop(self):
        """Background metrics collection loop"""
        while True:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.config.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(logger, e, {"component": "collection_loop", "collection_errors": self.collection_errors})
                self.collection_errors += 1
                await asyncio.sleep(min(self.config.collection_interval, 30))
    
    async def _collect_metrics(self):
        """Collect metrics from all collectors and export"""
        try:
            start_time = time.time()
            self.collection_count += 1
            
            # Collect metrics asynchronously
            logger.debug("Starting async metrics collection", event_type="collection_start")
            metrics = await self.registry.collect_all_async()
            
            # Export metrics using configured exporter
            await self.exporter.export_metrics(metrics)
            
            self.last_collection_time = time.time()
            collection_time = self.last_collection_time - start_time
            
            # Log structured metrics collection
            log_metrics_collection(logger, len(metrics), collection_time)
            
        except Exception as e:
            log_error(logger, e, {"component": "metrics_collection", "collection_count": self.collection_count})
            self.collection_errors += 1
            raise
    
    def _generate_html_interface(self) -> str:
        """Generate HTML interface"""
        status_data = self.registry.get_collector_status()
        
        # Handle both enhanced and legacy registry formats
        if isinstance(status_data, dict) and "environment" in status_data:
            # Enhanced registry format
            environment_info = status_data.get("environment", {})
            collectors_status = status_data.get("collectors", {})
            if isinstance(collectors_status, dict) and "collectors" in collectors_status:
                collectors_status = collectors_status.get("collectors", {})
        else:
            # Legacy format
            collectors_status = status_data
            environment_info = None
        
        # Generate environment section if available
        env_section = ""
        if environment_info:
            env_section = f"""
                <h2>Runtime Environment:</h2>
                <div class="section">
                    <ul>
                        <li><strong>Environment Type:</strong> <span class="status-enabled">{environment_info.get('type', 'unknown').upper()}</span></li>
                        <li><strong>Detection Confidence:</strong> {environment_info.get('detection_confidence', 0):.1%}</li>
                        <li><strong>Hardware Access:</strong> <span class="{'status-enabled' if environment_info.get('supports_hardware_access', False) else 'status-disabled'}">{'Yes' if environment_info.get('supports_hardware_access', False) else 'No'}</span></li>
                    </ul>
                </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Metrics Exporter</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; color: #333; }}
                .endpoint {{ margin: 10px 0; padding: 10px; background-color: #f8f9fa; border-radius: 4px; }}
                .endpoint a {{ text-decoration: none; color: #0066cc; font-weight: bold; }}
                .section {{ background-color: #e9ecef; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                .status-enabled {{ color: #28a745; }}
                .status-disabled {{ color: #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Metrics Exporter</h1>
                    <p>System metrics exporter with intelligent collection strategies</p>
                </div>
                
                <h2>Available Endpoints:</h2>
                <div class="endpoint"><a href="/metrics">/metrics</a> - Prometheus metrics</div>
                <div class="endpoint"><a href="/health">/health</a> - Health check</div>
                <div class="endpoint"><a href="/status">/status</a> - Status information</div>
                <div class="endpoint"><a href="/collectors">/collectors</a> - Collector information</div>
                <div class="endpoint"><a href="/debug/detection">/debug/detection</a> - Hardware detection debug</div>
                <div class="endpoint"><a href="/debug/collectors">/debug/collectors</a> - Collector data testing</div>
                <div class="endpoint"><a href="/debug/sensors">/debug/sensors</a> - Sensor collection testing</div>
                <div class="endpoint"><a href="/debug/metrics">/debug/metrics</a> - Metrics structure debug (raw + transformed)</div>
                <div class="endpoint"><a href="/debug/metrics/otel">/debug/metrics/otel</a> - OpenTelemetry transformed metrics preview</div>
                <div class="endpoint"><a href="/debug/config">/debug/config</a> - Configuration and naming strategy</div>
                <div class="endpoint"><a href="/debug/otlp/raw">/debug/otlp/raw</a> - Raw OTLP data structure</div>
                
                {env_section}
                
                <h2>Configuration:</h2>
                <div class="section">
                    <ul>
                        <li><strong>Collection Interval:</strong> {self.config.collection_interval} seconds</li>
                        <li><strong>Export Format:</strong> <span class="status-enabled">OTLP</span></li>
                        <li><strong>Exporter Status:</strong> <span class="{'status-enabled' if self.exporter.is_healthy() else 'status-disabled'}">{'Healthy' if self.exporter.is_healthy() else 'Unhealthy'}</span></li>
                        <li><strong>Hostname:</strong> {os.uname().nodename}</li>
                    </ul>
                </div>
                
                <h2>Collectors:</h2>
                <div class="section">
                    <ul>
                        {''.join([f'<li><strong>{name}:</strong> <span class="{"status-enabled" if info["enabled"] else "status-disabled"}">{"Enabled" if info["enabled"] else "Disabled"}</span> {"🔍" if info.get("auto_detected", False) else ""} {"📋" if info.get("registered", False) else "❌"} - {info["help"]}</li>' for name, info in sorted(collectors_status.items())])}
                    </ul>
                    <p><small>🔍 = Auto-detected, 📋 = Registered, ❌ = Not available</small></p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _simulate_otlp_export(self) -> Dict[str, Any]:
        """Simulate actual OTLP data structure that would be sent"""
        try:
            # Collect and transform metrics
            raw_metrics = self.registry.collect_all()
            # Apply transformations (always-on)
            from metrics.transformer import MetricTransformer
            transformer = MetricTransformer(self.config)
            final_metrics = transformer.transform_all(raw_metrics)
            
            # Get resource attributes
            resource_attrs = self.config.get_otlp_resource_attributes()
            
            # Simulate OTLP structure
            current_time = int(time.time() * 1_000_000_000)  # nanoseconds
            
            # Group metrics by name and labels
            metric_families = {}
            for metric in final_metrics:
                family_key = f"{metric.name}_{metric.metric_type.value}"
                if family_key not in metric_families:
                    metric_families[family_key] = {
                        "name": metric.name,
                        "description": metric.help_text,
                        "unit": getattr(metric, 'unit', '1'),
                        "type": metric.metric_type.value,
                        "data_points": []
                    }
                
                # Create data point
                data_point = {
                    "attributes": [
                        {"key": k, "value": {"string_value": str(v)}}
                        for k, v in metric.labels.items()
                    ],
                    "time_unix_nano": current_time,
                    "value": metric.value
                }
                
                metric_families[family_key]["data_points"].append(data_point)
            
            # Create OTLP structure
            otlp_data = {
                "resource_metrics": [
                    {
                        "resource": {
                            "attributes": [
                                {"key": k, "value": {"string_value": str(v)}}
                                for k, v in resource_attrs.items()
                            ]
                        },
                        "scope_metrics": [
                            {
                                "scope": {
                                    "name": "metrics-exporter",
                                    "version": self.config.service_version
                                },
                                "metrics": list(metric_families.values())
                            }
                        ]
                    }
                ]
            }
            
            return {
                "otlp_structure": otlp_data,
                "summary": {
                    "endpoint": self.config.otlp_endpoint,
                    "metric_families": len(metric_families),
                    "total_data_points": sum(len(f["data_points"]) for f in metric_families.values()),
                    "resource_attributes": len(resource_attrs),
                    "timestamp": time.time()
                }
            }
            
        except Exception as e:
            logger.error(f"Error simulating OTLP export: {e}")
            return {
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application"""
        return self.app