"""Metric data models"""
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class MetricType(Enum):
    """Prometheus metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """Represents a single metric value"""
    name: str
    value: float
    labels: Dict[str, str]
    help_text: str
    metric_type: MetricType = MetricType.GAUGE
    unit: str = "1"
    timestamp: Optional[float] = None
    
    def to_prometheus_line(self) -> str:
        """Convert to Prometheus exposition format"""
        labels_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_pairs) + "}"
        
        return f"{self.name}{labels_str} {self.value}"
    
    def to_prometheus_with_type(self) -> str:
        """Convert to Prometheus format with TYPE comment"""
        lines = []
        lines.append(f"# TYPE {self.name} {self.metric_type.value}")
        lines.append(self.to_prometheus_line())
        return "\n".join(lines)