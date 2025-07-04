"""Simplified metric models - OTLP only"""
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

class MetricType(Enum):
    """OpenTelemetry metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"

@dataclass
class MetricValue:
    """Single metric value for OTLP export"""
    name: str
    value: float
    labels: Dict[str, str]
    help_text: str
    metric_type: MetricType = MetricType.GAUGE
    unit: str = "1"
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        # Ensure labels is never None
        if self.labels is None:
            self.labels = {}