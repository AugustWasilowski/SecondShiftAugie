"""
Performance monitoring and metrics collection for the memory system.

This module provides comprehensive performance monitoring, metrics collection,
and alerting for memory system operations to enable proactive issue detection
and system optimization.

Requirements addressed:
- 6.1: Detailed logging for performance monitoring
- 6.3: Error recovery mechanisms for common failure scenarios
- 5.5: Graceful degradation and error handling
"""

import asyncio
import logging
import time
import statistics
from typing import Dict, List, Optional, Any, Callable, NamedTuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import json

from .exceptions import MemoryPerformanceError, MemoryErrorSeverity


logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected by the performance monitor."""
    COUNTER = "counter"           # Incrementing values (e.g., operation count)
    GAUGE = "gauge"              # Point-in-time values (e.g., memory usage)
    HISTOGRAM = "histogram"       # Distribution of values (e.g., response times)
    TIMER = "timer"              # Duration measurements


@dataclass
class PerformanceMetric:
    """Individual performance metric data point."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric to dictionary for serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp,
            "labels": self.labels
        }


@dataclass
class OperationStats:
    """Statistics for a specific operation."""
    operation_name: str
    total_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    recent_durations: deque = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.success_count / self.total_count) * 100.0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.error_count / self.total_count) * 100.0
    
    @property
    def avg_duration(self) -> float:
        """Calculate average duration."""
        if self.success_count == 0:
            return 0.0
        return self.total_duration / self.success_count
    
    @property
    def p95_duration(self) -> float:
        """Calculate 95th percentile duration."""
        if len(self.recent_durations) == 0:
            return 0.0
        sorted_durations = sorted(self.recent_durations)
        index = int(0.95 * len(sorted_durations))
        return sorted_durations[min(index, len(sorted_durations) - 1)]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "operation_name": self.operation_name,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "avg_duration": self.avg_duration,
            "min_duration": self.min_duration if self.min_duration != float('inf') else 0.0,
            "max_duration": self.max_duration,
            "p95_duration": self.p95_duration
        }


class PerformanceThreshold(NamedTuple):
    """Performance threshold definition."""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    comparison: str  # 'gt', 'lt', 'eq'


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system for memory operations.
    
    Collects metrics, tracks performance trends, and provides alerting
    for performance degradation and system health issues.
    """
    
    def __init__(self, 
                 max_history_size: int = 10000,
                 alert_callback: Optional[Callable] = None):
        """
        Initialize performance monitor.
        
        Args:
            max_history_size: Maximum number of metrics to keep in memory
            alert_callback: Optional callback for performance alerts
        """
        self.max_history_size = max_history_size
        self.alert_callback = alert_callback
        
        # Metrics storage
        self.metrics: deque = deque(maxlen=max_history_size)
        self.operation_stats: Dict[str, OperationStats] = defaultdict(OperationStats)
        self.component_stats: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # Performance thresholds
        self.thresholds: List[PerformanceThreshold] = [
            # STM operation thresholds
            PerformanceThreshold("stm_append_duration", 0.1, 0.5, "gt"),
            PerformanceThreshold("stm_retrieval_duration", 0.05, 0.2, "gt"),
            PerformanceThreshold("stm_summarization_duration", 2.0, 10.0, "gt"),
            
            # LTM operation thresholds
            PerformanceThreshold("ltm_storage_duration", 0.5, 2.0, "gt"),
            PerformanceThreshold("ltm_vector_search_duration", 0.1, 0.5, "gt"),
            PerformanceThreshold("ltm_hybrid_search_duration", 0.2, 1.0, "gt"),
            
            # Embedding operation thresholds
            PerformanceThreshold("embedding_generation_duration", 1.0, 5.0, "gt"),
            PerformanceThreshold("embedding_batch_duration", 5.0, 20.0, "gt"),
            
            # Error rate thresholds
            PerformanceThreshold("operation_error_rate", 5.0, 20.0, "gt"),
            PerformanceThreshold("connection_error_rate", 1.0, 10.0, "gt"),
        ]
        
        # Monitoring state
        self.monitoring_active = False
        self.last_alert_times: Dict[str, float] = {}
        self.alert_cooldown = 300.0  # 5 minutes between alerts for same metric
        
        logger.info(f"Performance monitor initialized with {len(self.thresholds)} thresholds")
    
    def record_metric(self, 
                     name: str, 
                     value: float, 
                     metric_type: MetricType = MetricType.GAUGE,
                     labels: Optional[Dict[str, str]] = None) -> None:
        """
        Record a performance metric.
        
        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric
            labels: Optional labels for metric categorization
        """
        metric = PerformanceMetric(
            name=name,
            value=value,
            metric_type=metric_type,
            timestamp=time.time(),
            labels=labels or {}
        )
        
        self.metrics.append(metric)
        
        # Check thresholds
        self._check_thresholds(metric)
        
        logger.debug(f"Recorded metric: {name}={value} ({metric_type.value})")
    
    def record_operation(self, 
                        operation_name: str, 
                        duration: float, 
                        success: bool,
                        component: Optional[str] = None,
                        error: Optional[Exception] = None) -> None:
        """
        Record an operation's performance metrics.
        
        Args:
            operation_name: Name of the operation
            duration: Operation duration in seconds
            success: Whether operation succeeded
            component: Optional component name
            error: Optional error if operation failed
        """
        # Update operation stats
        stats = self.operation_stats[operation_name]
        if not stats.operation_name:  # Initialize if new
            stats.operation_name = operation_name
        
        stats.total_count += 1
        
        if success:
            stats.success_count += 1
            stats.total_duration += duration
            stats.min_duration = min(stats.min_duration, duration)
            stats.max_duration = max(stats.max_duration, duration)
            stats.recent_durations.append(duration)
        else:
            stats.error_count += 1
        
        # Record individual metrics
        self.record_metric(f"{operation_name}_duration", duration, MetricType.HISTOGRAM,
                          {"component": component or "unknown", "success": str(success)})
        
        self.record_metric(f"{operation_name}_count", 1, MetricType.COUNTER,
                          {"component": component or "unknown", "success": str(success)})
        
        # Record error details if applicable
        if not success and error:
            error_type = error.__class__.__name__
            self.record_metric(f"{operation_name}_error", 1, MetricType.COUNTER,
                              {"error_type": error_type, "component": component or "unknown"})
        
        # Update component stats
        if component:
            comp_stats = self.component_stats[component]
            comp_stats["last_operation"] = operation_name
            comp_stats["last_duration"] = duration
            comp_stats["last_success"] = success
            comp_stats["last_update"] = time.time()
        
        logger.debug(f"Recorded operation: {operation_name} "
                    f"({'SUCCESS' if success else 'FAILED'}) in {duration:.3f}s")
    
    def get_operation_stats(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get operation statistics.
        
        Args:
            operation_name: Specific operation name, or None for all operations
            
        Returns:
            Dict containing operation statistics
        """
        if operation_name:
            if operation_name in self.operation_stats:
                return self.operation_stats[operation_name].to_dict()
            else:
                return {}
        else:
            return {name: stats.to_dict() 
                   for name, stats in self.operation_stats.items()}
    
    def get_component_health(self, component: Optional[str] = None) -> Dict[str, Any]:
        """
        Get component health information.
        
        Args:
            component: Specific component name, or None for all components
            
        Returns:
            Dict containing component health data
        """
        if component:
            return self.component_stats.get(component, {})
        else:
            return dict(self.component_stats)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive performance summary.
        
        Returns:
            Dict containing performance summary
        """
        current_time = time.time()
        
        # Calculate overall statistics
        total_operations = sum(stats.total_count for stats in self.operation_stats.values())
        total_errors = sum(stats.error_count for stats in self.operation_stats.values())
        overall_error_rate = (total_errors / total_operations * 100.0) if total_operations > 0 else 0.0
        
        # Get recent metrics (last 5 minutes)
        recent_cutoff = current_time - 300
        recent_metrics = [m for m in self.metrics if m.timestamp >= recent_cutoff]
        
        # Calculate average response times by operation
        avg_response_times = {}
        for op_name, stats in self.operation_stats.items():
            if stats.success_count > 0:
                avg_response_times[op_name] = stats.avg_duration
        
        # Identify slow operations (above warning threshold)
        slow_operations = []
        for threshold in self.thresholds:
            if threshold.metric_name.endswith("_duration"):
                op_name = threshold.metric_name.replace("_duration", "")
                if op_name in avg_response_times:
                    if avg_response_times[op_name] > threshold.warning_threshold:
                        slow_operations.append({
                            "operation": op_name,
                            "avg_duration": avg_response_times[op_name],
                            "threshold": threshold.warning_threshold
                        })
        
        return {
            "timestamp": current_time,
            "monitoring_active": self.monitoring_active,
            "total_metrics": len(self.metrics),
            "recent_metrics": len(recent_metrics),
            "total_operations": total_operations,
            "total_errors": total_errors,
            "overall_error_rate": overall_error_rate,
            "operation_count": len(self.operation_stats),
            "component_count": len(self.component_stats),
            "avg_response_times": avg_response_times,
            "slow_operations": slow_operations,
            "threshold_violations": len([t for t in self.thresholds 
                                       if self._is_threshold_violated(t)])
        }
    
    def get_metrics_by_name(self, 
                           metric_name: str, 
                           time_window: Optional[float] = None) -> List[PerformanceMetric]:
        """
        Get metrics by name within optional time window.
        
        Args:
            metric_name: Name of metric to retrieve
            time_window: Optional time window in seconds (from now backwards)
            
        Returns:
            List of matching metrics
        """
        current_time = time.time()
        cutoff_time = current_time - time_window if time_window else 0
        
        return [m for m in self.metrics 
                if m.name == metric_name and m.timestamp >= cutoff_time]
    
    def _check_thresholds(self, metric: PerformanceMetric) -> None:
        """Check if metric violates any thresholds."""
        for threshold in self.thresholds:
            if threshold.metric_name == metric.name:
                if self._is_threshold_violated_for_metric(threshold, metric):
                    self._trigger_alert(threshold, metric)
    
    def _is_threshold_violated(self, threshold: PerformanceThreshold) -> bool:
        """Check if a threshold is currently violated."""
        recent_metrics = self.get_metrics_by_name(threshold.metric_name, 60)  # Last minute
        if not recent_metrics:
            return False
        
        latest_metric = max(recent_metrics, key=lambda m: m.timestamp)
        return self._is_threshold_violated_for_metric(threshold, latest_metric)
    
    def _is_threshold_violated_for_metric(self, 
                                        threshold: PerformanceThreshold, 
                                        metric: PerformanceMetric) -> bool:
        """Check if a specific metric violates a threshold."""
        if threshold.comparison == "gt":
            return metric.value > threshold.critical_threshold
        elif threshold.comparison == "lt":
            return metric.value < threshold.critical_threshold
        elif threshold.comparison == "eq":
            return abs(metric.value - threshold.critical_threshold) < 0.001
        return False
    
    def _trigger_alert(self, threshold: PerformanceThreshold, metric: PerformanceMetric) -> None:
        """Trigger performance alert."""
        current_time = time.time()
        alert_key = f"{threshold.metric_name}_{threshold.comparison}_{threshold.critical_threshold}"
        
        # Check cooldown
        if alert_key in self.last_alert_times:
            if current_time - self.last_alert_times[alert_key] < self.alert_cooldown:
                return
        
        self.last_alert_times[alert_key] = current_time
        
        # Determine severity
        is_critical = self._is_threshold_violated_for_metric(threshold, metric)
        severity = "CRITICAL" if is_critical else "WARNING"
        
        alert_message = (f"Performance alert: {threshold.metric_name} = {metric.value:.3f} "
                        f"exceeds {severity.lower()} threshold {threshold.critical_threshold}")
        
        logger.warning(alert_message)
        
        # Call alert callback if provided
        if self.alert_callback:
            try:
                self.alert_callback({
                    "severity": severity,
                    "metric_name": threshold.metric_name,
                    "current_value": metric.value,
                    "threshold": threshold.critical_threshold,
                    "message": alert_message,
                    "timestamp": current_time,
                    "labels": metric.labels
                })
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
    
    def export_metrics(self, format_type: str = "json") -> str:
        """
        Export metrics in specified format.
        
        Args:
            format_type: Export format ("json", "prometheus")
            
        Returns:
            Formatted metrics string
        """
        if format_type == "json":
            return self._export_json()
        elif format_type == "prometheus":
            return self._export_prometheus()
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def _export_json(self) -> str:
        """Export metrics as JSON."""
        export_data = {
            "timestamp": time.time(),
            "metrics": [m.to_dict() for m in self.metrics],
            "operation_stats": self.get_operation_stats(),
            "component_health": self.get_component_health(),
            "performance_summary": self.get_performance_summary()
        }
        return json.dumps(export_data, indent=2)
    
    def _export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Group metrics by name
        metrics_by_name = defaultdict(list)
        for metric in self.metrics:
            metrics_by_name[metric.name].append(metric)
        
        # Export each metric group
        for metric_name, metric_list in metrics_by_name.items():
            # Add help and type comments
            lines.append(f"# HELP {metric_name} Memory system metric")
            
            metric_type = metric_list[0].metric_type.value
            prom_type = "counter" if metric_type == "counter" else "gauge"
            lines.append(f"# TYPE {metric_name} {prom_type}")
            
            # Add metric values
            for metric in metric_list[-10:]:  # Last 10 values
                labels_str = ""
                if metric.labels:
                    label_pairs = [f'{k}="{v}"' for k, v in metric.labels.items()]
                    labels_str = "{" + ",".join(label_pairs) + "}"
                
                lines.append(f"{metric_name}{labels_str} {metric.value} {int(metric.timestamp * 1000)}")
        
        return "\n".join(lines)
    
    def reset_stats(self) -> None:
        """Reset all performance statistics."""
        self.metrics.clear()
        self.operation_stats.clear()
        self.component_stats.clear()
        self.last_alert_times.clear()
        logger.info("Performance statistics reset")
    
    def start_monitoring(self) -> None:
        """Start performance monitoring."""
        self.monitoring_active = True
        logger.info("Performance monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        self.monitoring_active = False
        logger.info("Performance monitoring stopped")


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Decorator for automatic performance monitoring
def monitor_performance(operation_name: Optional[str] = None, 
                       component: Optional[str] = None):
    """
    Decorator to automatically monitor function performance.
    
    Args:
        operation_name: Custom operation name (defaults to function name)
        component: Component name for categorization
    """
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.time()
            success = False
            error = None
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = e
                raise
            finally:
                duration = time.time() - start_time
                performance_monitor.record_operation(
                    op_name, duration, success, component, error
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.time()
            success = False
            error = None
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error = e
                raise
            finally:
                duration = time.time() - start_time
                performance_monitor.record_operation(
                    op_name, duration, success, component, error
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Context manager for operation timing
class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, operation_name: str, component: Optional[str] = None):
        self.operation_name = operation_name
        self.component = component
        self.start_time = None
        self.success = False
        self.error = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.success = exc_type is None
        self.error = exc_val
        
        performance_monitor.record_operation(
            self.operation_name, duration, self.success, self.component, self.error
        )
        
        return False  # Don't suppress exceptions