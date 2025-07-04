"""Tests for FastAPI server module"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import httpx

from app.server import MetricsServer
from config import Config


class TestMetricsServer:
    """Test FastAPI server functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.config = Config()
        self.server = MetricsServer(self.config)
        self.client = TestClient(self.server.get_app())
    
    def test_health_endpoint_healthy(self):
        """Test health endpoint when service is healthy"""
        # Mock healthy state
        self.server.last_collection_time = 1234567890
        self.server.collection_count = 10
        self.server.collection_errors = 0
        
        with patch('time.time', return_value=1234567890 + 10):
            response = self.client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["total_collections"] == 10
            assert data["collection_errors"] == 0
    
    def test_health_endpoint_unhealthy(self):
        """Test health endpoint when service is unhealthy"""
        # Mock unhealthy state (last collection too old)
        self.server.last_collection_time = 1234567890
        self.server.collection_count = 10
        self.server.collection_errors = 0
        
        with patch('time.time', return_value=1234567890 + 100):
            response = self.client.get("/health")
            
            assert response.status_code == 503
            data = response.json()
            assert data["detail"]["status"] == "unhealthy"
    
    def test_metrics_endpoint_prometheus_enabled(self):
        """Test metrics endpoint when Prometheus is enabled"""
        mock_content = "# HELP test_metric Test metric\ntest_metric 1.0\n"
        
        with patch.object(self.server.prometheus_exporter, 'read_metrics_file', return_value=mock_content):
            response = self.client.get("/metrics")
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert response.text == mock_content
    
    def test_metrics_endpoint_prometheus_disabled(self):
        """Test metrics endpoint when Prometheus is disabled"""
        self.server.prometheus_exporter = None
        
        response = self.client.get("/metrics")
        
        assert response.status_code == 200
        assert "Prometheus export disabled" in response.text
    
    def test_status_endpoint(self):
        """Test status endpoint"""
        self.server.last_collection_time = 1234567890
        self.server.collection_count = 10
        self.server.collection_errors = 2
        
        with patch('time.time', return_value=1234567890 + 10):
            with patch('os.uname') as mock_uname:
                mock_uname.return_value.nodename = "test-host"
                
                response = self.client.get("/status")
                
                assert response.status_code == 200
                data = response.json()
                assert data["service"]["name"] == "lxc-metrics-exporter"
                assert data["service"]["hostname"] == "test-host"
                assert data["collection"]["total_collections"] == 10
                assert data["collection"]["collection_errors"] == 2
                assert data["collection"]["success_rate"] == 80.0
    
    def test_collectors_endpoint(self):
        """Test collectors endpoint"""
        mock_status = {
            "memory": {"enabled": True, "help": "Memory metrics"},
            "disk": {"enabled": True, "help": "Disk metrics"}
        }
        
        with patch.object(self.server.registry, 'get_collector_status', return_value=mock_status):
            response = self.client.get("/collectors")
            
            assert response.status_code == 200
            data = response.json()
            assert "collectors" in data
            assert "enabled_collectors" in data
            assert data["collectors"] == mock_status
    
    @pytest.mark.asyncio
    async def test_manual_collect_success(self):
        """Test manual collection endpoint success"""
        with patch.object(self.server, '_collect_metrics', new_callable=AsyncMock) as mock_collect:
            self.server.collection_count = 5
            
            async with httpx.AsyncClient(app=self.server.get_app(), base_url="http://test") as client:
                response = await client.post("/collect")
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["collection_count"] == 5
                mock_collect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_manual_collect_failure(self):
        """Test manual collection endpoint failure"""
        with patch.object(self.server, '_collect_metrics', new_callable=AsyncMock) as mock_collect:
            mock_collect.side_effect = Exception("Collection failed")
            
            async with httpx.AsyncClient(app=self.server.get_app(), base_url="http://test") as client:
                response = await client.post("/collect")
                
                assert response.status_code == 500
                data = response.json()
                assert "error" in data["detail"]
    
    def test_index_endpoint(self):
        """Test index HTML endpoint"""
        response = self.client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "LXC Metrics Exporter" in response.text
    
    @pytest.mark.asyncio
    async def test_collect_metrics_success(self):
        """Test metrics collection success"""
        mock_metrics = [
            {"name": "test_metric", "value": 1.0, "labels": {}}
        ]
        
        with patch.object(self.server.registry, 'collect_all', return_value=mock_metrics):
            with patch.object(self.server.prometheus_exporter, 'write_metrics_file') as mock_write:
                await self.server._collect_metrics()
                
                assert self.server.collection_count == 1
                assert self.server.last_collection_time > 0
                mock_write.assert_called_once_with(mock_metrics)
    
    @pytest.mark.asyncio
    async def test_collect_metrics_failure(self):
        """Test metrics collection failure"""
        with patch.object(self.server.registry, 'collect_all', side_effect=Exception("Collection failed")):
            with pytest.raises(Exception):
                await self.server._collect_metrics()
            
            assert self.server.collection_errors == 1