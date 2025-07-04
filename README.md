# Platform-Agnostic Metrics Exporter

A platform-agnostic Python-based metrics exporter that intelligently adapts between LXC containers and Proxmox hosts, with configurable export formats (Prometheus or OpenTelemetry OTLP).

## Features

- 🌐 **Platform-Agnostic**: Automatically detects LXC containers vs Proxmox hosts and adapts collection strategies
- 🎯 **Prometheus Compliant**: Follows Prometheus naming conventions and best practices
- 🔄 **Configurable Export**: Choose between Prometheus file format OR OpenTelemetry OTLP export (mutually exclusive)
- 🧩 **Environment-Aware**: Strategy pattern for optimal collection methods per environment
- 🚀 **High Performance**: Threaded metrics collection with configurable intervals
- 📊 **Rich Metrics**: Memory, CPU, disk, network, and process metrics with proper labels
- 🔒 **Production Ready**: Systemd service integration with proper user isolation
- 🏷️ **Smart Labeling**: Environment-aware instance identification
- 🏠 **Proxmox Integration**: Multi-container monitoring and cluster information when running on Proxmox hosts

## Metrics

All metrics follow Prometheus naming conventions with the `node_` prefix:

### Memory Metrics
- `node_memory_usage_bytes` - Memory currently in use
- `node_memory_free_bytes` - Amount of free memory  
- `node_memory_available_bytes` - Memory available for allocation
- `node_memory_total_bytes` - Total memory

### Filesystem Metrics
- `node_filesystem_usage_bytes{device,mountpoint,fstype}` - Filesystem space used
- `node_filesystem_avail_bytes{device,mountpoint,fstype}` - Filesystem space available
- `node_filesystem_size_bytes{device,mountpoint,fstype}` - Filesystem total size

### Process Metrics
- `node_processes_total` - Number of processes

### Labels
All metrics include standard labels:
- `host_name` - Container host name
- `container_id` - LXC container ID
- `instance` - Instance identifier (format: `hostname:container_id`)

## Quick Start

### 1. Installation

```bash
# Clone the repository (if not already done)
git clone https://github.com/cougz/metrics-exporters.git
cd metrics-exporters

# Create virtual environment
python3 -m venv venv

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Create directories
sudo mkdir -p /opt/metrics-exporters/{data,logs}

# Create otelcol user
sudo useradd -r -s /bin/false otelcol

# Set permissions
sudo chown -R otelcol:otelcol /opt/metrics-exporters
```

### 2. Service Configuration

**Choose your export format by editing the systemd service file:**

```bash
# Install systemd service
sudo cp metrics-exporter.service /etc/systemd/system/

# Edit the service file to configure export format
sudo nano /etc/systemd/system/metrics-exporter.service
```

**For OTLP Export (default):**
```ini
Environment=EXPORT_FORMAT=otlp
Environment=OTEL_ENDPOINT=your-otel-collector:4317
Environment=OTEL_SERVICE_NAME=metrics-exporter
Environment=OTEL_SERVICE_VERSION=1.0.0
Environment=OTEL_INSECURE=true
```

**For Prometheus Export:**
```ini
Environment=EXPORT_FORMAT=prometheus
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable metrics-exporter.service
sudo systemctl start metrics-exporter.service
```

### 3. Verification

```bash
# Check service status
sudo systemctl status metrics-exporter.service

# Test endpoints
curl http://localhost:9100/health
curl http://localhost:9100/status

# For Prometheus export format only:
curl http://localhost:9100/metrics
```

## Configuration

### Export Format Configuration

The exporter supports **mutually exclusive** export formats:

#### OTLP Format (default)
Sends metrics directly to an OpenTelemetry collector via gRPC:

```ini
Environment=EXPORT_FORMAT=otlp
Environment=OTEL_ENDPOINT=otel-collector:4317
Environment=OTEL_SERVICE_NAME=metrics-exporter
Environment=OTEL_SERVICE_VERSION=1.0.0
Environment=OTEL_INSECURE=true
```

#### Prometheus Format
Writes metrics to a file that can be scraped by Prometheus:

```ini
Environment=EXPORT_FORMAT=prometheus
Environment=PROMETHEUS_FILE=/opt/metrics-exporters/data/metrics.prom
```

### Other Configuration Options

```ini
# Core Settings
Environment=COLLECTION_INTERVAL=30
Environment=METRICS_PORT=9100

# Collectors
Environment=ENABLED_COLLECTORS=memory,disk,process

# Logging
Environment=LOG_LEVEL=INFO

# Instance Identification (optional - auto-generated if not specified)
Environment=INSTANCE_ID=custom-instance-id
Environment=SERVICE_INSTANCE_ID=custom-service-instance-id
```

### OpenTelemetry Collector Configuration (OTLP Export Format - Default)

Configure your OTEL collector to receive metrics on the gRPC endpoint:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

### Prometheus Scraping (Prometheus Export Format Only)

Add this job to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'lxc-metrics'
    static_configs:
      - targets: ['your-lxc-host:9100']
    scrape_interval: 30s
    metrics_path: /metrics
```

## API Endpoints

- `GET /metrics` - Prometheus metrics endpoint (only available with `EXPORT_FORMAT=prometheus`)
- `GET /health` - Health check endpoint
- `GET /status` - Detailed service status including export format
- `GET /collectors` - List of available collectors
- `POST /collect` - Manually trigger metrics collection

## Architecture

The application uses a **clean architecture** with configurable export formats:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI       │    │   Collectors    │    │   Single        │
│   Web Server    │◄───┤   Registry      │◄───┤   Exporter      │
│                 │    │                 │    │   (Format-based)│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         └──────────────►│   Background    │◄─────────────┘
                        │   Collection    │
                        │   Loop          │
                        └─────────────────┘
```

### Export Format Decision Tree

```
Configuration
     │
     ▼
┌─────────────────┐
│ EXPORT_FORMAT?  │
├─────────────────┤
│ prometheus      │──────► CleanPrometheusExporter ──► File Export
│ otlp           │──────► CleanOTLPExporter ──────► gRPC Export
└─────────────────┘
```

## Development

### Project Structure
```
lxc/
├── app/
│   ├── __init__.py
│   └── server.py              # FastAPI application
├── collectors/
│   ├── __init__.py
│   ├── base.py               # Base collector class
│   ├── memory.py             # Memory metrics collector
│   ├── disk.py               # Disk metrics collector
│   └── process.py            # Process metrics collector
├── metrics/
│   ├── __init__.py
│   ├── models.py             # Metric data models with ExportFormat enum
│   ├── registry.py           # Collector registry
│   └── exporters/
│       ├── __init__.py
│       ├── base.py           # BaseExporter abstraction and factory
│       ├── prometheus_clean.py  # Clean Prometheus file export
│       └── otlp_clean.py     # Clean OTLP gRPC export
├── middleware/
│   ├── __init__.py
│   └── security.py           # Security middleware
├── utils/
│   ├── __init__.py
│   └── container.py          # Container utility functions
├── config.py                 # Configuration management
├── logging_config.py         # Structured logging setup
├── main.py                   # Application entry point
├── requirements.txt          # Python dependencies
└── metrics-exporter.service # Systemd service
```

### Adding New Collectors

1. Create a new collector class inheriting from `BaseCollector`
2. Implement the `collect()` method returning `List[MetricValue]`
3. Place the file in the `collectors/` directory
4. The registry will auto-discover it

Example:
```python
from collectors.base import BaseCollector
from metrics.models import MetricValue, MetricType

class NetworkCollector(BaseCollector):
    def __init__(self, config=None):
        super().__init__(config, "network", "LXC container network metrics")
    
    def collect(self) -> List[MetricValue]:
        # Implement collection logic
        return [
            MetricValue(
                name="node_network_bytes_received",
                value=bytes_received,
                labels=self.get_standard_labels({"interface": "eth0"}),
                help_text="Network bytes received",
                metric_type=MetricType.COUNTER,
                unit="bytes"
            )
        ]
```

### Testing Different Export Formats

```bash
# Test OTLP format (default)
sudo systemctl stop metrics-exporter
# Edit service file: Environment=EXPORT_FORMAT=otlp
# Edit service file: Environment=OTEL_ENDPOINT=your-collector:4317
sudo systemctl start metrics-exporter
curl http://localhost:9100/health  # Check exporter_healthy status

# Test Prometheus format
sudo systemctl stop metrics-exporter
# Edit service file: Environment=EXPORT_FORMAT=prometheus
sudo systemctl start metrics-exporter
curl http://localhost:9100/metrics
```

## Troubleshooting

### Common Issues

1. **Service fails to start**
   ```bash
   sudo journalctl -u metrics-exporter.service -f
   ```

2. **Permission denied errors**
   ```bash
   sudo chown -R otelcol:otelcol /opt/metrics-exporters
   sudo mkdir -p /opt/metrics-exporters/{data,logs}
   ```

3. **Export format issues**
   - For Prometheus: Check if `/metrics` endpoint returns data
   - For OTLP: Check `exporter_healthy` status in `/health` endpoint
   - Verify `EXPORT_FORMAT` environment variable is set correctly

4. **OTLP connection failures**
   - Check endpoint connectivity: `telnet otel-collector-host 4317`
   - Verify OTEL_ENDPOINT format (no http:// prefix)
   - Ensure firewall rules allow gRPC traffic

### Logs

```bash
# Service logs
sudo journalctl -u metrics-exporter.service -f

# Application logs (structured JSON)
sudo -u otelcol tail -f /opt/metrics-exporters/logs/app.log
```

### Health Monitoring

```bash
# Check overall health
curl http://localhost:9100/health

# Check detailed status including export format
curl http://localhost:9100/status | jq '.exporter'
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request