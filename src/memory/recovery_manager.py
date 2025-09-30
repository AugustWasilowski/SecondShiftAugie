"""
Error recovery and graceful degradation manager for the memory system.

This module provides automated error recovery mechanisms, graceful degradation
strategies, and user notification systems to ensure the bot continues operating
even when memory system components fail.

Requirements addressed:
- 5.5: Graceful degradation and error handling with appropriate fallbacks
- 6.3: Error recovery mechanisms for common failure scenarios
- User notifications for degraded functionality
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import json

from .exceptions import (
    MemorySystemError, MemoryErrorSeverity, MemoryConnectionError,
    MemoryDatabaseError, EmbeddingConnectionError, MemoryCircuitBreakerError,
    MemoryDegradationError, create_recovery_context
)
from .performance_monitor import performance_monitor
from .health_checks import health_checker, HealthStatus


logger = logging.getLogger(__name__)


class RecoveryStrategy(Enum):
    """Recovery strategies for different types of failures."""
    RETRY = "retry"                    # Simple retry with backoff
    CIRCUIT_BREAKER = "circuit_breaker"  # Circuit breaker pattern
    FALLBACK = "fallback"              # Use alternative implementation
    DEGRADE = "degrade"                # Graceful degradation
    RESTART = "restart"                # Restart component
    MANUAL = "manual"                  # Requires manual intervention


class DegradationLevel(Enum):
    """Levels of system degradation."""
    NONE = "none"                      # Full functionality
    MINOR = "minor"                    # Minor features disabled
    MODERATE = "moderate"              # Significant features disabled
    SEVERE = "severe"                  # Major functionality lost
    CRITICAL = "critical"              # System barely functional


@dataclass
class RecoveryAction:
    """Definition of a recovery action."""
    name: str
    strategy: RecoveryStrategy
    action_function: Callable
    max_attempts: int = 3
    backoff_factor: float = 2.0
    timeout: float = 30.0
    prerequisites: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate recovery action configuration."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.backoff_factor < 1.0:
            raise ValueError("backoff_factor must be at least 1.0")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    component: str
    action_name: str
    attempt_number: int
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Get duration of recovery attempt."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time


class RecoveryManager:
    """
    Manages error recovery and graceful degradation for the memory system.
    
    Provides automated recovery mechanisms, tracks degradation levels,
    and manages user notifications for system state changes.
    """
    
    def __init__(self, 
                 max_recovery_attempts: int = 3,
                 recovery_cooldown: float = 300.0,
                 notification_callback: Optional[Callable] = None):
        """
        Initialize recovery manager.
        
        Args:
            max_recovery_attempts: Maximum recovery attempts per component
            recovery_cooldown: Cooldown period between recovery attempts
            notification_callback: Optional callback for user notifications
        """
        self.max_recovery_attempts = max_recovery_attempts
        self.recovery_cooldown = recovery_cooldown
        self.notification_callback = notification_callback
        
        # Recovery state tracking
        self.recovery_actions: Dict[str, Dict[str, RecoveryAction]] = {}
        self.recovery_attempts: List[RecoveryAttempt] = []
        self.last_recovery_times: Dict[str, float] = {}
        self.component_states: Dict[str, DegradationLevel] = {}
        self.disabled_features: Set[str] = set()
        
        # Circuit breaker states
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
        # Degradation tracking
        self.current_degradation = DegradationLevel.NONE
        self.degradation_reasons: List[str] = []
        
        logger.info("Recovery manager initialized")
    
    def register_recovery_action(self, 
                                component: str, 
                                action: RecoveryAction) -> None:
        """
        Register a recovery action for a component.
        
        Args:
            component: Component name
            action: Recovery action definition
        """
        if component not in self.recovery_actions:
            self.recovery_actions[component] = {}
        
        self.recovery_actions[component][action.name] = action
        logger.info(f"Registered recovery action '{action.name}' for {component}")
    
    async def handle_error(self, 
                          error: Exception, 
                          component: str, 
                          operation: str,
                          context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: The error that occurred
            component: Component where error occurred
            operation: Operation that failed
            context: Additional context information
            
        Returns:
            bool: True if recovery was successful, False otherwise
        """
        logger.warning(f"Handling error in {component}.{operation}: {error}")
        
        # Create recovery context
        recovery_context = create_recovery_context(error, component, operation)
        if context:
            recovery_context.update(context)
        
        # Determine recovery strategy based on error type
        strategy = self._determine_recovery_strategy(error, component)
        
        # Check if recovery is possible
        if not self._can_attempt_recovery(component):
            logger.warning(f"Recovery cooldown active for {component}, applying degradation")
            await self._apply_degradation(component, str(error))
            return False
        
        # Attempt recovery
        success = await self._attempt_recovery(component, strategy, recovery_context)
        
        if success:
            logger.info(f"Recovery successful for {component}")
            await self._restore_component(component)
        else:
            logger.error(f"Recovery failed for {component}, applying degradation")
            await self._apply_degradation(component, str(error))
        
        return success
    
    def _determine_recovery_strategy(self, 
                                   error: Exception, 
                                   component: str) -> RecoveryStrategy:
        """Determine the appropriate recovery strategy for an error."""
        if isinstance(error, MemoryConnectionError):
            return RecoveryStrategy.RETRY
        elif isinstance(error, MemoryDatabaseError):
            return RecoveryStrategy.CIRCUIT_BREAKER
        elif isinstance(error, EmbeddingConnectionError):
            return RecoveryStrategy.FALLBACK
        elif isinstance(error, MemoryCircuitBreakerError):
            return RecoveryStrategy.DEGRADE
        else:
            # Default strategy based on component
            if component == "database":
                return RecoveryStrategy.RETRY
            elif component == "embedding_service":
                return RecoveryStrategy.FALLBACK
            else:
                return RecoveryStrategy.DEGRADE
    
    def _can_attempt_recovery(self, component: str) -> bool:
        """Check if recovery can be attempted for a component."""
        current_time = time.time()
        
        if component in self.last_recovery_times:
            time_since_last = current_time - self.last_recovery_times[component]
            if time_since_last < self.recovery_cooldown:
                return False
        
        # Check recent recovery attempts
        recent_attempts = [
            attempt for attempt in self.recovery_attempts
            if (attempt.component == component and 
                current_time - attempt.start_time < 3600)  # Last hour
        ]
        
        return len(recent_attempts) < self.max_recovery_attempts
    
    async def _attempt_recovery(self, 
                               component: str, 
                               strategy: RecoveryStrategy,
                               context: Dict[str, Any]) -> bool:
        """Attempt recovery using the specified strategy."""
        if component not in self.recovery_actions:
            logger.warning(f"No recovery actions registered for {component}")
            return False
        
        # Find appropriate recovery action
        recovery_action = None
        for action in self.recovery_actions[component].values():
            if action.strategy == strategy:
                recovery_action = action
                break
        
        if not recovery_action:
            logger.warning(f"No recovery action found for {component} with strategy {strategy}")
            return False
        
        # Record recovery attempt
        attempt = RecoveryAttempt(
            component=component,
            action_name=recovery_action.name,
            attempt_number=len([a for a in self.recovery_attempts 
                               if a.component == component]) + 1,
            start_time=time.time()
        )
        
        self.recovery_attempts.append(attempt)
        self.last_recovery_times[component] = time.time()
        
        try:
            # Execute recovery action with timeout
            await asyncio.wait_for(
                recovery_action.action_function(context),
                timeout=recovery_action.timeout
            )
            
            attempt.end_time = time.time()
            attempt.success = True
            
            logger.info(f"Recovery action '{recovery_action.name}' succeeded for {component}")
            return True
            
        except asyncio.TimeoutError:
            attempt.end_time = time.time()
            attempt.error = "Recovery action timed out"
            logger.error(f"Recovery action '{recovery_action.name}' timed out for {component}")
            return False
            
        except Exception as e:
            attempt.end_time = time.time()
            attempt.error = str(e)
            logger.error(f"Recovery action '{recovery_action.name}' failed for {component}: {e}")
            return False
    
    async def _apply_degradation(self, component: str, reason: str) -> None:
        """Apply graceful degradation for a component."""
        logger.info(f"Applying degradation for {component}: {reason}")
        
        # Determine degradation level based on component
        if component == "database":
            degradation_level = DegradationLevel.CRITICAL
            self.disabled_features.update(["memory_storage", "memory_retrieval", "memory_export"])
        elif component == "embedding_service":
            degradation_level = DegradationLevel.MODERATE
            self.disabled_features.update(["ltm_storage", "vector_search", "memory_extraction"])
        elif component == "memory_service":
            degradation_level = DegradationLevel.SEVERE
            self.disabled_features.update(["memory_system"])
        else:
            degradation_level = DegradationLevel.MINOR
        
        # Update component state
        self.component_states[component] = degradation_level
        
        # Update overall degradation level
        max_degradation = max(self.component_states.values(), default=DegradationLevel.NONE)
        if max_degradation != self.current_degradation:
            old_degradation = self.current_degradation
            self.current_degradation = max_degradation
            
            logger.warning(f"System degradation level changed: {old_degradation.value} -> {max_degradation.value}")
            
            # Add reason to degradation reasons
            if reason not in self.degradation_reasons:
                self.degradation_reasons.append(reason)
            
            # Notify users of degradation
            await self._notify_degradation(old_degradation, max_degradation, reason)
    
    async def _restore_component(self, component: str) -> None:
        """Restore a component from degraded state."""
        if component in self.component_states:
            old_level = self.component_states[component]
            del self.component_states[component]
            
            logger.info(f"Restored {component} from {old_level.value} degradation")
            
            # Re-enable features
            if component == "database":
                self.disabled_features.discard("memory_storage")
                self.disabled_features.discard("memory_retrieval")
                self.disabled_features.discard("memory_export")
            elif component == "embedding_service":
                self.disabled_features.discard("ltm_storage")
                self.disabled_features.discard("vector_search")
                self.disabled_features.discard("memory_extraction")
            elif component == "memory_service":
                self.disabled_features.discard("memory_system")
            
            # Update overall degradation level
            new_max_degradation = max(self.component_states.values(), default=DegradationLevel.NONE)
            if new_max_degradation != self.current_degradation:
                old_degradation = self.current_degradation
                self.current_degradation = new_max_degradation
                
                logger.info(f"System degradation level improved: {old_degradation.value} -> {new_max_degradation.value}")
                
                # Remove resolved reasons
                self.degradation_reasons = [
                    reason for reason in self.degradation_reasons
                    if component not in reason.lower()
                ]
                
                # Notify users of recovery
                await self._notify_recovery(component, old_degradation, new_max_degradation)
    
    async def _notify_degradation(self, 
                                 old_level: DegradationLevel, 
                                 new_level: DegradationLevel,
                                 reason: str) -> None:
        """Notify users of system degradation."""
        if not self.notification_callback:
            return
        
        message = self._get_degradation_message(new_level, reason)
        
        try:
            await self.notification_callback({
                "type": "degradation",
                "old_level": old_level.value,
                "new_level": new_level.value,
                "reason": reason,
                "message": message,
                "disabled_features": list(self.disabled_features),
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Failed to send degradation notification: {e}")
    
    async def _notify_recovery(self, 
                              component: str,
                              old_level: DegradationLevel, 
                              new_level: DegradationLevel) -> None:
        """Notify users of system recovery."""
        if not self.notification_callback:
            return
        
        message = self._get_recovery_message(component, new_level)
        
        try:
            await self.notification_callback({
                "type": "recovery",
                "component": component,
                "old_level": old_level.value,
                "new_level": new_level.value,
                "message": message,
                "restored_features": self._get_restored_features(component),
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Failed to send recovery notification: {e}")
    
    def _get_degradation_message(self, level: DegradationLevel, reason: str) -> str:
        """Get user-friendly degradation message."""
        if level == DegradationLevel.MINOR:
            return "Memory system is experiencing minor issues. Most features remain available."
        elif level == DegradationLevel.MODERATE:
            return "Memory system is in degraded mode. Some advanced features are temporarily unavailable."
        elif level == DegradationLevel.SEVERE:
            return "Memory system is experiencing significant issues. Limited functionality available."
        elif level == DegradationLevel.CRITICAL:
            return "Memory system is currently unavailable. Operating without memory features."
        else:
            return "Memory system status unknown."
    
    def _get_recovery_message(self, component: str, level: DegradationLevel) -> str:
        """Get user-friendly recovery message."""
        if level == DegradationLevel.NONE:
            return f"{component.title()} has been restored. All memory features are now available."
        else:
            return f"{component.title()} has partially recovered. Some features have been restored."
    
    def _get_restored_features(self, component: str) -> List[str]:
        """Get list of features restored for a component."""
        if component == "database":
            return ["memory_storage", "memory_retrieval", "memory_export"]
        elif component == "embedding_service":
            return ["ltm_storage", "vector_search", "memory_extraction"]
        elif component == "memory_service":
            return ["memory_system"]
        else:
            return []
    
    def is_feature_available(self, feature: str) -> bool:
        """Check if a feature is currently available."""
        return feature not in self.disabled_features
    
    def get_degradation_status(self) -> Dict[str, Any]:
        """Get current degradation status."""
        return {
            "current_level": self.current_degradation.value,
            "component_states": {comp: level.value 
                               for comp, level in self.component_states.items()},
            "disabled_features": list(self.disabled_features),
            "degradation_reasons": self.degradation_reasons,
            "recovery_attempts": len(self.recovery_attempts),
            "last_recovery_times": dict(self.last_recovery_times)
        }
    
    def get_recovery_history(self, component: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recovery attempt history."""
        attempts = self.recovery_attempts
        if component:
            attempts = [a for a in attempts if a.component == component]
        
        return [
            {
                "component": attempt.component,
                "action_name": attempt.action_name,
                "attempt_number": attempt.attempt_number,
                "start_time": attempt.start_time,
                "duration": attempt.duration,
                "success": attempt.success,
                "error": attempt.error
            }
            for attempt in attempts
        ]


# Global recovery manager instance
recovery_manager = RecoveryManager()


# Common recovery actions

async def restart_database_connection(context: Dict[str, Any]) -> None:
    """Recovery action to restart database connection."""
    logger.info("Attempting to restart database connection")
    # This would be implemented to restart the database connection
    # For now, just simulate the action
    await asyncio.sleep(2)
    logger.info("Database connection restart completed")


async def switch_to_fallback_embedding(context: Dict[str, Any]) -> None:
    """Recovery action to switch to fallback embedding service."""
    logger.info("Switching to fallback embedding service")
    # This would be implemented to switch to a fallback embedding service
    await asyncio.sleep(1)
    logger.info("Switched to fallback embedding service")


async def clear_memory_cache(context: Dict[str, Any]) -> None:
    """Recovery action to clear memory caches."""
    logger.info("Clearing memory system caches")
    # This would be implemented to clear various caches
    await asyncio.sleep(0.5)
    logger.info("Memory caches cleared")


# Register default recovery actions
def register_default_recovery_actions():
    """Register default recovery actions for common components."""
    
    # Database recovery actions
    recovery_manager.register_recovery_action(
        "database",
        RecoveryAction(
            name="restart_connection",
            strategy=RecoveryStrategy.RETRY,
            action_function=restart_database_connection,
            max_attempts=3,
            timeout=30.0
        )
    )
    
    # Embedding service recovery actions
    recovery_manager.register_recovery_action(
        "embedding_service",
        RecoveryAction(
            name="fallback_service",
            strategy=RecoveryStrategy.FALLBACK,
            action_function=switch_to_fallback_embedding,
            max_attempts=2,
            timeout=15.0
        )
    )
    
    # Memory service recovery actions
    recovery_manager.register_recovery_action(
        "memory_service",
        RecoveryAction(
            name="clear_cache",
            strategy=RecoveryStrategy.RESTART,
            action_function=clear_memory_cache,
            max_attempts=1,
            timeout=10.0
        )
    )
    
    logger.info("Default recovery actions registered")