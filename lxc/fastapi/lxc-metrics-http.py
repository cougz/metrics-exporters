#!/usr/bin/env python3

import os
import time
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

# Configuration - Updated path
METRICS_FILE = '/opt/lxc-metrics/exporter/lxc_metrics.prom'

# FastAPI app setup
app = FastAPI(title="LXC Metrics FastAPI Server", version="1.0.0")

@app.get('/metrics', response_class=Response)
def get_metrics():
    """Serve metrics from file"""
    try:
        if os.path.exists(METRICS_FILE):
            with open(METRICS_FILE, 'r') as f:
                metrics_content = f.read()
            return Response(metrics_content, media_type='text/plain')
        else:
            return Response("# No metrics file found\n", 
                          media_type='text/plain', status_code=503)
    except Exception as e:
        return Response(f"# Error reading metrics: {str(e)}\n", 
                      media_type='text/plain', status_code=500)

@app.get('/health')
def health_check():
    """Health check endpoint"""
    try:
        if os.path.exists(METRICS_FILE):
            file_age = time.time() - os.path.getmtime(METRICS_FILE)
            metrics_size = os.path.getsize(METRICS_FILE)
            
            is_healthy = file_age < 120  # File should be updated within 2 minutes
            
            health_data = {
                "status": "healthy" if is_healthy else "unhealthy",
                "metrics_file": METRICS_FILE,
                "file_age_seconds": round(file_age, 1),
                "file_size_bytes": metrics_size,
                "file_exists": True
            }
            
            if not is_healthy:
                raise HTTPException(status_code=503, detail=health_data)
            
            return health_data
        else:
            raise HTTPException(status_code=503, detail={
                "status": "unhealthy",
                "metrics_file": METRICS_FILE,
                "file_exists": False,
                "error": "Metrics file not found"
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "status": "error",
            "error": str(e)
        })

@app.get('/status')
def get_status():
    """Detailed status endpoint"""
    try:
        file_exists = os.path.exists(METRICS_FILE)
        if file_exists:
            file_age = time.time() - os.path.getmtime(METRICS_FILE)
            file_size = os.path.getsize(METRICS_FILE)
            
            # Count metrics in file
            with open(METRICS_FILE, 'r') as f:
                content = f.read()
                metric_lines = len([line for line in content.split('\n') if line.startswith('system_') or line.startswith('lxc_')])
        else:
            file_age = None
            file_size = 0
            metric_lines = 0
        
        status_data = {
            "service": {
                "name": "lxc-metrics-fastapi",
                "version": "1.0.0",
                "uptime_seconds": round(time.time() - app.state.start_time, 1)
            },
            "metrics_file": {
                "path": METRICS_FILE,
                "exists": file_exists,
                "age_seconds": round(file_age, 1) if file_age else None,
                "size_bytes": file_size,
                "metric_count": metric_lines
            },
            "architecture": {
                "exporter": "/opt/lxc-metrics/exporter/lxc-metrics.sh",
                "fastapi": "/opt/lxc-metrics/fastapi/lxc-metrics-http.py"
            },
            "system": {
                "hostname": os.uname().nodename,
                "pid": os.getpid()
            }
        }
        
        return status_data
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})

@app.get('/', response_class=HTMLResponse)
def index():
    """Simple index page"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>LXC Metrics FastAPI Server</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .endpoint { margin: 10px 0; padding: 10px; background-color: #f8f9fa; border-radius: 4px; }
            .endpoint a { text-decoration: none; color: #0066cc; font-weight: bold; }
            .architecture { background-color: #e9ecef; padding: 15px; border-radius: 4px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>LXC Metrics FastAPI Server</h1>
        <p>FastAPI server serving LXC metrics from file</p>
        
        <h2>Available Endpoints:</h2>
        <div class="endpoint">
            <a href="/metrics">/metrics</a> - Prometheus metrics
        </div>
        <div class="endpoint">
            <a href="/health">/health</a> - Health check
        </div>
        <div class="endpoint">
            <a href="/status">/status</a> - Status information
        </div>
        
        <div class="architecture">
            <h2>Best Practice Metrics:</h2>
            <ul>
                <li><strong>Memory:</strong> system_memory_usage_bytes{state="used|free|available"}</li>
                <li><strong>Disk:</strong> system_filesystem_usage_bytes{device="...",mountpoint="/",fstype="zfs"}</li>
                <li><strong>Process:</strong> system_processes_count</li>
            </ul>
            <h2>Service Architecture:</h2>
            <ul>
                <li><strong>lxc-metrics-exporter:</strong> /opt/lxc-metrics/exporter/lxc-metrics.sh</li>
                <li><strong>lxc-metrics-fastapi:</strong> /opt/lxc-metrics/fastapi/lxc-metrics-http.py</li>
                <li><strong>Metrics file:</strong> """ + METRICS_FILE + """</li>
            </ul>
        </div>
    </body>
    </html>
    """
    return html

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    app.state.start_time = time.time()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9100)
