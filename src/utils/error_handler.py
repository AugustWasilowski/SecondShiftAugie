"""
Comprehensive error handling utilities for SecondShiftAugie bot.

Provides centralized error handling, logging, and graceful degradation utilities
to ensure the bot continues operating even when individual components fail.

Requirements addressed:
- 4.1: Fallback to text-only mode when VoxCPM fails
- 4.2: Proper error logging for debugging
- 4.3: Handle missing reference files gracefully
- 4.4: Handle Discord voice channel connection errors gracefully
"""

import asyncio
import functools
import logging
import traceback
from typing import Any, Callable, Optional, TypeVar, Union
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels for different types of failures."""
    CRITICAL = "CRITICAL"  # Bot cannot continue
    HIGH = "HIGH"         # Major feature unavailable
    MEDIUM = "MEDIUM"     # Minor feature degradation
    LOW = "LOW"           # Cosmetic or non-essential failure


class ComponentState(Enum):
    """Component operational states."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class ErrorContext:
    """Context information for error handling."""
    
    def __init__(self, component: str, operation: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        self.component = component
        self.operation = operation
        self.severity = severity
        self.retry_count = 0
        self.max_retries = 3
        self.fallback_enabled = True


def handle_errors(
    context: ErrorContext,
    fallback_value: Any = None,
    log_traceback: bool = True,
    reraise_critical: bool = True
):
    """
    Decorator for comprehensive error handling with graceful degradation.
    
    Args:
        context: Error context information
        fallback_value: Value to return on error
        log_traceback: Whether to log full traceback
        reraise_critical: Whether to reraise critical errors
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Union[T, Any]]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Union[T, Any]:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return _handle_exception(
                    e, context, fallback_value, log_traceback, reraise_critical, func.__name__
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Union[T, Any]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return _handle_exception(
                    e, context, fallback_value, log_traceback, reraise_critical, func.__name__
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


def _handle_exception(
    exception: Exception,
    context: ErrorContext,
    fallback_value: Any,
    log_traceback: bool,
    reraise_critical: bool,
    func_name: str
) -> Any:
    """Handle an exception according to the error context."""
    
    # Log the error with appropriate level
    error_msg = f"Error in {context.component}.{context.operation} ({func_name}): {exception}"
    
    if context.severity == ErrorSeverity.CRITICAL:
        logger.critical(error_msg)
    elif context.severity == ErrorSeverity.HIGH:
        logger.error(error_msg)
    elif context.severity == ErrorSeverity.MEDIUM:
        logger.warning(error_msg)
    else:
        logger.info(error_msg)
    
    # Log traceback if requested
    if log_traceback:
        logger.debug(f"Traceback for {context.component}.{context.operation}:\n{traceback.format_exc()}")
    
    # Increment retry count
    context.retry_count += 1
    
    # Log degradation information
    if context.fallback_enabled and fallback_value is not None:
        logger.info(f"{context.component} entering degraded mode - using fallback behavior")
    
    # Reraise critical errors if requested
    if context.severity == ErrorSeverity.CRITICAL and reraise_critical:
        raise exception
    
    return fallback_value


class ComponentHealthMonitor:
    """Monitor and track component health states."""
    
    def __init__(self):
        self._component_states = {}
        self._error_counts = {}
        self._last_errors = {}
    
    def update_component_state(self, component: str, state: ComponentState, error: Optional[str] = None):
        """Update the state of a component."""
        self._component_states[component] = state
        
        if error:
            self._error_counts[component] = self._error_counts.get(component, 0) + 1
            self._last_errors[component] = error
            
        logger.info(f"Component {component} state: {state.value}")
        if error:
            logger.warning(f"Component {component} error: {error}")
    
    def get_component_state(self, component: str) -> ComponentState:
        """Get the current state of a component."""
        return self._component_states.get(component, ComponentState.HEALTHY)
    
    def is_component_healthy(self, component: str) -> bool:
        """Check if a component is in a healthy state."""
        state = self.get_component_state(component)
        return state in [ComponentState.HEALTHY, ComponentState.DEGRADED]
    
    def get_system_health_summary(self) -> dict:
        """Get a summary of overall system health."""
        total_components = len(self._component_states)
        healthy_count = sum(1 for state in self._component_states.values() 
                          if state == ComponentState.HEALTHY)
        degraded_count = sum(1 for state in self._component_states.values() 
                           if state == ComponentState.DEGRADED)
        failed_count = sum(1 for state in self._component_states.values() 
                         if state == ComponentState.FAILED)
        
        return {
            "total_components": total_components,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "failed": failed_count,
            "overall_health": "HEALTHY" if failed_count == 0 else "DEGRADED" if degraded_count > 0 else "FAILED"
        }


# Global health monitor instance
health_monitor = ComponentHealthMonitor()


def log_component_error(component: str, operation: str, error: Exception, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
    """Log a component error and update health monitoring."""
    error_msg = f"{component}.{operation} failed: {error}"
    
    if severity == ErrorSeverity.CRITICAL:
        logger.critical(error_msg)
        health_monitor.update_component_state(component, ComponentState.FAILED, str(error))
    elif severity == ErrorSeverity.HIGH:
        logger.error(error_msg)
        health_monitor.update_component_state(component, ComponentState.DEGRADED, str(error))
    elif severity == ErrorSeverity.MEDIUM:
        logger.warning(error_msg)
        health_monitor.update_component_state(component, ComponentState.DEGRADED, str(error))
    else:
        logger.info(error_msg)


def log_component_recovery(component: str, operation: str):
    """Log successful component recovery."""
    logger.info(f"{component}.{operation} recovered successfully")
    health_monitor.update_component_state(component, ComponentState.HEALTHY)


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exceptions to catch and retry on
    
    Returns:
        Result of the function call
    
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    delay = base_delay
    
    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func()
            else:
                return func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"All {max_retries} retry attempts failed for {func.__name__}")
                break
            
            logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
            logger.info(f"Retrying in {delay:.1f} seconds...")
            
            await asyncio.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)
    
    raise last_exception


def safe_async_call(coro, default_value=None, log_errors=True):
    """
    Safely execute an async call with error handling.
    
    Args:
        coro: Coroutine to execute
        default_value: Value to return on error
        log_errors: Whether to log errors
    
    Returns:
        Result of coroutine or default_value on error
    """
    async def wrapper():
        try:
            return await coro
        except Exception as e:
            if log_errors:
                logger.error(f"Safe async call failed: {e}")
            return default_value
    
    return wrapper()


class GracefulDegradationManager:
    """Manages graceful degradation of bot features."""
    
    def __init__(self):
        self.disabled_features = set()
        self.degraded_features = set()
        self.feature_fallbacks = {}
    
    def disable_feature(self, feature: str, reason: str):
        """Disable a feature due to errors."""
        self.disabled_features.add(feature)
        logger.warning(f"Feature '{feature}' disabled: {reason}")
    
    def enable_degraded_mode(self, feature: str, fallback_behavior: str):
        """Enable degraded mode for a feature."""
        self.degraded_features.add(feature)
        self.feature_fallbacks[feature] = fallback_behavior
        logger.info(f"Feature '{feature}' in degraded mode: {fallback_behavior}")
    
    def is_feature_available(self, feature: str) -> bool:
        """Check if a feature is available (not disabled)."""
        return feature not in self.disabled_features
    
    def is_feature_degraded(self, feature: str) -> bool:
        """Check if a feature is in degraded mode."""
        return feature in self.degraded_features
    
    def get_feature_status(self, feature: str) -> str:
        """Get the status of a feature."""
        if feature in self.disabled_features:
            return "DISABLED"
        elif feature in self.degraded_features:
            return "DEGRADED"
        else:
            return "NORMAL"
    
    def restore_feature(self, feature: str):
        """Restore a feature to normal operation."""
        self.disabled_features.discard(feature)
        self.degraded_features.discard(feature)
        self.feature_fallbacks.pop(feature, None)
        logger.info(f"Feature '{feature}' restored to normal operation")


# Global degradation manager instance
degradation_manager = GracefulDegradationManager()