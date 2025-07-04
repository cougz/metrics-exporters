"""FastAPI server setup and routes"""
import asyncio
import time
import os
from typing import Dict, Any
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse
from config import Config
from metrics.registry_enhanced import EnvironmentAwareMetricsRegistry
from metrics.exporters.base import ExporterFactory
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
        
        # Initialize single exporter based on format
        self.exporter = ExporterFactory.create_exporter(config)
        
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
        
        # Rate limiting middleware
        self.app.add_middleware(
            RateLimitMiddleware,
            max_requests=self.config.rate_limit_requests,
            window_seconds=self.config.rate_limit_window
        )
        
        # Security headers middleware
        self.app.add_middleware(
            SecurityHeadersMiddleware,
            trusted_hosts=self.config.trusted_hosts
        )
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get('/metrics', response_class=Response)
        def get_metrics():
            """Serve metrics in Prometheus format (only available for Prometheus export)"""
            if self.config.is_prometheus_format():
                try:
                    content = self.config.prometheus_file.read_text(encoding='utf-8')
                    return Response(content, media_type='text/plain')
                except FileNotFoundError:
                    return Response("# Metrics file not found\n", media_type='text/plain')
            else:
                return Response("# Metrics endpoint only available for Prometheus export format\n", media_type='text/plain')
        
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
                "export_format": self.config.export_format.value,
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
                    "format": self.config.export_format.value,
                    "healthy": self.exporter.is_healthy(),
                    "prometheus_file": str(self.config.prometheus_file) if self.config.is_prometheus_format() else None,
                    "otlp_endpoint": self.config.otel_endpoint if self.config.is_otlp_format() else None
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
                
                {env_section}
                
                <h2>Configuration:</h2>
                <div class="section">
                    <ul>
                        <li><strong>Collection Interval:</strong> {self.config.collection_interval} seconds</li>
                        <li><strong>Export Format:</strong> <span class="status-enabled">{self.config.export_format.value.upper()}</span></li>
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
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application"""
        return self.app