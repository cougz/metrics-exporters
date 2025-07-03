# Metrics Exporters

A collection of custom metrics exporters for various infrastructure components, supporting multiple export formats including Prometheus and OpenTelemetry.

## Available Exporters

### LXC Metrics Exporter

A Python-based metrics exporter for LXC containers that provides comprehensive monitoring data following Prometheus best practices.

📁 **Location**: [`lxc/`](./lxc/)

🔧 **Features**:
- Prometheus-compliant metric naming
- OpenTelemetry SDK integration
- Dual export (Prometheus file + OTLP)
- Modular collector architecture
- RESTful API endpoints

📊 **Metrics**:
- Container memory usage, free, available, and total
- Filesystem usage, available space, and total size
- Process count

🚀 **Quick Start**: See [LXC Exporter README](./lxc/README.md)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see individual exporter directories for specific licensing information.