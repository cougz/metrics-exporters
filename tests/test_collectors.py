"""Tests for collector modules"""
import pytest
from unittest.mock import patch, Mock
from pathlib import Path

from config import Config
from collectors.base import BaseCollector
from collectors.memory import MemoryCollector
from collectors.disk import DiskCollector
from collectors.process import ProcessCollector


class MockCollector(BaseCollector):
    """Mock collector for testing base functionality"""
    
    def __init__(self, config: Config):
        super().__init__(config, "mock", "Mock collector for testing")
    
    def collect(self):
        return [
            {"name": "mock_metric", "value": 1.0, "labels": {"test": "value"}}
        ]


class TestBaseCollector:
    """Test base collector functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.config = Config()
        self.collector = MockCollector(self.config)
    
    def test_collector_initialization(self):
        """Test collector initialization"""
        assert self.collector.name == "mock"
        assert self.collector.help == "Mock collector for testing"
        assert self.collector.config == self.config
    
    def test_collector_enabled_check(self):
        """Test collector enabled check"""
        # Mock collector is not in default enabled collectors
        assert self.collector.is_enabled() is False
        
        # Add to enabled collectors
        self.config.enabled_collectors.append("mock")
        assert self.collector.is_enabled() is True
    
    def test_collector_metrics_collection(self):
        """Test metrics collection"""
        metrics = self.collector.collect()
        
        assert len(metrics) == 1
        assert metrics[0]["name"] == "mock_metric"
        assert metrics[0]["value"] == 1.0
        assert metrics[0]["labels"]["test"] == "value"


class TestMemoryCollector:
    """Test memory collector"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.config = Config()
        self.collector = MemoryCollector(self.config)
    
    def test_memory_collector_initialization(self):
        """Test memory collector initialization"""
        assert self.collector.name == "memory"
        assert "memory" in self.collector.help.lower()
    
    @patch('psutil.virtual_memory')
    def test_memory_metrics_collection(self, mock_virtual_memory):
        """Test memory metrics collection"""
        # Mock psutil memory data
        mock_memory = Mock()
        mock_memory.total = 8589934592  # 8GB
        mock_memory.available = 4294967296  # 4GB
        mock_memory.percent = 50.0
        mock_memory.used = 4294967296  # 4GB
        mock_memory.free = 4294967296  # 4GB
        mock_virtual_memory.return_value = mock_memory
        
        metrics = self.collector.collect()
        
        assert len(metrics) > 0
        metric_names = [m["name"] for m in metrics]
        assert "lxc_memory_total_bytes" in metric_names
        assert "lxc_memory_available_bytes" in metric_names
        assert "lxc_memory_usage_percent" in metric_names
    
    def test_memory_collector_enabled_by_default(self):
        """Test memory collector is enabled by default"""
        assert self.collector.is_enabled() is True


class TestDiskCollector:
    """Test disk collector"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.config = Config()
        self.collector = DiskCollector(self.config)
    
    def test_disk_collector_initialization(self):
        """Test disk collector initialization"""
        assert self.collector.name == "disk"
        assert "disk" in self.collector.help.lower()
    
    @patch('psutil.disk_usage')
    def test_disk_metrics_collection(self, mock_disk_usage):
        """Test disk metrics collection"""
        # Mock psutil disk usage data
        mock_usage = Mock()
        mock_usage.total = 107374182400  # 100GB
        mock_usage.used = 53687091200   # 50GB
        mock_usage.free = 53687091200   # 50GB
        mock_disk_usage.return_value = mock_usage
        
        metrics = self.collector.collect()
        
        assert len(metrics) > 0
        metric_names = [m["name"] for m in metrics]
        assert "lxc_disk_total_bytes" in metric_names
        assert "lxc_disk_used_bytes" in metric_names
        assert "lxc_disk_free_bytes" in metric_names
    
    def test_disk_collector_enabled_by_default(self):
        """Test disk collector is enabled by default"""
        assert self.collector.is_enabled() is True


class TestProcessCollector:
    """Test process collector"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.config = Config()
        self.collector = ProcessCollector(self.config)
    
    def test_process_collector_initialization(self):
        """Test process collector initialization"""
        assert self.collector.name == "process"
        assert "process" in self.collector.help.lower()
    
    @patch('psutil.process_iter')
    def test_process_metrics_collection(self, mock_process_iter):
        """Test process metrics collection"""
        # Mock psutil process data
        mock_process = Mock()
        mock_process.info = {
            'pid': 1234,
            'name': 'test_process',
            'cpu_percent': 5.0,
            'memory_percent': 2.5,
            'status': 'running'
        }
        mock_process_iter.return_value = [mock_process]
        
        metrics = self.collector.collect()
        
        assert len(metrics) > 0
        metric_names = [m["name"] for m in metrics]
        assert "lxc_process_count" in metric_names
        assert "lxc_process_cpu_percent" in metric_names
        assert "lxc_process_memory_percent" in metric_names
    
    def test_process_collector_enabled_by_default(self):
        """Test process collector is enabled by default"""
        assert self.collector.is_enabled() is True
    
    @patch('psutil.process_iter')
    def test_process_collection_with_exception(self, mock_process_iter):
        """Test process collection handles exceptions gracefully"""
        # Mock process that raises exception
        mock_process = Mock()
        mock_process.info.side_effect = Exception("Process access denied")
        mock_process_iter.return_value = [mock_process]
        
        # Should not raise exception
        metrics = self.collector.collect()
        
        # Should still return some metrics (at least process count)
        assert len(metrics) >= 1