"""
Setup and initialization for comprehensive error handling and monitoring.

This module initializes all error handling, monitoring, and recovery components
for the memory system, ensuring they work together seamlessly.

Requirements addressed:
- 5.5: Graceful degradation and error handling with appropriate fallbacks
- 6.1: Detailed logging for performance monitoring
- 6.3: Error recovery mechanisms for common failure scenarios
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any

from .performance_monitor import performance_monitor
from .health_checks import health_checker
from .recovery_manager import recovery_manager, register_default_recovery_actions
from .monitoring_endpoints import monitoring_endpoints, set_memory_service
from .exceptions import MemorySystemError, MemoryErrorSeverity


logger = logging.getLogger(__name__)


async def initialize_error_handling_system(
    memory_service=None,
    notification_callback: Optional[Callable] = None,
    alert_callback: Optional[Callable] = None
) -> bool:
    """
    Initialize the comprehensive error handling and monitoring system.
    
    Args:
        memory_service: MemoryService instance to monitor
        notification_callback: Callback for user notifications
        alert_callback: Callback for performance alerts
        
    Returns:
        bool: True if initialization successful
    """
    try:
        logger.info("Initializing comprehensive error handling system")
        
        # 1. Initialize performance monitoring
        if alert_callback:
            performance_monitor.alert_callback = alert_callback
        
        performance_monitor.start_monitoring()
        logger.info("Performance monitoring initialized")
        
        # 2. Initialize recovery manager
        if notification_callback:
            recovery_manager.notification_callback = notification_callback
        
        # Register default recovery actions
        register_default_recovery_actions()
        logger.info("Recovery manager initialized with default actions")
        
        # 3. Set up monitoring endpoints
        if memory_service:
            set_memory_service(memory_service)
        
        logger.info("Monitoring endpoints initialized")
        
        # 4. Register custom health checks if memory service is available
        if memory_service:
            await _register_memory_service_health_checks(memory_service)
        
        # 5. Set up error handling integration
        await _setup_error_handling_integration()
        
        logger.info("Error handling system initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize error handling system: {e}")
        return False


async def _register_memory_service_health_checks(memory_service) -> None:
    """Register health checks for memory service components."""
    try:
        # Database health check
        if hasattr(memory_service, 'db_pool') and memory_service.db_pool:
            from .health_checks import check_database_health
            
            health_checker.register_health_check(
                "database",
                lambda: check_database_health(memory_service.db_pool),
                interval=60.0,
                recovery_action=lambda ctx: _recover_database_connection(memory_service, ctx)
            )
        
        # Embedding service health check
        if hasattr(memory_service, 'embedding_client') and memory_service.embedding_client:
            from .health_checks import check_embedding_service_health
            
            health_checker.register_health_check(
                "embedding_service",
                lambda: check_embedding_service_health(memory_service.embedding_client),
                interval=120.0,
                recovery_action=lambda ctx: _recover_embedding_service(memory_service, ctx)
            )
        
        # Memory service health check
        from .health_checks import check_memory_service_health
        
        health_checker.register_health_check(
            "memory_service",
            lambda: check_memory_service_health(memory_service),
            interval=300.0,
            recovery_action=lambda ctx: _recover_memory_service(memory_service, ctx)
        )
        
        logger.info("Memory service health checks registered")
        
    except Exception as e:
        logger.error(f"Failed to register memory service health checks: {e}")


async def _setup_error_handling_integration() -> None:
    """Set up integration between error handling components."""
    try:
        # Set up performance monitor to trigger recovery on threshold violations
        def performance_alert_handler(alert_data: Dict[str, Any]) -> None:
            """Handle performance alerts by triggering recovery if needed."""
            try:
                severity = alert_data.get("severity", "WARNING")
                metric_name = alert_data.get("metric_name", "unknown")
                
                if severity == "CRITICAL":
                    # Trigger recovery for critical performance issues
                    component = _extract_component_from_metric(metric_name)
                    if component:
                        asyncio.create_task(_trigger_performance_recovery(component, alert_data))
                        
            except Exception as e:
                logger.error(f"Performance alert handler failed: {e}")
        
        # Set the alert handler
        performance_monitor.alert_callback = performance_alert_handler
        
        logger.info("Error handling integration set up")
        
    except Exception as e:
        logger.error(f"Failed to set up error handling integration: {e}")


def _extract_component_from_metric(metric_name: str) -> Optional[str]:
    """Extract component name from metric name."""
    if "database" in metric_name or "stm" in metric_name:
        return "database"
    elif "embedding" in metric_name:
        return "embedding_service"
    elif "ltm" in metric_name or "memory" in metric_name:
        return "memory_service"
    else:
        return None


async def _trigger_performance_recovery(component: str, alert_data: Dict[str, Any]) -> None:
    """Trigger recovery for performance-related issues."""
    try:
        logger.warning(f"Triggering performance recovery for {component}: {alert_data}")
        
        # Create a performance-related error
        from .exceptions import MemoryPerformanceError
        
        error = MemoryPerformanceError(
            f"Performance threshold exceeded for {alert_data.get('metric_name')}",
            operation_time=alert_data.get('current_value')
        )
        
        # Handle the error through recovery manager
        await recovery_manager.handle_error(error, component, "performance_monitoring")
        
    except Exception as e:
        logger.error(f"Failed to trigger performance recovery: {e}")


async def _recover_database_connection(memory_service, context: Dict[str, Any]) -> None:
    """Recovery action for database connection issues."""
    try:
        logger.info("Attempting database connection recovery")
        
        # Close existing connection pool
        if hasattr(memory_service, 'db_pool') and memory_service.db_pool:
            await memory_service.db_pool.close()
            memory_service.db_pool = None
        
        # Reinitialize database connection
        success = await memory_service._initialize_database()
        
        if success:
            logger.info("Database connection recovery successful")
        else:
            raise Exception("Failed to reinitialize database connection")
            
    except Exception as e:
        logger.error(f"Database connection recovery failed: {e}")
        raise


async def _recover_embedding_service(memory_service, context: Dict[str, Any]) -> None:
    """Recovery action for embedding service issues."""
    try:
        logger.info("Attempting embedding service recovery")
        
        # Close existing embedding client
        if hasattr(memory_service, 'embedding_client') and memory_service.embedding_client:
            await memory_service.embedding_client.close()
            memory_service.embedding_client = None
        
        # Reinitialize embedding client
        success = await memory_service._initialize_embedding_client()
        
        if success:
            logger.info("Embedding service recovery successful")
        else:
            raise Exception("Failed to reinitialize embedding client")
            
    except Exception as e:
        logger.error(f"Embedding service recovery failed: {e}")
        raise


async def _recover_memory_service(memory_service, context: Dict[str, Any]) -> None:
    """Recovery action for memory service issues."""
    try:
        logger.info("Attempting memory service recovery")
        
        # Clear caches and reset state
        if hasattr(memory_service, '_initialized'):
            memory_service._initialized = False
        
        # Attempt reinitialization
        success = await memory_service.initialize()
        
        if success:
            logger.info("Memory service recovery successful")
        else:
            raise Exception("Failed to reinitialize memory service")
            
    except Exception as e:
        logger.error(f"Memory service recovery failed: {e}")
        raise


async def setup_discord_error_notifications(bot_instance) -> Callable:
    """
    Set up Discord notifications for memory system errors.
    
    Args:
        bot_instance: Discord bot instance
        
    Returns:
        Notification callback function
    """
    async def discord_notification_callback(notification_data: Dict[str, Any]) -> None:
        """Send Discord notifications for memory system events."""
        try:
            notification_type = notification_data.get("type", "unknown")
            message = notification_data.get("message", "Memory system notification")
            
            # Determine notification channel (could be configured)
            # For now, just log the notification
            if notification_type == "degradation":
                logger.warning(f"Discord notification (degradation): {message}")
            elif notification_type == "recovery":
                logger.info(f"Discord notification (recovery): {message}")
            else:
                logger.info(f"Discord notification ({notification_type}): {message}")
            
            # Here you could send actual Discord messages to a specific channel
            # Example:
            # channel = bot_instance.get_channel(NOTIFICATION_CHANNEL_ID)
            # if channel:
            #     await channel.send(f"🔧 **Memory System**: {message}")
            
        except Exception as e:
            logger.error(f"Discord notification callback failed: {e}")
    
    return discord_notification_callback


def setup_logging_for_error_handling() -> None:
    """Set up enhanced logging for error handling components."""
    try:
        # Configure logging for error handling modules
        error_handling_loggers = [
            "src.memory.exceptions",
            "src.memory.performance_monitor",
            "src.memory.health_checks",
            "src.memory.recovery_manager",
            "src.memory.monitoring_endpoints"
        ]
        
        for logger_name in error_handling_loggers:
            logger_instance = logging.getLogger(logger_name)
            logger_instance.setLevel(logging.INFO)
            
            # Add specific formatting for error handling logs
            if not logger_instance.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
                )
                handler.setFormatter(formatter)
                logger_instance.addHandler(handler)
        
        logger.info("Enhanced logging configured for error handling components")
        
    except Exception as e:
        logger.error(f"Failed to set up error handling logging: {e}")


async def shutdown_error_handling_system() -> None:
    """Gracefully shutdown the error handling system."""
    try:
        logger.info("Shutting down error handling system")
        
        # Stop performance monitoring
        performance_monitor.stop_monitoring()
        
        # Stop health monitoring
        await health_checker.stop_monitoring()
        
        # Clear recovery manager state
        recovery_manager.recovery_attempts.clear()
        recovery_manager.last_recovery_times.clear()
        
        logger.info("Error handling system shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during error handling system shutdown: {e}")


# Utility function for easy integration
async def setup_memory_error_handling(
    memory_service,
    bot_instance=None,
    enable_discord_notifications: bool = True
) -> bool:
    """
    Easy setup function for memory system error handling.
    
    Args:
        memory_service: MemoryService instance
        bot_instance: Optional Discord bot instance
        enable_discord_notifications: Whether to enable Discord notifications
        
    Returns:
        bool: True if setup successful
    """
    try:
        # Set up logging
        setup_logging_for_error_handling()
        
        # Set up Discord notifications if requested
        notification_callback = None
        if enable_discord_notifications and bot_instance:
            notification_callback = await setup_discord_error_notifications(bot_instance)
        
        # Initialize the error handling system
        success = await initialize_error_handling_system(
            memory_service=memory_service,
            notification_callback=notification_callback
        )
        
        if success:
            logger.info("Memory system error handling setup completed successfully")
        else:
            logger.error("Memory system error handling setup failed")
        
        return success
        
    except Exception as e:
        logger.error(f"Failed to set up memory error handling: {e}")
        return False