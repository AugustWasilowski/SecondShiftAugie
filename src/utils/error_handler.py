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
import time
from typing import Any, Callable, Optional, TypeVar, Union, Dict
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


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, requests blocked
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for AI service calls.
    
    Implements requirement 1.3, 2.3, 2.5: Circuit breaker pattern for Ollama requests
    to prevent cascading failures and enable graceful degradation.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
        name: str = "CircuitBreaker"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
            expected_exception: Exception type that triggers circuit breaker
            name: Name for logging purposes
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        
        logger.info(f"Circuit breaker '{name}' initialized with threshold={failure_threshold}, timeout={recovery_timeout}s")
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker to a function."""
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await self._call_with_circuit_breaker(func, args, kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we'll run them in a way that respects the circuit breaker
            if self.state == CircuitBreakerState.OPEN:
                if not self._should_attempt_reset():
                    raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
                else:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    async def _call_with_circuit_breaker(self, func: Callable, args: tuple, kwargs: dict):
        """Execute function with circuit breaker logic."""
        if self.state == CircuitBreakerState.OPEN:
            if not self._should_attempt_reset():
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
            else:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.info(f"Circuit breaker '{self.name}' recovered - returning to CLOSED state")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on successful call
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitBreakerState.OPEN:
                logger.error(f"Circuit breaker '{self.name}' OPENED after {self.failure_count} failures")
                self.state = CircuitBreakerState.OPEN
                
                # Update health monitoring
                health_monitor.update_component_state(
                    f"circuit_breaker_{self.name.lower()}", 
                    ComponentState.FAILED,
                    f"Circuit breaker opened after {self.failure_count} failures"
                )
        else:
            logger.warning(f"Circuit breaker '{self.name}' failure {self.failure_count}/{self.failure_threshold}")
    
    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state
    
    def get_failure_count(self) -> int:
        """Get current failure count."""
        return self.failure_count
    
    def reset(self):
        """Manually reset the circuit breaker."""
        logger.info(f"Circuit breaker '{self.name}' manually reset")
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        
        # Update health monitoring
        health_monitor.update_component_state(
            f"circuit_breaker_{self.name.lower()}", 
            ComponentState.HEALTHY,
            None
        )


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class AIErrorHandler:
    """
    Specialized error handler for AI service interactions.
    
    Implements requirements:
    - 1.3: Provide fallback responses when Ollama fails
    - 2.3: Implement retry logic with exponential backoff  
    - 2.5: Continue operating in degraded mode
    - 6.2: Proper timeout and error handling for API calls
    - 6.4: Detailed logging for AI interactions and errors
    - 6.5: Indicate when AI features are unavailable
    """
    
    def __init__(self):
        """Initialize AI error handler with circuit breakers and monitoring."""
        # Circuit breaker for Ollama API calls
        self.ollama_circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=120.0,  # 2 minutes
            expected_exception=Exception,
            name="OllamaAPI"
        )
        
        # Circuit breaker for AI response generation
        self.ai_response_circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,  # 1 minute
            expected_exception=Exception,
            name="AIResponse"
        )
        
        # Error tracking
        self.error_counts = {
            "connection_errors": 0,
            "timeout_errors": 0,
            "model_errors": 0,
            "response_errors": 0,
            "circuit_breaker_trips": 0
        }
        
        self.last_errors = {}
        self.error_timestamps = []
        
        logger.info("AI error handler initialized with circuit breakers")
    
    def log_ai_interaction(
        self, 
        operation: str, 
        success: bool, 
        duration: Optional[float] = None,
        error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log detailed AI interaction information.
        
        Implements requirement 6.4: Add detailed logging for AI interactions and errors.
        
        Args:
            operation: Name of the AI operation
            success: Whether the operation succeeded
            duration: Operation duration in seconds
            error: Exception if operation failed
            details: Additional operation details
        """
        timestamp = time.time()
        
        # Prepare log message
        status = "SUCCESS" if success else "FAILED"
        duration_str = f" ({duration:.2f}s)" if duration else ""
        
        log_msg = f"AI {operation} {status}{duration_str}"
        
        if details:
            detail_parts = []
            for key, value in details.items():
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                detail_parts.append(f"{key}={value}")
            
            if detail_parts:
                log_msg += f" - {', '.join(detail_parts)}"
        
        # Log with appropriate level
        if success:
            logger.info(log_msg)
        else:
            logger.error(log_msg)
            
            if error:
                logger.error(f"AI {operation} error details: {error}")
                
                # Track error types for monitoring
                error_type = type(error).__name__
                if "connection" in error_type.lower() or "network" in str(error).lower():
                    self.error_counts["connection_errors"] += 1
                elif "timeout" in error_type.lower() or "timeout" in str(error).lower():
                    self.error_counts["timeout_errors"] += 1
                elif "model" in str(error).lower():
                    self.error_counts["model_errors"] += 1
                else:
                    self.error_counts["response_errors"] += 1
                
                # Store last error for debugging
                self.last_errors[operation] = {
                    "error": str(error),
                    "timestamp": timestamp,
                    "type": error_type
                }
        
        # Track error timestamps for rate monitoring
        if not success:
            self.error_timestamps.append(timestamp)
            # Keep only last hour of errors
            cutoff = timestamp - 3600
            self.error_timestamps = [t for t in self.error_timestamps if t > cutoff]
    
    def get_ai_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive AI health status.
        
        Returns:
            Dict containing AI health information
        """
        current_time = time.time()
        
        # Calculate error rate (errors per hour)
        recent_errors = len(self.error_timestamps)
        
        # Get circuit breaker states
        ollama_cb_state = self.ollama_circuit_breaker.get_state()
        response_cb_state = self.ai_response_circuit_breaker.get_state()
        
        # Determine overall AI health
        if (ollama_cb_state == CircuitBreakerState.OPEN or 
            response_cb_state == CircuitBreakerState.OPEN):
            overall_health = "FAILED"
        elif (ollama_cb_state == CircuitBreakerState.HALF_OPEN or 
              response_cb_state == CircuitBreakerState.HALF_OPEN or
              recent_errors > 10):
            overall_health = "DEGRADED"
        else:
            overall_health = "HEALTHY"
        
        return {
            "overall_health": overall_health,
            "circuit_breakers": {
                "ollama_api": {
                    "state": ollama_cb_state.value,
                    "failure_count": self.ollama_circuit_breaker.get_failure_count()
                },
                "ai_response": {
                    "state": response_cb_state.value,
                    "failure_count": self.ai_response_circuit_breaker.get_failure_count()
                }
            },
            "error_counts": self.error_counts.copy(),
            "recent_error_rate": recent_errors,
            "last_errors": {k: v["error"] for k, v in self.last_errors.items()}
        }
    
    def should_use_ai(self) -> bool:
        """
        Determine if AI should be used based on circuit breaker states.
        
        Implements requirement 6.5: Indicate when AI features are unavailable.
        
        Returns:
            bool: True if AI should be used, False if degraded mode should be used
        """
        ollama_available = self.ollama_circuit_breaker.get_state() != CircuitBreakerState.OPEN
        response_available = self.ai_response_circuit_breaker.get_state() != CircuitBreakerState.OPEN
        
        return ollama_available and response_available
    
    def get_degradation_reason(self) -> Optional[str]:
        """
        Get reason why AI is in degraded mode.
        
        Returns:
            String describing degradation reason, or None if not degraded
        """
        ollama_state = self.ollama_circuit_breaker.get_state()
        response_state = self.ai_response_circuit_breaker.get_state()
        
        if ollama_state == CircuitBreakerState.OPEN:
            return "Ollama API circuit breaker is open due to repeated failures"
        elif response_state == CircuitBreakerState.OPEN:
            return "AI response generation circuit breaker is open due to repeated failures"
        elif ollama_state == CircuitBreakerState.HALF_OPEN:
            return "Ollama API is recovering from failures"
        elif response_state == CircuitBreakerState.HALF_OPEN:
            return "AI response generation is recovering from failures"
        
        return None
    
    def reset_circuit_breakers(self):
        """Manually reset all AI circuit breakers."""
        logger.info("Manually resetting AI circuit breakers")
        self.ollama_circuit_breaker.reset()
        self.ai_response_circuit_breaker.reset()
        
        # Clear error tracking
        self.error_counts = {key: 0 for key in self.error_counts}
        self.error_timestamps.clear()
        self.last_errors.clear()


# Global AI error handler instance
ai_error_handler = AIErrorHandler()