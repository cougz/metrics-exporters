# Metrics Exporter

A lightweight, platform-agnostic system metrics exporter that intelligently adapts between container and host environments, with configurable export formats (Prometheus or OpenTelemetry OTLP).

## Features

- 🔍 **Environment-Aware**: Automatically detects container vs host environments and adapts collection strategies
- 🎯 **Prometheus Compliant**: Follows Prometheus naming conventions and best practices
- 🔄 **Configurable Export**: Choose between Prometheus file format OR OpenTelemetry OTLP export (mutually exclusive)
- 🧩 **Smart Collection**: Strategy pattern for optimal collection methods per environment
- 🚀 **High Performance**: Threaded metrics collection with configurable intervals
- 📊 **Rich Metrics**: Memory, CPU, disk, network, and process metrics with proper labels
- 🔒 **Production Ready**: Systemd service integration with proper user isolation
- 🏷️ **Smart Labeling**: Environment-aware instance identification

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

### ZFS Pool Metrics (Host environments only)
- `node_zfs_pool_size_bytes{pool,health}` - ZFS pool total size in bytes
- `node_zfs_pool_allocated_bytes{pool,health}` - ZFS pool allocated space in bytes
- `node_zfs_pool_free_bytes{pool,health}` - ZFS pool free space in bytes
- `node_zfs_pool_capacity_percent{pool,health}` - ZFS pool capacity as percentage
- `node_zfs_pool_fragmentation_percent{pool,health}` - ZFS pool fragmentation percentage
- `node_zfs_pool_readonly{pool,health}` - ZFS pool readonly status (1 = readonly, 0 = read-write)
- `node_zfs_pool_read_ops_per_sec{pool,health}` - ZFS pool read operations per second
- `node_zfs_pool_write_ops_per_sec{pool,health}` - ZFS pool write operations per second
- `node_zfs_pool_read_bytes_per_sec{pool,health}` - ZFS pool read bandwidth in bytes per second
- `node_zfs_pool_write_bytes_per_sec{pool,health}` - ZFS pool write bandwidth in bytes per second

### Process Metrics
- `node_processes_total` - Number of processes

### Hardware Sensor Metrics (Host environments only - unified sensors collector)
- `system.cpu.temperature{sensor.chip,sensor.type,cpu.core,cpu.package}` - CPU temperature in Celsius
- `system.cpu.temperature.threshold{sensor.chip,sensor.type,cpu.core,cpu.package,threshold.type}` - CPU temperature thresholds
- `system.cpu.temperature.alarm{sensor.chip,sensor.type,cpu.core,cpu.package}` - CPU temperature alarm state
- `system.nvme.temperature{sensor.chip,sensor.type,nvme.device,nvme.sensor}` - NVMe temperature in Celsius
- `system.nvme.temperature.threshold{sensor.chip,sensor.type,nvme.device,nvme.sensor,threshold.type}` - NVMe temperature thresholds
- `system.nvme.temperature.alarm{sensor.chip,sensor.type,nvme.device,nvme.sensor}` - NVMe temperature alarm state

### SMART Disk Metrics (Host environments only - optional smart collector)
- `disk.smart.health_status{device,model,serial,interface}` - SMART overall health (1=passed, 0=failed)
- `disk.smart.temperature{device,model,serial,interface}` - Disk temperature from SMART
- `disk.smart.power_on_hours{device,model,serial,interface}` - Total power-on hours
- `disk.smart.power_cycles{device,model,serial,interface}` - Power cycle count
- `disk.smart.attribute.raw_value{device,model,serial,interface,attribute_id,attribute_name}` - SMART attribute raw values
- `disk.nvme.critical_warning{device,model,serial}` - NVMe critical warning flags
- `disk.nvme.available_spare_percent{device,model,serial}` - NVMe available spare percentage
- `disk.nvme.percentage_used{device,model,serial}` - NVMe percentage of life used
- `disk.nvme.data_read_bytes{device,model,serial}` - Total data read in bytes
- `disk.nvme.data_written_bytes{device,model,serial}` - Total data written in bytes
- `disk.nvme.media_errors{device,model,serial}` - NVMe media error count
- `disk.nvme.unsafe_shutdowns{device,model,serial}` - NVMe unsafe shutdown count

### Labels
All metrics include standard labels:
- `host_name` - Host name
- `container_id` - Container ID (when running in containers)
- `instance` - Instance identifier (format varies by environment)

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

# Configure sudo for SMART collector (optional - only if using smart collector)
echo 'otelcol ALL=(ALL) NOPASSWD: /usr/sbin/smartctl' | sudo tee /etc/sudoers.d/metrics-exporter
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

# Collectors (auto-detected by default based on environment)
# Default collectors: memory,cpu,filesystem,network,process
# Host-only collectors: zfs (if ZFS detected), sensors (if hardware sensors detected)
# Optional collectors: smart (disabled by default, requires sudo configuration)
# To enable SMART collector: ENABLED_COLLECTORS=memory,cpu,filesystem,network,process,smart
Environment=ENABLED_COLLECTORS=memory,filesystem,process

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
  - job_name: 'system-metrics'
    static_configs:
      - targets: ['your-host:9100']
    scrape_interval: 30s
    metrics_path: /metrics
```

## API Endpoints

- `GET /metrics` - Prometheus metrics endpoint (only available with `EXPORT_FORMAT=prometheus`)
- `GET /health` - Health check endpoint
- `GET /status` - Detailed service status including export format
- `GET /collectors` - List of available collectors
- `POST /collect` - Manually trigger metrics collection

## Collectors

### Auto-detected Collectors
The system automatically detects and enables appropriate collectors based on the environment:

- **Container environments**: memory, cpu, filesystem, network, process
- **Host environments**: All above + zfs (if ZFS detected), sensors (if hardware sensors available)

### Unified Sensors Collector
The `sensors` collector replaces the previous separate `sensors_cpu` and `sensors_nvme` collectors. It uses the `sensors` command to collect all hardware temperature data and exports it using OpenTelemetry semantic conventions.

### Optional SMART Collector
The `smart` collector provides comprehensive SMART disk health data but requires:
1. Manual enablement in `ENABLED_COLLECTORS`
2. Sudo configuration (see installation section)

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
/opt/metrics-exporters/
├── app/
│   ├── __init__.py
│   └── server.py              # FastAPI application
├── collectors/
│   ├── __init__.py
│   ├── base_enhanced.py      # Environment-aware base collector
│   ├── memory_enhanced.py    # Memory metrics collector
│   ├── cpu_enhanced.py       # CPU metrics collector
│   ├── filesystem_enhanced.py # Filesystem metrics collector
│   ├── network_enhanced.py   # Network metrics collector
│   ├── process_enhanced.py   # Process metrics collector
│   ├── zfs_enhanced.py       # ZFS pool metrics (host only)
│   ├── sensors_enhanced.py   # Unified hardware sensors (host only)
│   └── smart_enhanced.py     # SMART disk data (host only, optional)
├── environment/
│   ├── __init__.py
│   ├── detection.py          # Environment detection logic
│   ├── capabilities.py       # Environment capability mapping
│   └── context.py            # Runtime environment context
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
        super().__init__(config, "network", "System network metrics")
    
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