#!/usr/bin/env python3
"""Test script to show exactly what OTLP metrics are being sent"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, '/opt/metrics-exporters')

from config import Config
from metrics.registry_enhanced import EnvironmentAwareMetricsRegistry
from metrics.transformer import MetricTransformer

async def main():
    # Load config
    config = Config()
    
    # Create registry and collect metrics
    registry = EnvironmentAwareMetricsRegistry(config)
    raw_metrics = await registry.collect_all_async()
    
    print(f"=== RAW METRICS ({len(raw_metrics)}) ===")
    for metric in raw_metrics[:5]:
        print(f"  {metric.name} = {metric.value} {metric.labels}")
    
    # Apply transformations
    transformer = MetricTransformer(config)
    transformed = transformer.transform_metrics(raw_metrics)
    enhanced = transformer.add_calculated_metrics(transformed)
    final = transformer.remove_redundant_metrics(enhanced)
    
    print(f"\n=== TRANSFORMED METRICS ({len(final)}) ===")
    for metric in final[:10]:
        print(f"  {metric.name} = {metric.value} {metric.labels}")
    
    # Show resource attributes
    resource_attrs = config.get_otel_resource_attributes()
    resource_attrs.update(transformer.get_resource_attributes())
    
    print(f"\n=== RESOURCE ATTRIBUTES ===")
    for key, value in resource_attrs.items():
        print(f"  {key} = {value}")
    
    print(f"\n=== SUMMARY ===")
    print(f"Original metrics: {len(raw_metrics)}")
    print(f"Final metrics: {len(final)}")
    print(f"Transformation enabled: {config.use_otel_semconv}")
    print(f"OTLP endpoint: {config.otel_endpoint}")

if __name__ == "__main__":
    asyncio.run(main())