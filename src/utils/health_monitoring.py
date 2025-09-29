"""
Comprehensive health monitoring system for SecondShiftAugie bot.

Provides centralized health monitoring, periodic health checks, and automated
recovery mechanisms for all bot components including AI services.

Requirements addressed:
- 1.3: Provide fallback responses when Ollama fails
- 2.3: Implement retry logic with exponential backoff
- 2.5: Continue operating in degraded mode
- 6.2: Proper timeout and error handling for API calls
- 6.4: Detailed logging for AI interactions and errors
- 6.5: Indicate when AI features are unavailable
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum

from .error_handler import (
    health_monitor, degradation_manager, ai_error_handler,
    ComponentState, ErrorSeverity
)

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a component health check."""
    component: str
    healthy: bool
    response_time: float
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthMonitoringService:
    """
    Centralized health monitoring service for all bot components.
    
    Provides periodic health checks, automated recovery, and comprehensive
    status reporting for the entire bot system.
    """
    
    def __init__(self, check_interval: float = 300.0):  # 5 minutes
        """
        Initialize health monitoring service.
        
        Args:
            check_interval: Interval between health checks in seconds
        """
        self.check_interval = check_interval
        self.health_checks: Dict[str, Callable] = {}
        self.last_check_times: Dict[str, float] = {}
        self.health_history: Dict[str, List[HealthCheckResult]] = {}
        self.max_history_length = 50
        
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info(f"Health monitoring service initialized with {check_interval}s interval")
    
    def register_health_check(self, component: str, check_function: Callable) -> None:
        """
        Register a health check function for a component.
        
        Args:
            component: Name of the component
            check_function: Async function that returns bool (healthy/unhealthy)
        """
        self.health_checks[component] = check_function
        self.health_history[component] = []
        logger.info(f"Registered health check for component: {component}")
    
    async def start_monitoring(self) -> None:
        """Start the periodic health monitoring task."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Health monitoring already running")
            return
        
        logger.info("Starting health monitoring service")
        self._shutdown_event.clear()
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self) -> None:
        """Stop the periodic health monitoring task."""
        logger.info("Stopping health monitoring service")
        self._shutdown_event.set()
        
        if self._monitoring_task and not self._monitoring_task.done():
            try:
                await asyncio.wait_for(self._monitoring_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Health monitoring task did not stop gracefully")
                self._monitoring_task.cancel()
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs periodic health checks."""
        logger.info("Health monitoring loop started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    await self._run_health_checks()
                    
                    # Wait for next check interval or shutdown
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=self.check_interval
                        )
                        break  # Shutdown requested
                    except asyncio.TimeoutError:
                        continue  # Time for next check
                        
                except Exception as e:
                    logger.error(f"Error in health monitoring loop: {e}")
                    # Continue monitoring even if individual checks fail
                    await asyncio.sleep(30)  # Brief pause before retrying
                    
        except asyncio.CancelledError:
            logger.info("Health monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in health monitoring loop: {e}")
        finally:
            logger.info("Health monitoring loop stopped")
    
    async def _run_health_checks(self) -> None:
        """Run health checks for all registered components."""
        current_time = time.time()
        
        for component, check_function in self.health_checks.items():
            try:
                start_time = time.time()
                
                # Run the health check
                is_healthy = await check_function()
                
                response_time = time.time() - start_time
                
                # Create health check result
                result = HealthCheckResult(
                    component=component,
                    healthy=is_healthy,
                    response_time=response_time
                )
                
                # Update component state
                if is_healthy:
                    health_monitor.update_component_state(component, ComponentState.HEALTHY)
                    logger.debug(f"Health check passed for {component} ({response_time:.2f}s)")
                else:
                    health_monitor.update_component_state(
                        component, 
                        ComponentState.DEGRADED, 
                        "Health check failed"
                    )
                    logger.warning(f"Health check failed for {component} ({response_time:.2f}s)")
                
                # Store result in history
                self._store_health_result(component, result)
                self.last_check_times[component] = current_time
                
            except Exception as e:
                response_time = time.time() - start_time
                
                # Create failed health check result
                result = HealthCheckResult(
                    component=component,
                    healthy=False,
                    response_time=response_time,
                    error_message=str(e)
                )
                
                # Update component state
                health_monitor.update_component_state(
                    component, 
                    ComponentState.FAILED, 
                    str(e)
                )
                
                logger.error(f"Health check error for {component}: {e}")
                
                # Store result in history
                self._store_health_result(component, result)
                self.last_check_times[component] = current_time
    
    def _store_health_result(self, component: str, result: HealthCheckResult) -> None:
        """Store health check result in history."""
        if component not in self.health_history:
            self.health_history[component] = []
        
        self.health_history[component].append(result)
        
        # Trim history to max length
        if len(self.health_history[component]) > self.max_history_length:
            self.health_history[component] = self.health_history[component][-self.max_history_length:]
    
    async def run_immediate_health_check(self, component: str) -> Optional[HealthCheckResult]:
        """
        Run an immediate health check for a specific component.
        
        Args:
            component: Name of the component to check
            
        Returns:
            HealthCheckResult or None if component not registered
        """
        if component not in self.health_checks:
            logger.warning(f"No health check registered for component: {component}")
            return None
        
        try:
            start_time = time.time()
            check_function = self.health_checks[component]
            
            is_healthy = await check_function()
            response_time = time.time() - start_time
            
            result = HealthCheckResult(
                component=component,
                healthy=is_healthy,
                response_time=response_time
            )
            
            # Update component state
            if is_healthy:
                health_monitor.update_component_state(component, ComponentState.HEALTHY)
            else:
                health_monitor.update_component_state(
                    component, 
                    ComponentState.DEGRADED, 
                    "Immediate health check failed"
                )
            
            # Store result
            self._store_health_result(component, result)
            self.last_check_times[component] = time.time()
            
            logger.info(f"Immediate health check for {component}: {'PASS' if is_healthy else 'FAIL'} ({response_time:.2f}s)")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            
            result = HealthCheckResult(
                component=component,
                healthy=False,
                response_time=response_time,
                error_message=str(e)
            )
            
            health_monitor.update_component_state(component, ComponentState.FAILED, str(e))
            self._store_health_result(component, result)
            self.last_check_times[component] = time.time()
            
            logger.error(f"Immediate health check error for {component}: {e}")
            return result
    
    def get_component_health_summary(self, component: str) -> Optional[Dict[str, Any]]:
        """
        Get health summary for a specific component.
        
        Args:
            component: Name of the component
            
        Returns:
            Dict containing health summary or None if component not found
        """
        if component not in self.health_history:
            return None
        
        history = self.health_history[component]
        if not history:
            return {
                "component": component,
                "status": "NO_DATA",
                "last_check": None,
                "success_rate": 0.0,
                "avg_response_time": 0.0,
                "recent_errors": []
            }
        
        # Calculate statistics
        recent_checks = history[-10:]  # Last 10 checks
        successful_checks = [r for r in recent_checks if r.healthy]
        failed_checks = [r for r in recent_checks if not r.healthy]
        
        success_rate = len(successful_checks) / len(recent_checks) if recent_checks else 0.0
        avg_response_time = sum(r.response_time for r in recent_checks) / len(recent_checks)
        
        # Get recent errors
        recent_errors = [
            {
                "time": time.time(),  # We don't store timestamps in results yet
                "error": r.error_message
            }
            for r in failed_checks[-5:]  # Last 5 errors
            if r.error_message
        ]
        
        return {
            "component": component,
            "status": health_monitor.get_component_state(component).value,
            "last_check": self.last_check_times.get(component),
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "total_checks": len(history),
            "recent_checks": len(recent_checks),
            "recent_errors": recent_errors
        }
    
    def get_system_health_report(self) -> Dict[str, Any]:
        """
        Get comprehensive system health report.
        
        Returns:
            Dict containing system-wide health information
        """
        # Get overall system health from health monitor
        system_summary = health_monitor.get_system_health_summary()
        
        # Get AI-specific health information
        ai_health = ai_error_handler.get_ai_health_status()
        
        # Get component summaries
        component_summaries = {}
        for component in self.health_checks.keys():
            component_summaries[component] = self.get_component_health_summary(component)
        
        # Get degradation information
        degradation_info = {
            "ai_responses_available": degradation_manager.is_feature_available("ai_responses"),
            "voice_generation_available": degradation_manager.is_feature_available("voice_generation"),
            "audio_playback_available": degradation_manager.is_feature_available("audio_playback"),
            "slash_commands_available": degradation_manager.is_feature_available("slash_commands")
        }
        
        return {
            "timestamp": time.time(),
            "system_summary": system_summary,
            "ai_health": ai_health,
            "component_summaries": component_summaries,
            "degradation_info": degradation_info,
            "monitoring_active": self._monitoring_task is not None and not self._monitoring_task.done()
        }


# Global health monitoring service instance
health_monitoring_service = HealthMonitoringService()