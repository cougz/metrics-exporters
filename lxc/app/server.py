"""FastAPI server setup and routes"""
import asyncio
import time
import os
from typing import Dict, Any
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse
from config import Config
from metrics.registry import MetricsRegistry
from metrics.exporters.prometheus import PrometheusExporter
from metrics.exporters.opentelemetry import OpenTelemetryExporter
from logging_config import get_logger, log_metrics_collection, log_error
from middleware.security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    HealthCheckMiddleware
)


logger = get_logger(__name__)


class MetricsServer:
    """FastAPI server for LXC metrics exporter"""
    
    def __init__(self, config: Config):
        self.config = config
        self.app = FastAPI(
            title="LXC Metrics Exporter",
            version="1.0.0",
            docs_url=None,  # Disable docs for security
            redoc_url=None,  # Disable redoc for security
            openapi_url=None  # Disable OpenAPI schema for security
        )
        self.registry = MetricsRegistry(config)
        
        # Initialize exporters
        self.prometheus_exporter = PrometheusExporter(config) if config.prometheus_enabled else None
        self.otel_exporter = OpenTelemetryExporter(config) if config.otel_enabled else None
        
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
            """Serve metrics in Prometheus format"""
            if self.prometheus_exporter:
                content = self.prometheus_exporter.read_metrics_file()
                return Response(content, media_type='text/plain')
            else:
                return Response("# Prometheus export disabled\n", media_type='text/plain')
        
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
                "prometheus_enabled": self.config.prometheus_enabled,
                "opentelemetry_enabled": self.config.otel_enabled and self.otel_exporter.is_enabled() if self.otel_exporter else False
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
                "exporters": {
                    "prometheus": {
                        "enabled": self.config.prometheus_enabled,
                        "file": self.config.prometheus_file if self.config.prometheus_enabled else None
                    },
                    "opentelemetry": {
                        "enabled": self.config.otel_enabled,
                        "endpoint": self.config.otel_endpoint if self.config.otel_enabled else None,
                        "configured": self.otel_exporter.is_enabled() if self.otel_exporter else False
                    }
                }
            }
        
        @self.app.get('/collectors')
        def list_collectors():
            """List all available collectors"""
            return {
                "collectors": self.registry.get_collector_status(),
                "enabled_collectors": self.config.enabled_collectors
            }
        
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
            
            # Start exporters
            if self.otel_exporter:
                await self.otel_exporter.start()
            
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
            
            # Cleanup exporters
            if self.otel_exporter:
                await self.otel_exporter.shutdown()
            
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
            
            # Export to Prometheus
            if self.prometheus_exporter:
                self.prometheus_exporter.write_metrics_file(metrics)
            
            # Export to OpenTelemetry asynchronously
            if self.otel_exporter and self.otel_exporter.is_enabled():
                await self.otel_exporter.export_metrics(metrics)
            
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
        collectors_status = self.registry.get_collector_status()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>LXC Metrics Exporter</title>
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
                    <h1>LXC Metrics Exporter</h1>
                    <p>FastAPI based metrics exporter for LXC containers</p>
                </div>
                
                <h2>Available Endpoints:</h2>
                <div class="endpoint"><a href="/metrics">/metrics</a> - Prometheus metrics</div>
                <div class="endpoint"><a href="/health">/health</a> - Health check</div>
                <div class="endpoint"><a href="/status">/status</a> - Status information</div>
                <div class="endpoint"><a href="/collectors">/collectors</a> - Collector information</div>
                
                <h2>Configuration:</h2>
                <div class="section">
                    <ul>
                        <li><strong>Collection Interval:</strong> {self.config.collection_interval} seconds</li>
                        <li><strong>Prometheus Export:</strong> <span class="{'status-enabled' if self.config.prometheus_enabled else 'status-disabled'}">{'Enabled' if self.config.prometheus_enabled else 'Disabled'}</span></li>
                        <li><strong>OpenTelemetry Export:</strong> <span class="{'status-enabled' if self.config.otel_enabled else 'status-disabled'}">{'Enabled' if self.config.otel_enabled else 'Disabled'}</span></li>
                        <li><strong>Hostname:</strong> {os.uname().nodename}</li>
                    </ul>
                </div>
                
                <h2>Collectors:</h2>
                <div class="section">
                    <ul>
                        {''.join([f'<li><strong>{name}:</strong> <span class="{"status-enabled" if info["enabled"] else "status-disabled"}">{"Enabled" if info["enabled"] else "Disabled"}</span> - {info["help"]}</li>' for name, info in collectors_status.items()])}
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application"""
        return self.app