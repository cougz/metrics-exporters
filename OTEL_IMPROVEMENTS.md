# OpenTelemetry Best Practices Implementation

## Overview

This document summarizes the OpenTelemetry best practices implemented in the metrics exporter system. The implementation transforms your existing 81 Prometheus-style metrics into approximately 15-20 well-structured OpenTelemetry semantic metrics while maintaining full observability coverage.

## Key Improvements

### 1. Semantic Naming Conventions ✅

**Before (Prometheus style):**
```
node_cpu_count
node_cpu_usage_percent
node_memory_total_bytes
node_memory_free_bytes
node_disk_read_bytes_total
node_network_receive_bytes_total
```

**After (OpenTelemetry semantic):**
```
system.cpu.logical.count
system.cpu.utilization
system.memory.usage (with state="total|used|free")
system.disk.io (with direction="read|write")
system.network.io (with direction="receive|transmit")
```

### 2. Metric Consolidation with Labels ✅

**Before:** Multiple separate metrics
```
node_memory_total_bytes
node_memory_free_bytes
node_memory_usage_bytes
node_memory_available_bytes
```

**After:** Single metric with state labels
```
system.memory.usage
- state="total"
- state="free"
- state="used"
- state="available"
```

### 3. Proper Unit Standardization ✅

**Before:**
- Inconsistent units (bytes, percent, etc.)
- No unit metadata

**After:**
- Standardized OpenTelemetry units
- `By` for bytes
- `1` for ratios/percentages (converted from 0-100% to 0-1)
- `By/s` for byte rates
- `Hz` for frequencies

### 4. Resource Attributes vs Metric Labels ✅

**Before:** Host information as metric labels
```
node_cpu_usage_percent{hostname="web-01", instance="web-01:abc123"}
```

**After:** Host information as resource attributes
```
Resource: {
  "service.name": "lxc-metrics-exporter",
  "service.version": "1.0.0", 
  "service.instance.id": "web-01:abc123",
  "host.name": "web-01"
}
Metric: system.cpu.utilization
```

### 5. Calculated Utilization Metrics ✅

**New metrics automatically calculated:**
- `system.memory.utilization` (from used/total)
- `system.filesystem.utilization` (from used/total per filesystem)
- `system.cpu.utilization` (from 1 - idle_ratio)

### 6. Redundant Metric Removal ✅

**Removed redundant metrics:**
- `node_zfs_pool_capacity_percent` (replaced by calculated utilization)
- Duplicate percentage metrics where ratios are now provided

## Implementation Details

### Configuration

The feature is controlled by the `use_otel_semconv` configuration option:

```python
# config.py
use_otel_semconv: bool = Field(default=True, description="Use OpenTelemetry semantic conventions")
```

### Core Components

1. **`metrics/semantic_conventions.py`** - Mapping definitions
2. **`metrics/transformer.py`** - Transformation logic
3. **`metrics/exporters/opentelemetry.py`** - Updated exporter

### Metric Transformations

#### CPU Metrics
| Prometheus | OpenTelemetry | Unit | Labels |
|------------|---------------|------|--------|
| `node_cpu_count` | `system.cpu.logical.count` | `1` | - |
| `node_cpu_usage_percent` | `system.cpu.utilization` | `1` | - |
| `node_cpu_user_percent` | `system.cpu.time` | `1` | `state="user"` |
| `node_cpu_system_percent` | `system.cpu.time` | `1` | `state="system"` |
| `node_load1` | `system.cpu.load_average.1m` | `1` | - |

#### Memory Metrics
| Prometheus | OpenTelemetry | Unit | Labels |
|------------|---------------|------|--------|
| `node_memory_total_bytes` | `system.memory.usage` | `By` | `state="total"` |
| `node_memory_free_bytes` | `system.memory.usage` | `By` | `state="free"` |
| `node_memory_usage_bytes` | `system.memory.usage` | `By` | `state="used"` |
| *(calculated)* | `system.memory.utilization` | `1` | - |

#### Disk Metrics
| Prometheus | OpenTelemetry | Unit | Labels |
|------------|---------------|------|--------|
| `node_disk_read_bytes_total` | `system.disk.io` | `By` | `direction="read"` |
| `node_disk_written_bytes_total` | `system.disk.io` | `By` | `direction="write"` |
| `node_disk_reads_completed_total` | `system.disk.operations` | `{operation}` | `direction="read"` |

#### Network Metrics
| Prometheus | OpenTelemetry | Unit | Labels |
|------------|---------------|------|--------|
| `node_network_receive_bytes_total` | `system.network.io` | `By` | `direction="receive"` |
| `node_network_transmit_bytes_total` | `system.network.io` | `By` | `direction="transmit"` |
| `node_network_receive_errors_total` | `system.network.errors` | `1` | `direction="receive"` |

## Benefits

### 1. Reduced Metric Count
- **Before:** 81 individual metrics
- **After:** ~15-20 consolidated metrics
- **Improvement:** ~75% reduction in metric count

### 2. Improved Query Efficiency
- Consolidated metrics enable efficient queries across dimensions
- Example: `system.memory.usage` can show all memory states in one query

### 3. Better Observability
- Standardized naming makes dashboards portable
- Automatic utilization calculations provide immediate insights
- Resource attributes reduce metric cardinality

### 4. OpenTelemetry Compliance
- Follows official OpenTelemetry semantic conventions
- Compatible with OpenTelemetry collectors and backends
- Future-proof for OpenTelemetry ecosystem tools

## Usage

### Enable OpenTelemetry Semantic Conventions

```bash
# Set environment variable
export USE_OTEL_SEMCONV=true

# Or in configuration
use_otel_semconv: true
```

### Backwards Compatibility

The transformation only applies when:
1. `use_otel_semconv=true` is set
2. Using OTLP export format

Prometheus format exports remain unchanged for backwards compatibility.

### Testing

Run the comprehensive test suite:

```bash
sudo /opt/metrics-exporters/venv/bin/python3 test_otel_conventions.py
```

## Migration Guide

### For Existing Dashboards

If you have existing dashboards using Prometheus metric names:

1. **Gradual Migration:** Keep `use_otel_semconv=false` initially
2. **Update Queries:** Replace old metric names with new semantic names
3. **Update Labels:** Use consolidated state/direction labels
4. **Enable Feature:** Set `use_otel_semconv=true`

### Example Query Updates

**Before:**
```promql
node_memory_usage_bytes / node_memory_total_bytes
```

**After:**
```promql
system_memory_utilization
# or
system_memory_usage{state="used"} / system_memory_usage{state="total"}
```

## Verification

The implementation includes comprehensive tests that verify:
- ✅ Semantic naming transformations
- ✅ Unit standardization
- ✅ Metric consolidation
- ✅ Calculated metrics generation
- ✅ Resource attribute extraction
- ✅ Percentage-to-ratio conversion

## Future Enhancements

1. **Additional Semantic Metrics:** Add more OpenTelemetry semantic metrics as they become available
2. **Custom Transformations:** Allow custom metric transformations via configuration
3. **Validation:** Add validation for OpenTelemetry compliance
4. **Performance Monitoring:** Track transformation performance impact

## References

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OpenTelemetry Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/)
- [System Metrics Conventions](https://opentelemetry.io/docs/specs/semconv/system/system-metrics/)