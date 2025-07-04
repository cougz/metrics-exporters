"""Batch exporter for optimized metric exports"""
import asyncio
import time
from typing import List, Dict, Any, Optional
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from logging_config import get_logger
from ..models import MetricValue


logger = get_logger(__name__)


class BatchExporter:
    """Base class for batch exporters with connection pooling"""
    
    def __init__(self, 
                 batch_size: int = 100,
                 batch_timeout: float = 5.0,
                 max_queue_size: int = 1000,
                 worker_threads: int = 2):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_queue_size = max_queue_size
        
        # Batch management
        self._metrics_queue = deque()
        self._last_export_time = time.time()
        self._export_lock = asyncio.Lock()
        self._shutdown = False
        
        # Thread pool for blocking operations
        self._executor = ThreadPoolExecutor(
            max_workers=worker_threads,
            thread_name_prefix="batch_exporter"
        )
        
        # Background task for periodic exports
        self._export_task = None
        
    async def start(self):
        """Start the batch exporter"""
        if self._export_task is None:
            self._export_task = asyncio.create_task(self._export_loop())
            logger.info("Batch exporter started", 
                       batch_size=self.batch_size,
                       batch_timeout=self.batch_timeout)
    
    async def stop(self):
        """Stop the batch exporter and flush remaining metrics"""
        self._shutdown = True
        
        if self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining metrics
        await self._flush_metrics()
        
        # Cleanup executor
        self._executor.shutdown(wait=True)
        
        logger.info("Batch exporter stopped")
    
    async def export_metrics(self, metrics: List[MetricValue]):
        """Add metrics to the batch queue"""
        async with self._export_lock:
            # Check queue size limit
            if len(self._metrics_queue) + len(metrics) > self.max_queue_size:
                # Drop oldest metrics to make room
                overflow = len(self._metrics_queue) + len(metrics) - self.max_queue_size
                for _ in range(overflow):
                    if self._metrics_queue:
                        self._metrics_queue.popleft()
                
                logger.warning("Metrics queue overflow, dropped metrics",
                             dropped_count=overflow,
                             queue_size=len(self._metrics_queue))
            
            # Add new metrics
            self._metrics_queue.extend(metrics)
            
            # Check if we should export immediately
            if len(self._metrics_queue) >= self.batch_size:
                await self._export_batch()
    
    async def _export_loop(self):
        """Background loop for periodic exports"""
        while not self._shutdown:
            try:
                await asyncio.sleep(1.0)  # Check every second
                
                current_time = time.time()
                time_since_last_export = current_time - self._last_export_time
                
                # Export if timeout reached and we have metrics
                if (time_since_last_export >= self.batch_timeout and 
                    len(self._metrics_queue) > 0):
                    await self._export_batch()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Export loop error", error=str(e), exc_info=True)
                await asyncio.sleep(5.0)  # Back off on error
    
    async def _export_batch(self):
        """Export a batch of metrics"""
        async with self._export_lock:
            if not self._metrics_queue:
                return
            
            # Extract batch
            batch = []
            while self._metrics_queue and len(batch) < self.batch_size:
                batch.append(self._metrics_queue.popleft())
            
            if not batch:
                return
            
            # Export batch
            try:
                start_time = time.time()
                
                # Run the actual export in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self._executor, self._export_batch_sync, batch)
                
                export_time = time.time() - start_time
                self._last_export_time = time.time()
                
                logger.debug("Batch exported",
                           batch_size=len(batch),
                           export_time_seconds=round(export_time, 3),
                           queue_remaining=len(self._metrics_queue))
                
            except Exception as e:
                logger.error("Batch export failed",
                           batch_size=len(batch),
                           error=str(e),
                           exc_info=True)
                
                # Re-queue failed metrics (at front of queue)
                for metric in reversed(batch):
                    self._metrics_queue.appendleft(metric)
    
    async def _flush_metrics(self):
        """Flush all remaining metrics"""
        while self._metrics_queue:
            await self._export_batch()
    
    def _export_batch_sync(self, batch: List[MetricValue]):
        """Synchronous batch export - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _export_batch_sync")


class MetricsBuffer:
    """Memory-efficient metrics buffer with deduplication"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._buffer: Dict[str, MetricValue] = {}
        self._insertion_order: deque = deque()
    
    def add_metric(self, metric: MetricValue):
        """Add metric to buffer with deduplication"""
        # Create unique key for metric
        key = f"{metric.name}_{hash(frozenset(metric.labels.items()) if metric.labels else frozenset())}"
        
        # If metric exists, update it
        if key in self._buffer:
            self._buffer[key] = metric
        else:
            # Check buffer size
            if len(self._buffer) >= self.max_size:
                # Remove oldest metric
                oldest_key = self._insertion_order.popleft()
                self._buffer.pop(oldest_key, None)
            
            # Add new metric
            self._buffer[key] = metric
            self._insertion_order.append(key)
    
    def get_metrics(self) -> List[MetricValue]:
        """Get all metrics from buffer"""
        return list(self._buffer.values())
    
    def clear(self):
        """Clear the buffer"""
        self._buffer.clear()
        self._insertion_order.clear()
    
    def size(self) -> int:
        """Get buffer size"""
        return len(self._buffer)