#!/usr/bin/env python3

import os
import time
import threading
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

# Configuration
COLLECTION_INTERVAL = 30  # seconds
METRICS_FILE = '/opt/lxc-metrics-exporter/metrics.prom'

# FastAPI app setup
app = FastAPI(title="LXC Metrics Exporter", version="1.0.0")

# Global variables for metrics collection
current_metrics = ""
metrics_lock = threading.Lock()
last_update_time = 0
collection_errors = 0
total_collections = 0

def log_message(message: str, level: str = "INFO"):
    """Simple logging function"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)

def is_valid_number(value: str) -> bool:
    """Check if a string is a valid number"""
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False

def output_metric(metric_name: str, metric_type: str, value: str, additional_labels: str = "") -> str:
    """Format a metric in Prometheus format"""
    if not is_valid_number(value):
        return ""
    
    lines = []
    lines.append(f"# TYPE {metric_name} {metric_type}")
    lines.append(f"{metric_name}{{{additional_labels}}} {value}")
    return "\n".join(lines)

def get_memory_metrics() -> list:
    """Collect memory metrics (converted from bash script)"""
    metrics = []
    
    # Check cgroup v2 memory info
    cgroup_memory_limit = None
    cgroup_memory_usage = None
    
    try:
        if os.path.exists("/sys/fs/cgroup/memory.max"):
            with open("/sys/fs/cgroup/memory.max", "r") as f:
                cgroup_memory_limit = f.read().strip()
            
            with open("/sys/fs/cgroup/memory.current", "r") as f:
                cgroup_memory_usage = f.read().strip()
    except (IOError, OSError):
        pass
    
    # Parse /proc/meminfo
    proc_meminfo = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if ":" in line:
                    key, value = line.split(":", 1)
                    # Extract numeric value (remove kB suffix)
                    value_kb = value.strip().split()[0]
                    proc_meminfo[key] = int(value_kb)
    except (IOError, OSError, ValueError):
        return metrics
    
    # Calculate memory metrics
    if cgroup_memory_limit == "max" or not cgroup_memory_limit:
        # Use /proc/meminfo
        total_kb = proc_meminfo.get("MemTotal", 0)
        available_kb = proc_meminfo.get("MemAvailable", 0)
        free_kb = proc_meminfo.get("MemFree", 0)
        buffers_kb = proc_meminfo.get("Buffers", 0)
        cached_kb = proc_meminfo.get("Cached", 0)
        
        total_mem = total_kb * 1024
        
        # If total memory is reasonable container size (< 10GB), use it
        if total_mem < 10737418240:
            # Get current usage from cgroup if available
            if cgroup_memory_usage and is_valid_number(cgroup_memory_usage):
                used_mem = int(cgroup_memory_usage)
            else:
                # Calculate used memory
                used_mem = (total_kb - free_kb - buffers_kb - cached_kb) * 1024
            
            free_mem = total_mem - used_mem
            available_mem = available_kb * 1024
        else:
            # Fallback to known 2GB limit
            total_mem = 2147483648  # 2GB
            used_mem = int(cgroup_memory_usage) if cgroup_memory_usage and is_valid_number(cgroup_memory_usage) else 0
            free_mem = total_mem - used_mem
            available_mem = free_mem
    else:
        # Use cgroup limits
        total_mem = int(cgroup_memory_limit)
        used_mem = int(cgroup_memory_usage)
        free_mem = total_mem - used_mem
        available_mem = free_mem
    
    # Output metrics
    metrics.append(output_metric("system_memory_usage_bytes", "gauge", str(used_mem), 'state="used"'))
    metrics.append(output_metric("system_memory_usage_bytes", "gauge", str(free_mem), 'state="free"'))
    metrics.append(output_metric("system_memory_usage_bytes", "gauge", str(available_mem), 'state="available"'))
    metrics.append(output_metric("system_memory_total_bytes", "gauge", str(total_mem), ""))
    metrics.append(output_metric("lxc_memory_usage_bytes", "gauge", str(used_mem), ""))
    
    return [m for m in metrics if m]

def get_disk_metrics() -> list:
    """Collect disk metrics (converted from bash script)"""
    metrics = []
    
    try:
        # Get disk usage using df command
        result = subprocess.run(["df", "-T", "/"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                # Parse df output: Filesystem Type 1K-blocks Used Available Use% Mounted-on
                parts = lines[1].split()
                if len(parts) >= 7:
                    filesystem = parts[0]
                    fstype = parts[1]
                    size_kb = int(parts[2])
                    used_kb = int(parts[3])
                    avail_kb = int(parts[4])
                    mountpoint = parts[6]
                    
                    # Convert to bytes
                    size_bytes = size_kb * 1024
                    used_bytes = used_kb * 1024
                    avail_bytes = avail_kb * 1024
                    
                    # Format labels
                    disk_labels = f'device="{filesystem}",mountpoint="{mountpoint}",fstype="{fstype}"'
                    
                    # OpenTelemetry semantic conventions
                    metrics.append(output_metric("system_filesystem_usage_bytes", "gauge", str(used_bytes), disk_labels))
                    metrics.append(output_metric("system_filesystem_available_bytes", "gauge", str(avail_bytes), disk_labels))
                    metrics.append(output_metric("system_filesystem_size_bytes", "gauge", str(size_bytes), disk_labels))
                    
                    # Legacy compatibility
                    metrics.append(output_metric("lxc_disk_usage_bytes", "gauge", str(used_bytes), disk_labels))
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, IndexError):
        pass
    
    return [m for m in metrics if m]

def get_process_metrics() -> list:
    """Collect process count metrics (converted from bash script)"""
    metrics = []
    
    try:
        # Count processes using ps
        result = subprocess.run(["ps", "-A", "--no-headers"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            process_count = len(result.stdout.strip().split('\n'))
            
            metrics.append(output_metric("system_processes_count", "gauge", str(process_count), ""))
            metrics.append(output_metric("lxc_process_count", "gauge", str(process_count), ""))
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    
    return [m for m in metrics if m]

def collect_metrics_python() -> str:
    """Collect all metrics using Python (converted from bash script)"""
    all_metrics = []
    
    # Header
    all_metrics.append("# OpenTelemetry metrics for LXC")
    all_metrics.append(f"# Generated at {datetime.now().astimezone().isoformat()}")
    
    # Collect different metric types
    all_metrics.extend(get_memory_metrics())
    all_metrics.extend(get_disk_metrics())
    all_metrics.extend(get_process_metrics())
    
    # Footer
    all_metrics.append("# End of metrics")
    
    return "\n".join(all_metrics)

def write_metrics_file(metrics_content: str) -> bool:
    """Write metrics to file atomically"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
        
        # Write to temp file first
        temp_file = f"{METRICS_FILE}.tmp"
        with open(temp_file, 'w') as f:
            f.write(metrics_content)
        
        # Atomic move
        os.rename(temp_file, METRICS_FILE)
        
        # Set permissions
        os.chmod(METRICS_FILE, 0o644)
        
        # Try to set ownership (might fail if not root)
        try:
            import pwd
            import grp
            otelcol_user = pwd.getpwnam('otelcol')
            otelcol_group = grp.getgrnam('otelcol')
            os.chown(METRICS_FILE, otelcol_user.pw_uid, otelcol_group.gr_gid)
        except (KeyError, OSError):
            pass  # Ignore if user/group doesn't exist or no permission
        
        return True
    except Exception as e:
        log_message(f"Error writing metrics file: {e}", "ERROR")
        return False

def metrics_collection_thread():
    """Background thread for collecting metrics"""
    global current_metrics, last_update_time, collection_errors, total_collections
    
    log_message("Starting background metrics collection thread")
    
    while True:
        try:
            start_time = time.time()
            total_collections += 1
            
            # Collect metrics using Python
            log_message("Collecting metrics")
            fresh_metrics = collect_metrics_python()
            
            # Write to file
            if write_metrics_file(fresh_metrics):
                # Update global metrics with thread safety
                with metrics_lock:
                    current_metrics = fresh_metrics
                    last_update_time = time.time()
                
                collection_time = time.time() - start_time
                log_message(f"Metrics collection completed in {collection_time:.2f}s")
            else:
                collection_errors += 1
                log_message("Failed to write metrics file", "ERROR")
                
        except Exception as e:
            collection_errors += 1
            log_message(f"Unexpected error collecting metrics: {e}", "ERROR")
            
        # Wait for next collection cycle
        time.sleep(COLLECTION_INTERVAL)

@app.get('/metrics', response_class=Response)
def get_metrics():
    """Serve the most recently collected metrics in Prometheus format"""
    with metrics_lock:
        if current_metrics:
            return Response(current_metrics, media_type='text/plain')
        else:
            # No metrics available yet
            return Response("# No metrics available yet - collection in progress\n", 
                          media_type='text/plain', status_code=503)

@app.get('/health')
def health_check():
    """Health check endpoint with detailed status"""
    with metrics_lock:
        age = time.time() - last_update_time if last_update_time > 0 else float('inf')
        metrics_available = bool(current_metrics)
    
    # Determine health status
    is_healthy = age < COLLECTION_INTERVAL * 2 and metrics_available
    status_code = 200 if is_healthy else 503
    
    # Build health response
    health_data = {
        "status": "healthy" if is_healthy else "unhealthy",
        "last_update_seconds_ago": round(age, 1) if age != float('inf') else None,
        "metrics_available": metrics_available,
        "collection_interval": COLLECTION_INTERVAL,
        "total_collections": total_collections,
        "collection_errors": collection_errors,
        "error_rate": round(collection_errors / max(total_collections, 1) * 100, 1),
        "metrics_file": METRICS_FILE
    }
    
    if not is_healthy:
        raise HTTPException(status_code=status_code, detail=health_data)
    
    return health_data

@app.get('/status')
def get_status():
    """Detailed status endpoint for debugging"""
    with metrics_lock:
        age = time.time() - last_update_time if last_update_time > 0 else float('inf')
        metrics_size = len(current_metrics) if current_metrics else 0
    
    # Check file system
    metrics_dir = os.path.dirname(METRICS_FILE)
    metrics_dir_exists = os.path.exists(metrics_dir)
    metrics_dir_writable = os.access(metrics_dir, os.W_OK) if metrics_dir_exists else False
    
    
    # Get LXC container information
    lxc_info = get_lxc_info()
    
    status_data = {
        "service": {
            "name": "lxc-metrics-exporter",
            "version": "1.0.0",
            "uptime_seconds": round(time.time() - app.state.start_time, 1),
            "collection_interval": COLLECTION_INTERVAL
        },
        "metrics": {
            "last_update_seconds_ago": round(age, 1) if age != float('inf') else None,
            "metrics_size_bytes": metrics_size,
            "total_collections": total_collections,
            "collection_errors": collection_errors,
            "success_rate": round((total_collections - collection_errors) / max(total_collections, 1) * 100, 1)
        },
        "files": {
            "metrics_file": METRICS_FILE,
            "metrics_dir_exists": metrics_dir_exists,
            "metrics_dir_writable": metrics_dir_writable
        },
        "lxc": lxc_info,
        "system": {
            "python_version": sys.version.split()[0],
            "pid": os.getpid(),
            "hostname": os.uname().nodename,
            "working_directory": os.getcwd()
        }
    }
    
    return status_data

@app.get('/debug/collect-now')
def debug_collect_now():
    """Manually trigger metrics collection for debugging"""
    try:
        start_time = time.time()
        
        # Collect metrics
        fresh_metrics = collect_metrics_python()
        
        # Write to file
        write_success = write_metrics_file(fresh_metrics)
        
        # Update global metrics if successful
        if write_success:
            with metrics_lock:
                global current_metrics, last_update_time
                current_metrics = fresh_metrics
                last_update_time = time.time()
        
        execution_time = time.time() - start_time
        
        return {
            "success": True,
            "execution_time": round(execution_time, 2),
            "file_write_success": write_success,
            "metrics_size": len(fresh_metrics)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get('/debug/metrics-raw')
def get_raw_metrics():
    """Get raw metrics for debugging"""
    with metrics_lock:
        if current_metrics:
            return {"raw_metrics": current_metrics, "size": len(current_metrics)}
        else:
            return {"raw_metrics": None, "size": 0}

def get_lxc_info() -> Dict[str, Any]:
    """Get LXC container information"""
    lxc_info = {}
    
    # Try to get container ID
    try:
        with open('/proc/self/cgroup', 'r') as f:
            cgroup_content = f.read()
            if 'lxc' in cgroup_content:
                lxc_info['container_type'] = 'lxc'
                # Extract container ID if possible
                for line in cgroup_content.split('\n'):
                    if 'lxc' in line and '/' in line:
                        parts = line.split('/')
                        for part in parts:
                            if part.startswith('lxc') or part.isdigit():
                                lxc_info['container_id'] = part
                                break
    except:
        pass
    
    # Check if we're in a container
    if os.path.exists('/.dockerenv'):
        lxc_info['container_type'] = 'docker'
    elif os.path.exists('/proc/1/environ'):
        try:
            with open('/proc/1/environ', 'rb') as f:
                environ = f.read().decode('utf-8', errors='ignore')
                if 'container=' in environ:
                    lxc_info['container_type'] = 'container'
        except:
            pass
    
    return lxc_info

@app.get('/', response_class=HTMLResponse)
def index():
    """Web interface for debugging and monitoring"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>LXC Metrics Exporter</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 40px; 
                background-color: #f5f5f5;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .header { 
                text-align: center; 
                margin-bottom: 30px;
                color: #333;
            }
            .endpoint { 
                margin: 10px 0; 
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
            .endpoint a { 
                text-decoration: none; 
                color: #0066cc; 
                font-weight: bold;
            }
            .endpoint a:hover { 
                text-decoration: underline; 
            }
            .endpoint .description {
                color: #666;
                margin-top: 5px;
                font-size: 0.9em;
            }
            .metrics-preview {
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 4px;
                margin: 20px 0;
                border-left: 4px solid #0066cc;
            }
            .config-section {
                background-color: #e9ecef;
                padding: 15px;
                border-radius: 4px;
                margin: 20px 0;
            }
            .button {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 5px;
            }
            .button:hover {
                background-color: #0056b3;
            }
            .debug-output {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 15px;
                border-radius: 4px;
                font-family: monospace;
                white-space: pre-wrap;
                max-height: 400px;
                overflow-y: auto;
            }
        </style>
        <script>
            async function collectNow() {
                const button = document.getElementById('collect-now-btn');
                const output = document.getElementById('collect-output');
                
                button.disabled = true;
                button.textContent = 'Collecting...';
                output.textContent = 'Collecting metrics...';
                
                try {
                    const response = await fetch('/debug/collect-now');
                    const data = await response.json();
                    
                    output.textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    output.textContent = 'Error: ' + error.message;
                }
                
                button.disabled = false;
                button.textContent = 'Collect Now';
            }
            
            async function loadStatus() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    document.getElementById('status-info').textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    document.getElementById('status-info').textContent = 'Error loading status: ' + error.message;
                }
            }
            
            // Load status on page load
            window.onload = loadStatus;
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>LXC Metrics Exporter</h1>
                <p>FastAPI based Metrics Exporter for LXC containers</p>
            </div>
            
            <div class="metrics-preview">
                <h3>Collected Metrics:</h3>
                <ul>
                    <li><strong>Memory metrics:</strong> Usage, free, available, and total memory</li>
                    <li><strong>Filesystem metrics:</strong> Usage, available, and total disk space</li>
                    <li><strong>Process metrics:</strong> Number of running processes</li>
                    <li><strong>OpenTelemetry format:</strong> Standard metric naming and labels</li>
                    <li><strong>Automatic updates:</strong> Metrics refreshed every 30 seconds</li>
                </ul>
            </div>

            <h2>Available Endpoints:</h2>
            <div class="endpoint">
                <a href="/metrics">/metrics</a>
                <div class="description">Prometheus metrics in text format</div>
            </div>
            <div class="endpoint">
                <a href="/health">/health</a>
                <div class="description">Health check endpoint (JSON)</div>
            </div>
            <div class="endpoint">
                <a href="/status">/status</a>
                <div class="description">Detailed status information (JSON)</div>
            </div>
            <div class="endpoint">
                <a href="/debug/metrics-raw">/debug/metrics-raw</a>
                <div class="description">Raw metrics data for debugging</div>
            </div>
            <div class="endpoint">
                <a href="/debug/collect-now">/debug/collect-now</a>
                <div class="description">Manually trigger metrics collection</div>
            </div>

            <h2>Configuration:</h2>
            <div class="config-section">
                <ul>
                    <li><strong>Collection Interval:</strong> """ + str(COLLECTION_INTERVAL) + """ seconds</li>
                    <li><strong>Metrics File:</strong> """ + METRICS_FILE + """</li>
                    <li><strong>Hostname:</strong> """ + os.uname().nodename + """</li>
                </ul>
            </div>

            <h2>Debug Tools:</h2>
            <button id="collect-now-btn" class="button" onclick="collectNow()">Collect Now</button>
            <button class="button" onclick="loadStatus()">Refresh Status</button>
            
            <h3>Collection Output:</h3>
            <div id="collect-output" class="debug-output">Click "Collect Now" to manually trigger metrics collection</div>
            
            <h3>Status Information:</h3>
            <div id="status-info" class="debug-output">Loading status...</div>
        </div>
    </body>
    </html>
    """
    return html

def validate_configuration():
    """Validate configuration before starting"""
    errors = []
    
    # Check if metrics directory exists and is writable
    metrics_dir = os.path.dirname(METRICS_FILE)
    if not os.path.exists(metrics_dir):
        try:
            os.makedirs(metrics_dir, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create metrics directory {metrics_dir}: {e}")
    elif not os.access(metrics_dir, os.W_OK):
        errors.append(f"Metrics directory not writable: {metrics_dir}")
    
    return errors

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    app.state.start_time = time.time()
    
    log_message("Starting LXC Metrics Exporter v1.0.0")
    log_message(f"Configuration: Collection interval={COLLECTION_INTERVAL}s")
    
    # Validate configuration
    config_errors = validate_configuration()
    if config_errors:
        log_message("Configuration errors found:", "ERROR")
        for error in config_errors:
            log_message(f"  - {error}", "ERROR")
        return
    
    # Run initial metrics collection
    log_message("Running initial metrics collection...")
    try:
        start_time = time.time()
        
        # Collect metrics
        fresh_metrics = collect_metrics_python()
        
        # Write to file
        if write_metrics_file(fresh_metrics):
            # Update global metrics
            global current_metrics, last_update_time
            with metrics_lock:
                current_metrics = fresh_metrics
                last_update_time = time.time()
            
            collection_time = time.time() - start_time
            log_message(f"Initial metrics collection completed in {collection_time:.2f}s")
        else:
            log_message("Initial metrics collection failed: Could not write file", "ERROR")
        
    except Exception as e:
        log_message(f"Initial metrics collection failed: {e}", "ERROR")
        log_message("Web server will start but metrics may not be available immediately", "WARNING")
    
    # Start the background metrics collection thread
    log_message("Starting background metrics collection thread")
    metrics_thread = threading.Thread(target=metrics_collection_thread, daemon=True)
    metrics_thread.start()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9100)
