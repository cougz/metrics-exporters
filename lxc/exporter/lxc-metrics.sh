#!/bin/bash

METRICS_OUTPUT_FILE="/opt/lxc-metrics/exporter/lxc_metrics.prom"
TEMP_OUTPUT_FILE="${METRICS_OUTPUT_FILE}.tmp"

mkdir -p "$(dirname "$METRICS_OUTPUT_FILE")"

output_metric() {
    local metric_name=$1
    local metric_type=$2
    local value=$3
    local additional_labels=$4

    if [[ -z "$value" ]] || ! [[ "$value" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
        return
    fi

    echo "# TYPE $metric_name $metric_type"
    echo "${metric_name}{${additional_labels}} $value"
}

{
    echo "# OpenTelemetry metrics for LXC"
    echo "# Generated at $(/bin/date -Iseconds)"

    # === Memory Metrics ===
    # Check if we can get container memory from cgroups
    CGROUP_MEMORY_LIMIT=""
    CGROUP_MEMORY_USAGE=""
    
    if [ -f "/sys/fs/cgroup/memory.max" ]; then
        CGROUP_MEMORY_LIMIT=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
        CGROUP_MEMORY_USAGE=$(cat /sys/fs/cgroup/memory.current 2>/dev/null)
    fi
    
    # If cgroup shows unlimited, try to detect actual container limits
    if [ "$CGROUP_MEMORY_LIMIT" = "max" ] || [ -z "$CGROUP_MEMORY_LIMIT" ]; then
        # Check if /proc/meminfo shows container-specific memory
        if [ -f "/proc/meminfo" ]; then
            PROC_TOTAL_KB=$(grep "MemTotal:" /proc/meminfo | awk '{print $2}')
            PROC_AVAILABLE_KB=$(grep "MemAvailable:" /proc/meminfo | awk '{print $2}')
            
            TOTAL_MEM=$((PROC_TOTAL_KB * 1024))
            
            # If total memory is reasonable container size (< 10GB), use it
            if [ "$TOTAL_MEM" -lt 10737418240 ]; then
                echo "# Debug: Using /proc/meminfo container memory: $TOTAL_MEM bytes"
                
                # Get current usage from cgroup if available
                if [ -n "$CGROUP_MEMORY_USAGE" ]; then
                    USED_MEM="$CGROUP_MEMORY_USAGE"
                else
                    # Calculate used memory
                    PROC_FREE_KB=$(grep "MemFree:" /proc/meminfo | awk '{print $2}')
                    PROC_BUFFERS_KB=$(grep "Buffers:" /proc/meminfo | awk '{print $2}')
                    PROC_CACHED_KB=$(grep "Cached:" /proc/meminfo | awk '{print $2}')
                    
                    USED_MEM=$(( (PROC_TOTAL_KB - PROC_FREE_KB - PROC_BUFFERS_KB - PROC_CACHED_KB) * 1024 ))
                fi
                
                FREE_MEM=$((TOTAL_MEM - USED_MEM))
                AVAILABLE_MEM=$((PROC_AVAILABLE_KB * 1024))
                
                output_metric "system_memory_usage_bytes" "gauge" "$USED_MEM" "state=\"used\""
                output_metric "system_memory_usage_bytes" "gauge" "$FREE_MEM" "state=\"free\""
                output_metric "system_memory_usage_bytes" "gauge" "$AVAILABLE_MEM" "state=\"available\""
                output_metric "system_memory_total_bytes" "gauge" "$TOTAL_MEM" ""
                output_metric "lxc_memory_usage_bytes" "gauge" "$USED_MEM" ""
                
            else
                echo "# Debug: /proc/meminfo shows host memory, falling back to hardcoded 2GB"
                # Fallback to known 2GB limit with current usage from cgroup
                TOTAL_MEM=2147483648  # 2GB
                USED_MEM="$CGROUP_MEMORY_USAGE"
                FREE_MEM=$((TOTAL_MEM - USED_MEM))
                AVAILABLE_MEM="$FREE_MEM"
                
                output_metric "system_memory_usage_bytes" "gauge" "$USED_MEM" "state=\"used\""
                output_metric "system_memory_usage_bytes" "gauge" "$FREE_MEM" "state=\"free\""
                output_metric "system_memory_usage_bytes" "gauge" "$AVAILABLE_MEM" "state=\"available\""
                output_metric "system_memory_total_bytes" "gauge" "$TOTAL_MEM" ""
                output_metric "lxc_memory_usage_bytes" "gauge" "$USED_MEM" ""
            fi
        fi
    else
        # Use cgroup limits if they're set
        TOTAL_MEM="$CGROUP_MEMORY_LIMIT"
        USED_MEM="$CGROUP_MEMORY_USAGE"
        FREE_MEM=$((TOTAL_MEM - USED_MEM))
        AVAILABLE_MEM="$FREE_MEM"
        
        output_metric "system_memory_usage_bytes" "gauge" "$USED_MEM" "state=\"used\""
        output_metric "system_memory_usage_bytes" "gauge" "$FREE_MEM" "state=\"free\""
        output_metric "system_memory_usage_bytes" "gauge" "$AVAILABLE_MEM" "state=\"available\""
        output_metric "system_memory_total_bytes" "gauge" "$TOTAL_MEM" ""
        output_metric "lxc_memory_usage_bytes" "gauge" "$USED_MEM" ""
    fi

    # === Disk Usage Metrics (Best Practices) ===
    # Use df to get disk usage for root filesystem (/) only
    if /usr/bin/which df >/dev/null 2>&1; then
        # Get only the root filesystem (/) information with filesystem type
        ROOT_FS_INFO=$(/bin/df -T / 2>/dev/null | /usr/bin/tail -n 1)
        if [ $? -eq 0 ] && [ -n "$ROOT_FS_INFO" ]; then
            # df -T output: Filesystem Type 1K-blocks Used Available Use% Mounted-on
            FILESYSTEM=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $1}')
            FSTYPE=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $2}')
            SIZE_KB=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $3}')
            USED_KB=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $4}')
            AVAIL_KB=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $5}')
            MOUNTPOINT=$(echo "$ROOT_FS_INFO" | /usr/bin/awk '{print $7}')

            # Convert from kilobytes to bytes (df shows 1K-blocks)
            SIZE_BYTES=$((SIZE_KB * 1024))
            USED_BYTES=$((USED_KB * 1024))
            AVAIL_BYTES=$((AVAIL_KB * 1024))

            # Best practice labels following OpenTelemetry semantic conventions
            DISK_LABELS="device=\"$FILESYSTEM\",mountpoint=\"$MOUNTPOINT\",fstype=\"$FSTYPE\""

            echo "# Debug: Root filesystem: $FILESYSTEM ($FSTYPE) - Used: $USED_BYTES bytes, Total: $SIZE_BYTES bytes"

            # OpenTelemetry semantic conventions for disk metrics
            output_metric "system_filesystem_usage_bytes" "gauge" "$USED_BYTES" "$DISK_LABELS"
            output_metric "system_filesystem_available_bytes" "gauge" "$AVAIL_BYTES" "$DISK_LABELS"
            output_metric "system_filesystem_size_bytes" "gauge" "$SIZE_BYTES" "$DISK_LABELS"
            
            # Legacy compatibility metrics
            output_metric "lxc_disk_usage_bytes" "gauge" "$USED_BYTES" "$DISK_LABELS"
        fi
    fi

    # === Process Count Metrics ===
    if /usr/bin/which ps >/dev/null 2>&1; then
        PROCESS_COUNT=$(/bin/ps -A --no-headers 2>/dev/null | /usr/bin/wc -l)
        if [ $? -eq 0 ]; then
            output_metric "system_processes_count" "gauge" "$PROCESS_COUNT" ""
            output_metric "lxc_process_count" "gauge" "$PROCESS_COUNT" ""
        fi
    fi

    echo "# End of metrics"

} > "$TEMP_OUTPUT_FILE"

if [ -f "$TEMP_OUTPUT_FILE" ]; then
    /bin/mv "$TEMP_OUTPUT_FILE" "$METRICS_OUTPUT_FILE"
    /bin/chmod 644 "$METRICS_OUTPUT_FILE"
    /bin/chown otelcol:otelcol "$METRICS_OUTPUT_FILE" 2>/dev/null || true
fi
