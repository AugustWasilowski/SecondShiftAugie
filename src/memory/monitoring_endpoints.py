"""
Monitoring endpoints and utilities for the memory system.

This module provides HTTP-like endpoints and utilities for monitoring
memory system health, performance, and status. These can be integrated
with Discord commands or external monitoring systems.

Requirements addressed:
- 5.5: Graceful degradation with user notifications
- 6.1: Detailed logging for performance monitoring
- 6.3: Error recovery mechanisms for common failure scenarios
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from .performance_monitor import performance_monitor
from .health_checks import health_checker
from .recovery_manager import recovery_manager
from .exceptions import MemorySystemError, MemoryErrorSeverity


logger = logging.getLogger(__name__)


class MonitoringLevel(Enum):
    """Monitoring detail levels."""
    BASIC = "basic"           # Basic status only
    DETAILED = "detailed"     # Detailed metrics
    COMPREHENSIVE = "comprehensive"  # Full diagnostic information


@dataclass
class MonitoringResponse:
    """Response from monitoring endpoints."""
    status_code: int
    data: Dict[str, Any]
    message: str
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status_code": self.status_code,
            "data": self.data,
            "message": self.message,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class MemoryMonitoringEndpoints:
    """
    Monitoring endpoints for the memory system.
    
    Provides various endpoints for checking system health, performance,
    and status that can be used by Discord commands or external monitoring.
    """
    
    def __init__(self, memory_service=None):
        """
        Initialize monitoring endpoints.
        
        Args:
            memory_service: Optional MemoryService instance
        """
        self.memory_service = memory_service
        self.start_time = time.time()
        
        logger.info("Memory monitoring endpoints initialized")
    
    async def health_check(self, level: MonitoringLevel = MonitoringLevel.BASIC) -> MonitoringResponse:
        """
        Health check endpoint.
        
        Args:
            level: Level of detail to include
            
        Returns:
            MonitoringResponse with health information
        """
        try:
            if level == MonitoringLevel.BASIC:
                # Basic health check
                if self.memory_service:
                    service_status = await self.memory_service.get_service_status()
                    is_healthy = service_status.get("mode") != "no_memory"
                else:
                    is_healthy = False
                
                return MonitoringResponse(
                    status_code=200 if is_healthy else 503,
                    data={
                        "healthy": is_healthy,
                        "mode": service_status.get("mode", "unknown") if self.memory_service else "unknown",
                        "uptime": time.time() - self.start_time
                    },
                    message="Health check completed",
                    timestamp=time.time()
                )
            
            elif level == MonitoringLevel.DETAILED:
                # Detailed health information
                health_summary = await health_checker.get_system_health_summary()
                
                overall_healthy = health_summary.get("overall_status") == "HEALTHY"
                
                return MonitoringResponse(
                    status_code=200 if overall_healthy else 503,
                    data=health_summary,
                    message="Detailed health check completed",
                    timestamp=time.time()
                )
            
            else:  # COMPREHENSIVE
                # Comprehensive health and performance data
                health_summary = await health_checker.get_system_health_summary()
                performance_summary = performance_monitor.get_performance_summary()
                degradation_status = recovery_manager.get_degradation_status()
                
                overall_healthy = health_summary.get("overall_status") == "HEALTHY"
                
                return MonitoringResponse(
                    status_code=200 if overall_healthy else 503,
                    data={
                        "health": health_summary,
                        "performance": performance_summary,
                        "degradation": degradation_status,
                        "uptime": time.time() - self.start_time
                    },
                    message="Comprehensive health check completed",
                    timestamp=time.time()
                )
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Health check failed",
                timestamp=time.time()
            )
    
    async def performance_metrics(self) -> MonitoringResponse:
        """
        Performance metrics endpoint.
        
        Returns:
            MonitoringResponse with performance metrics
        """
        try:
            performance_summary = performance_monitor.get_performance_summary()
            
            return MonitoringResponse(
                status_code=200,
                data=performance_summary,
                message="Performance metrics retrieved",
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Failed to retrieve performance metrics",
                timestamp=time.time()
            )
    
    async def component_status(self, component: Optional[str] = None) -> MonitoringResponse:
        """
        Component status endpoint.
        
        Args:
            component: Specific component name, or None for all components
            
        Returns:
            MonitoringResponse with component status
        """
        try:
            if component:
                # Check specific component
                result = await health_checker.check_component_health(component)
                
                return MonitoringResponse(
                    status_code=200 if result.status.value == "HEALTHY" else 503,
                    data=result.to_dict(),
                    message=f"Component status for {component}",
                    timestamp=time.time()
                )
            else:
                # Check all components
                results = await health_checker.check_all_components()
                
                all_healthy = all(r.status.value == "HEALTHY" for r in results.values())
                
                return MonitoringResponse(
                    status_code=200 if all_healthy else 503,
                    data={name: result.to_dict() for name, result in results.items()},
                    message="All component statuses",
                    timestamp=time.time()
                )
                
        except Exception as e:
            logger.error(f"Failed to get component status: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Failed to retrieve component status",
                timestamp=time.time()
            )
    
    async def recovery_status(self) -> MonitoringResponse:
        """
        Recovery and degradation status endpoint.
        
        Returns:
            MonitoringResponse with recovery status
        """
        try:
            degradation_status = recovery_manager.get_degradation_status()
            recovery_history = recovery_manager.get_recovery_history()
            
            return MonitoringResponse(
                status_code=200,
                data={
                    "degradation": degradation_status,
                    "recovery_history": recovery_history[-10:]  # Last 10 attempts
                },
                message="Recovery status retrieved",
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to get recovery status: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Failed to retrieve recovery status",
                timestamp=time.time()
            )
    
    async def system_info(self) -> MonitoringResponse:
        """
        System information endpoint.
        
        Returns:
            MonitoringResponse with system information
        """
        try:
            info = {
                "uptime": time.time() - self.start_time,
                "memory_service_available": self.memory_service is not None,
                "monitoring_active": performance_monitor.monitoring_active,
                "registered_health_checks": len(health_checker.health_checks),
                "registered_recovery_actions": sum(
                    len(actions) for actions in recovery_manager.recovery_actions.values()
                )
            }
            
            if self.memory_service:
                service_status = await self.memory_service.get_service_status()
                info.update({
                    "memory_mode": service_status.get("mode", "unknown"),
                    "memory_initialized": service_status.get("initialized", False),
                    "components": service_status.get("components", {})
                })
            
            return MonitoringResponse(
                status_code=200,
                data=info,
                message="System information retrieved",
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Failed to retrieve system information",
                timestamp=time.time()
            )
    
    async def trigger_recovery(self, component: str) -> MonitoringResponse:
        """
        Trigger recovery for a specific component.
        
        Args:
            component: Component name to recover
            
        Returns:
            MonitoringResponse with recovery result
        """
        try:
            success = await health_checker.attempt_recovery(component)
            
            return MonitoringResponse(
                status_code=200 if success else 500,
                data={
                    "component": component,
                    "recovery_attempted": True,
                    "recovery_successful": success
                },
                message=f"Recovery {'successful' if success else 'failed'} for {component}",
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to trigger recovery for {component}: {e}")
            return MonitoringResponse(
                status_code=500,
                data={
                    "component": component,
                    "recovery_attempted": False,
                    "error": str(e)
                },
                message=f"Failed to trigger recovery for {component}",
                timestamp=time.time()
            )
    
    async def export_metrics(self, format_type: str = "json") -> MonitoringResponse:
        """
        Export metrics in specified format.
        
        Args:
            format_type: Export format ("json" or "prometheus")
            
        Returns:
            MonitoringResponse with exported metrics
        """
        try:
            if format_type not in ["json", "prometheus"]:
                return MonitoringResponse(
                    status_code=400,
                    data={"error": f"Unsupported format: {format_type}"},
                    message="Invalid export format",
                    timestamp=time.time()
                )
            
            exported_data = performance_monitor.export_metrics(format_type)
            
            return MonitoringResponse(
                status_code=200,
                data={
                    "format": format_type,
                    "metrics": exported_data if format_type == "json" else None,
                    "raw_data": exported_data if format_type == "prometheus" else None
                },
                message=f"Metrics exported in {format_type} format",
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return MonitoringResponse(
                status_code=500,
                data={"error": str(e)},
                message="Failed to export metrics",
                timestamp=time.time()
            )
    
    def get_user_friendly_status(self) -> str:
        """
        Get user-friendly status message for Discord.
        
        Returns:
            String with user-friendly status
        """
        try:
            if not self.memory_service:
                return "❌ Memory system is not available"
            
            # Get basic status synchronously (simplified)
            degradation = recovery_manager.get_degradation_status()
            current_level = degradation.get("current_level", "none")
            
            if current_level == "none":
                return "✅ Memory system is fully operational"
            elif current_level == "minor":
                return "⚠️ Memory system has minor issues but is mostly functional"
            elif current_level == "moderate":
                return "⚠️ Memory system is in degraded mode with limited functionality"
            elif current_level == "severe":
                return "❌ Memory system has significant issues with minimal functionality"
            elif current_level == "critical":
                return "❌ Memory system is currently unavailable"
            else:
                return "❓ Memory system status is unknown"
                
        except Exception as e:
            logger.error(f"Failed to get user-friendly status: {e}")
            return "❓ Unable to determine memory system status"
    
    async def get_recommendations(self) -> List[str]:
        """
        Get system health recommendations.
        
        Returns:
            List of recommendation strings
        """
        try:
            health_summary = await health_checker.get_system_health_summary()
            return health_summary.get("recommendations", [])
        except Exception as e:
            logger.error(f"Failed to get recommendations: {e}")
            return ["Unable to generate recommendations due to monitoring error"]


# Global monitoring endpoints instance
monitoring_endpoints = MemoryMonitoringEndpoints()


def set_memory_service(memory_service):
    """Set the memory service for monitoring endpoints."""
    monitoring_endpoints.memory_service = memory_service
    logger.info("Memory service set for monitoring endpoints")


# Utility functions for Discord integration

async def get_health_embed_data() -> Dict[str, Any]:
    """
    Get health data formatted for Discord embed.
    
    Returns:
        Dict with embed-ready health data
    """
    try:
        response = await monitoring_endpoints.health_check(MonitoringLevel.DETAILED)
        
        if response.status_code == 200:
            color = 0x00ff00  # Green
            title = "✅ Memory System Health"
        else:
            color = 0xff0000  # Red
            title = "❌ Memory System Health"
        
        health_data = response.data
        
        fields = []
        
        # Overall status
        fields.append({
            "name": "Overall Status",
            "value": health_data.get("overall_status", "Unknown"),
            "inline": True
        })
        
        # Component counts
        fields.append({
            "name": "Components",
            "value": f"✅ {health_data.get('healthy_components', 0)} "
                    f"⚠️ {health_data.get('degraded_components', 0)} "
                    f"❌ {health_data.get('unhealthy_components', 0)}",
            "inline": True
        })
        
        # Performance summary
        perf_summary = health_data.get("performance_summary", {})
        if perf_summary:
            error_rate = perf_summary.get("overall_error_rate", 0)
            fields.append({
                "name": "Error Rate",
                "value": f"{error_rate:.1f}%",
                "inline": True
            })
        
        return {
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": response.timestamp
        }
        
    except Exception as e:
        logger.error(f"Failed to get health embed data: {e}")
        return {
            "title": "❌ Memory System Health",
            "color": 0xff0000,
            "fields": [
                {
                    "name": "Error",
                    "value": f"Failed to retrieve health data: {str(e)[:100]}",
                    "inline": False
                }
            ],
            "timestamp": time.time()
        }


async def get_performance_summary_text() -> str:
    """
    Get performance summary as formatted text.
    
    Returns:
        String with performance summary
    """
    try:
        response = await monitoring_endpoints.performance_metrics()
        
        if response.status_code != 200:
            return f"❌ Failed to retrieve performance metrics: {response.message}"
        
        data = response.data
        
        lines = [
            "📊 **Memory System Performance**",
            "",
            f"**Total Operations:** {data.get('total_operations', 0):,}",
            f"**Error Rate:** {data.get('overall_error_rate', 0):.1f}%",
            f"**Active Components:** {data.get('component_count', 0)}",
            ""
        ]
        
        # Add slow operations if any
        slow_ops = data.get("slow_operations", [])
        if slow_ops:
            lines.append("⚠️ **Slow Operations:**")
            for op in slow_ops[:3]:  # Show top 3
                lines.append(f"• {op['operation']}: {op['avg_duration']:.2f}s")
            lines.append("")
        
        # Add response times
        avg_times = data.get("avg_response_times", {})
        if avg_times:
            lines.append("⏱️ **Average Response Times:**")
            for op, time_val in list(avg_times.items())[:5]:  # Show top 5
                lines.append(f"• {op}: {time_val:.3f}s")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        return f"❌ Failed to retrieve performance summary: {str(e)[:100]}"