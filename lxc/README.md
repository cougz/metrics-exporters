# LXC Metrics Exporter

A Python-based Prometheus exporter for LXC container metrics with OpenTelemetry SDK integration.

## Features

- 🎯 **Prometheus Compliant**: Follows Prometheus naming conventions and best practices
- 🔄 **Dual Export**: Supports both Prometheus file format and OpenTelemetry OTLP export
- 🧩 **Modular Architecture**: Plugin-based collector system for easy extensibility
- 🚀 **High Performance**: Threaded metrics collection with configurable intervals
- 📊 **Rich Metrics**: Memory, disk, and process metrics with proper labels
- 🔒 **Production Ready**: Systemd service integration with proper user isolation

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

## Quick Start

### 1. Installation

```bash
# Clone the repository (if not already done)
git clone https://github.com/cougz/metrics-exporters.git
cd metrics-exporters/lxc

# Create directory
sudo mkdir -p /opt/lxc-metrics-exporter

# Copy files from lxc subdirectory
sudo cp -r . /opt/lxc-metrics-exporter/

# Create virtual environment
sudo python3 -m venv /opt/lxc-metrics-exporter/venv

# Install dependencies
sudo /opt/lxc-metrics-exporter/venv/bin/pip install -r /opt/lxc-metrics-exporter/requirements.txt

# Create otelcol user
sudo useradd -r -s /bin/false otelcol

# Set permissions
sudo chown -R otelcol:otelcol /opt/lxc-metrics-exporter
```

### 2. Service Configuration

```bash
# Install systemd service (already copied from lxc subdirectory)
sudo cp /opt/lxc-metrics-exporter/lxc-metrics-exporter.service /etc/systemd/system/

# Edit the service file to configure your OpenTelemetry endpoint (optional)
sudo nano /etc/systemd/system/lxc-metrics-exporter.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable lxc-metrics-exporter.service
sudo systemctl start lxc-metrics-exporter.service
```

### 3. Verification

```bash
# Check service status
sudo systemctl status lxc-metrics-exporter.service

# Test endpoints
curl http://localhost:9100/health
curl http://localhost:9100/metrics
curl http://localhost:9100/status
```

## Configuration

### Environment Variables

Configure the exporter through environment variables in the systemd service file:

```ini
# Core Settings
Environment=COLLECTION_INTERVAL=30
Environment=METRICS_PORT=9100

# Prometheus Export
Environment=PROMETHEUS_ENABLED=true
Environment=PROMETHEUS_FILE=/opt/lxc-metrics-exporter/data/metrics.prom

# OpenTelemetry Export
Environment=OTEL_ENABLED=true
Environment=OTEL_ENDPOINT=your-otel-collector:4317
Environment=OTEL_SERVICE_NAME=lxc-metrics-exporter
Environment=OTEL_SERVICE_VERSION=1.0.0
Environment=OTEL_INSECURE=true

# Collectors
Environment=ENABLED_COLLECTORS=memory,disk,process
```

### Prometheus Scraping

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

- `GET /metrics` - Prometheus metrics endpoint
- `GET /health` - Health check endpoint
- `GET /status` - Detailed service status
- `GET /collectors` - List of available collectors

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI       │    │   Collectors    │    │   Exporters     │
│   Web Server    │◄───┤   Registry      │◄───┤   (Prometheus   │
│                 │    │                 │    │   OpenTelemetry)│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │
         │              ┌─────────────────┐
         └──────────────►│   Background    │
                        │   Collection    │
                        │   Thread        │
                        └─────────────────┘
```

## Development

### Project Structure
```
lxc/
├── app/
│   ├── __init__.py
│   └── server.py           # FastAPI application
├── collectors/
│   ├── __init__.py
│   ├── base.py            # Base collector class
│   ├── memory.py          # Memory metrics collector
│   ├── disk.py            # Disk metrics collector
│   └── process.py         # Process metrics collector
├── metrics/
│   ├── __init__.py
│   ├── models.py          # Metric data models
│   ├── registry.py        # Collector registry
│   └── exporters/
│       ├── __init__.py
│       ├── prometheus.py  # Prometheus file export
│       └── opentelemetry.py # OpenTelemetry export
├── utils/
│   └── __init__.py
├── config.py              # Configuration management
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
└── lxc-metrics-exporter.service # Systemd service
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
    @property
    def name(self) -> str:
        return "network"
    
    def collect(self) -> List[MetricValue]:
        # Implement collection logic
        return [MetricValue(...)]
```

## Troubleshooting

### Common Issues

1. **Service fails to start**
   ```bash
   sudo journalctl -u lxc-metrics-exporter.service -f
   ```

2. **Permission denied errors**
   ```bash
   sudo chown -R otelcol:otelcol /opt/lxc-metrics-exporter
   ```

3. **OpenTelemetry export failures**
   - Check endpoint connectivity
   - Verify OTEL_ENDPOINT format
   - Ensure firewall rules allow traffic

### Logs

```bash
# Service logs
sudo journalctl -u lxc-metrics-exporter.service -f

# Application logs
sudo -u otelcol tail -f /opt/lxc-metrics-exporter/logs/app.log
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request