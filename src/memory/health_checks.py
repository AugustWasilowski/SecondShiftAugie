"""
Health check endpoints and monitoring for the memory system.

This module provides comprehensive health checks for all memory system components,
enabling proactive monitoring and automated recovery mechanisms.

Requirements addressed:
- 5.5: Graceful degradation and error handling with appropriate fallbacks
- 6.1: Detailed logging for performance monitoring
- 6.3: Error recovery mechanisms for common failure scenarios
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, NamedTuple
from dataclasses import dataclass
from enum import Enum
import json

from .exceptions import (
    MemorySystemError, MemoryConnectionError, MemoryDatabaseError,
    EmbeddingConnectionError, MemoryErrorSeverity
)
from .performance_monitor import performance_monitor, PerformanceTimer


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels for components."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""
    component: str
    status: HealthStatus
    response_time: float
    message: str
    details: Dict[str, Any]
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "component": self.component,
            "status": self.status.value,
            "response_time": self.response_time,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp
        }


class HealthChecker:
    """
    Comprehensive health checking system for memory components.
    
    Provides health checks for database connectivity, embedding services,
    and overall system health with automated recovery suggestions.
    """
    
    def __init__(self):
        """Initialize health checker."""
        self.health_checks: Dict[str, Callable] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
        self.check_intervals: Dict[str, float] = {}
        self.recovery_actions: Dict[str, Callable] = {}
        
        logger.info("Health checker initialized")
    
    def register_health_check(self, 
                             component: str, 
                             check_function: Callable,
                             interval: float = 60.0,
                             recovery_action: Optional[Callable] = None) -> None:
        """
        Register a health check for a component.
        
        Args:
            component: Component name
            check_function: Async function that returns health status
            interval: Check interval in seconds
            recovery_action: Optional recovery function
        """
        self.health_checks[component] = check_function
        self.check_intervals[component] = interval
        
        if recovery_action:
            self.recovery_actions[component] = recovery_action
        
        logger.info(f"Registered health check for {component} (interval: {interval}s)")
    
    async def check_component_health(self, component: str) -> HealthCheckResult:
        """
        Perform health check for a specific component.
        
        Args:
            component: Component name to check
            
        Returns:
            HealthCheckResult: Health check result
        """
        if component not in self.health_checks:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNKNOWN,
                response_time=0.0,
                message=f"No health check registered for {component}",
                details={},
                timestamp=time.time()
            )
        
        start_time = time.time()
        
        try:
            with PerformanceTimer(f"health_check_{component}", "health_monitoring"):
                check_function = self.health_checks[component]
                
                # Run health check with timeout
                result = await asyncio.wait_for(check_function(), timeout=30.0)
                
                response_time = time.time() - start_time
                
                # Parse result
                if isinstance(result, bool):
                    status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                    message = f"{component} is {'healthy' if result else 'unhealthy'}"
                    details = {}
                elif isinstance(result, dict):
                    status = HealthStatus(result.get('status', 'UNKNOWN'))
                    message = result.get('message', f"{component} health check completed")
                    details = result.get('details', {})
                else:
                    status = HealthStatus.UNKNOWN
                    message = f"Invalid health check result for {component}"
                    details = {"result": str(result)}
                
                health_result = HealthCheckResult(
                    component=component,
                    status=status,
                    response_time=response_time,
                    message=message,
                    details=details,
                    timestamp=time.time()
                )
                
                self.last_results[component] = health_result
                
                logger.debug(f"Health check for {component}: {status.value} ({response_time:.3f}s)")
                
                return health_result
                
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            health_result = HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                message=f"{component} health check timed out",
                details={"error": "timeout", "timeout_duration": 30.0},
                timestamp=time.time()
            )
            
            self.last_results[component] = health_result
            logger.warning(f"Health check timeout for {component} after {response_time:.3f}s")
            
            return health_result
            
        except Exception as e:
            response_time = time.time() - start_time
            health_result = HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                response_time=response_time,
                message=f"{component} health check failed: {e}",
                details={"error": str(e), "error_type": e.__class__.__name__},
                timestamp=time.time()
            )
            
            self.last_results[component] = health_result
            logger.error(f"Health check error for {component}: {e}")
            
            return health_result   
 
    async def check_all_components(self) -> Dict[str, HealthCheckResult]:
        """
        Check health of all registered components.
        
        Returns:
            Dict mapping component names to health results
        """
        results = {}
        
        # Run all health checks concurrently
        tasks = []
        for component in self.health_checks.keys():
            task = asyncio.create_task(self.check_component_health(component))
            tasks.append((component, task))
        
        # Wait for all checks to complete
        for component, task in tasks:
            try:
                result = await task
                results[component] = result
            except Exception as e:
                logger.error(f"Failed to run health check for {component}: {e}")
                results[component] = HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    response_time=0.0,
                    message=f"Health check execution failed: {e}",
                    details={"error": str(e)},
                    timestamp=time.time()
                )
        
        return results
    
    async def get_system_health_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive system health summary.
        
        Returns:
            Dict containing system health information
        """
        # Check all components
        component_results = await self.check_all_components()
        
        # Calculate overall health
        healthy_count = sum(1 for r in component_results.values() 
                           if r.status == HealthStatus.HEALTHY)
        degraded_count = sum(1 for r in component_results.values() 
                            if r.status == HealthStatus.DEGRADED)
        unhealthy_count = sum(1 for r in component_results.values() 
                             if r.status == HealthStatus.UNHEALTHY)
        
        total_components = len(component_results)
        
        # Determine overall status
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Get performance summary
        perf_summary = performance_monitor.get_performance_summary()
        
        return {
            "timestamp": time.time(),
            "overall_status": overall_status.value,
            "total_components": total_components,
            "healthy_components": healthy_count,
            "degraded_components": degraded_count,
            "unhealthy_components": unhealthy_count,
            "component_results": {name: result.to_dict() 
                                for name, result in component_results.items()},
            "performance_summary": perf_summary,
            "recommendations": self._generate_recommendations(component_results)
        }
    
    def _generate_recommendations(self, 
                                 results: Dict[str, HealthCheckResult]) -> List[str]:
        """Generate health recommendations based on check results."""
        recommendations = []
        
        for component, result in results.items():
            if result.status == HealthStatus.UNHEALTHY:
                if component == "database":
                    recommendations.append("Check database connection and server status")
                elif component == "embedding_service":
                    recommendations.append("Verify Ollama service is running and accessible")
                elif component == "memory_service":
                    recommendations.append("Restart memory service or check component dependencies")
                else:
                    recommendations.append(f"Investigate {component} component issues")
            
            elif result.status == HealthStatus.DEGRADED:
                recommendations.append(f"Monitor {component} for potential issues")
        
        # Add performance-based recommendations
        perf_summary = performance_monitor.get_performance_summary()
        if perf_summary.get("overall_error_rate", 0) > 10:
            recommendations.append("High error rate detected - investigate system stability")
        
        if perf_summary.get("slow_operations"):
            recommendations.append("Slow operations detected - consider performance optimization")
        
        return recommendations
    
    async def attempt_recovery(self, component: str) -> bool:
        """
        Attempt to recover an unhealthy component.
        
        Args:
            component: Component name to recover
            
        Returns:
            bool: True if recovery was attempted, False if no recovery action available
        """
        if component not in self.recovery_actions:
            logger.warning(f"No recovery action available for {component}")
            return False
        
        try:
            recovery_action = self.recovery_actions[component]
            logger.info(f"Attempting recovery for {component}")
            
            await recovery_action()
            
            # Re-check health after recovery attempt
            await asyncio.sleep(5)  # Wait a bit for recovery to take effect
            result = await self.check_component_health(component)
            
            if result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]:
                logger.info(f"Recovery successful for {component}")
                return True
            else:
                logger.warning(f"Recovery attempt for {component} did not improve health")
                return False
                
        except Exception as e:
            logger.error(f"Recovery attempt failed for {component}: {e}")
            return False


# Specific health check implementations

async def check_database_health(db_pool) -> Dict[str, Any]:
    """
    Check database connectivity and basic functionality.
    
    Args:
        db_pool: Database connection pool
        
    Returns:
        Dict containing health check result
    """
    try:
        if not db_pool:
            return {
                "status": "UNHEALTHY",
                "message": "Database pool not initialized",
                "details": {"error": "no_pool"}
            }
        
        # Test basic connectivity
        async with db_pool.acquire() as conn:
            # Simple query to test connection
            result = await conn.fetchval("SELECT 1")
            
            if result != 1:
                return {
                    "status": "UNHEALTHY",
                    "message": "Database query returned unexpected result",
                    "details": {"result": result}
                }
            
            # Check memory system tables exist
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('messages', 'thread_summaries', 'memories')
            """)
            
            table_names = [row['table_name'] for row in tables]
            missing_tables = set(['messages', 'thread_summaries', 'memories']) - set(table_names)
            
            if missing_tables:
                return {
                    "status": "DEGRADED",
                    "message": f"Missing database tables: {missing_tables}",
                    "details": {"missing_tables": list(missing_tables)}
                }
            
            # Check pgvector extension
            extensions = await conn.fetch("""
                SELECT extname FROM pg_extension WHERE extname = 'vector'
            """)
            
            if not extensions:
                return {
                    "status": "DEGRADED",
                    "message": "pgvector extension not installed",
                    "details": {"missing_extension": "vector"}
                }
            
            return {
                "status": "HEALTHY",
                "message": "Database is healthy",
                "details": {
                    "tables": table_names,
                    "extensions": ["vector"]
                }
            }
            
    except Exception as e:
        return {
            "status": "UNHEALTHY",
            "message": f"Database health check failed: {e}",
            "details": {"error": str(e), "error_type": e.__class__.__name__}
        }


async def check_embedding_service_health(embedding_client) -> Dict[str, Any]:
    """
    Check embedding service connectivity and functionality.
    
    Args:
        embedding_client: EmbeddingClient instance
        
    Returns:
        Dict containing health check result
    """
    try:
        if not embedding_client:
            return {
                "status": "UNHEALTHY",
                "message": "Embedding client not initialized",
                "details": {"error": "no_client"}
            }
        
        # Test basic connectivity
        is_healthy = await embedding_client.health_check()
        
        if not is_healthy:
            return {
                "status": "UNHEALTHY",
                "message": "Embedding service health check failed",
                "details": {"service_url": embedding_client.base_url}
            }
        
        # Test embedding generation with small text
        try:
            test_embedding = await embedding_client.embed_text("test")
            
            if not test_embedding or len(test_embedding) == 0:
                return {
                    "status": "DEGRADED",
                    "message": "Embedding generation returned empty result",
                    "details": {"test_result": "empty_embedding"}
                }
            
            return {
                "status": "HEALTHY",
                "message": "Embedding service is healthy",
                "details": {
                    "service_url": embedding_client.base_url,
                    "model": embedding_client.model,
                    "embedding_dimension": len(test_embedding)
                }
            }
            
        except Exception as e:
            return {
                "status": "DEGRADED",
                "message": f"Embedding generation test failed: {e}",
                "details": {
                    "service_url": embedding_client.base_url,
                    "error": str(e)
                }
            }
            
    except Exception as e:
        return {
            "status": "UNHEALTHY",
            "message": f"Embedding service health check failed: {e}",
            "details": {"error": str(e), "error_type": e.__class__.__name__}
        }


async def check_memory_service_health(memory_service) -> Dict[str, Any]:
    """
    Check overall memory service health.
    
    Args:
        memory_service: MemoryService instance
        
    Returns:
        Dict containing health check result
    """
    try:
        if not memory_service:
            return {
                "status": "UNHEALTHY",
                "message": "Memory service not initialized",
                "details": {"error": "no_service"}
            }
        
        # Get service status
        service_status = await memory_service.get_service_status()
        
        if not service_status.get("initialized", False):
            return {
                "status": "UNHEALTHY",
                "message": "Memory service not initialized",
                "details": service_status
            }
        
        mode = service_status.get("mode", "no_memory")
        
        if mode == "no_memory":
            return {
                "status": "UNHEALTHY",
                "message": "Memory service in no-memory mode",
                "details": service_status
            }
        elif mode == "stm_only":
            return {
                "status": "DEGRADED",
                "message": "Memory service in STM-only mode",
                "details": service_status
            }
        elif mode == "full":
            return {
                "status": "HEALTHY",
                "message": "Memory service fully operational",
                "details": service_status
            }
        else:
            return {
                "status": "UNKNOWN",
                "message": f"Memory service in unknown mode: {mode}",
                "details": service_status
            }
            
    except Exception as e:
        return {
            "status": "UNHEALTHY",
            "message": f"Memory service health check failed: {e}",
            "details": {"error": str(e), "error_type": e.__class__.__name__}
        }


# Global health checker instance
health_checker = HealthChecker()