"""
Custom exception classes for memory operations.

This module defines a comprehensive hierarchy of exceptions for the memory system,
providing specific error types for different failure scenarios to enable better
error handling and recovery mechanisms.

Requirements addressed:
- 5.5: Graceful degradation and error handling with appropriate fallbacks
- 6.1: Detailed logging for performance monitoring
- 6.3: Error recovery mechanisms for common failure scenarios
"""

from typing import Optional, Dict, Any
from enum import Enum


class MemoryErrorSeverity(Enum):
    """Severity levels for memory system errors."""
    LOW = "LOW"           # Minor issues, system continues normally
    MEDIUM = "MEDIUM"     # Degraded functionality, some features unavailable
    HIGH = "HIGH"         # Major issues, significant functionality lost
    CRITICAL = "CRITICAL" # System failure, memory system unusable


class MemorySystemError(Exception):
    """
    Base exception for all memory system errors.
    
    Provides common functionality for error tracking, severity classification,
    and recovery suggestions.
    """
    
    def __init__(
        self, 
        message: str, 
        severity: MemoryErrorSeverity = MemoryErrorSeverity.MEDIUM,
        component: Optional[str] = None,
        operation: Optional[str] = None,
        recoverable: bool = True,
        recovery_suggestion: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize memory system error.
        
        Args:
            message: Human-readable error message
            severity: Error severity level
            component: Component where error occurred
            operation: Operation that failed
            recoverable: Whether error is recoverable
            recovery_suggestion: Suggested recovery action
            error_code: Unique error code for tracking
            context: Additional context information
        """
        super().__init__(message)
        self.severity = severity
        self.component = component or "unknown"
        self.operation = operation or "unknown"
        self.recoverable = recoverable
        self.recovery_suggestion = recovery_suggestion
        self.error_code = error_code
        self.context = context or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "severity": self.severity.value,
            "component": self.component,
            "operation": self.operation,
            "recoverable": self.recoverable,
            "recovery_suggestion": self.recovery_suggestion,
            "error_code": self.error_code,
            "context": self.context
        }
    
    def get_user_message(self) -> str:
        """Get user-friendly error message."""
        if self.severity == MemoryErrorSeverity.LOW:
            return "Memory system experienced a minor issue but is continuing normally."
        elif self.severity == MemoryErrorSeverity.MEDIUM:
            return "Memory system is running in degraded mode. Some features may be unavailable."
        elif self.severity == MemoryErrorSeverity.HIGH:
            return "Memory system is experiencing significant issues. Limited functionality available."
        else:  # CRITICAL
            return "Memory system is currently unavailable. Operating without memory features."


# Configuration and Initialization Errors

class MemoryConfigurationError(MemorySystemError):
    """Raised when memory system configuration is invalid or missing."""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.CRITICAL,
            component="configuration",
            recoverable=False,
            recovery_suggestion="Check configuration settings and environment variables",
            **kwargs
        )
        self.config_key = config_key


class MemoryInitializationError(MemorySystemError):
    """Raised when memory system components fail to initialize."""
    
    def __init__(self, message: str, failed_component: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.HIGH,
            component="initialization",
            recoverable=True,
            recovery_suggestion="Restart the memory system or check component dependencies",
            **kwargs
        )
        self.failed_component = failed_component


# Database and Storage Errors

class MemoryDatabaseError(MemorySystemError):
    """Base class for database-related memory errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="database",
            recovery_suggestion="Check database connection and retry operation",
            **kwargs
        )


class MemoryConnectionError(MemoryDatabaseError):
    """Raised when database connection fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.HIGH,
            operation="connection",
            recovery_suggestion="Check database server status and connection parameters",
            error_code="MEM_DB_CONN_001",
            **kwargs
        )


class MemoryTransactionError(MemoryDatabaseError):
    """Raised when database transaction fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="transaction",
            recovery_suggestion="Retry the operation or check for conflicting transactions",
            error_code="MEM_DB_TXN_001",
            **kwargs
        )


class MemorySchemaError(MemoryDatabaseError):
    """Raised when database schema is invalid or missing."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.CRITICAL,
            operation="schema_validation",
            recoverable=False,
            recovery_suggestion="Run database migrations or check schema setup",
            error_code="MEM_DB_SCHEMA_001",
            **kwargs
        )


# STM (Short-Term Memory) Errors

class STMError(MemorySystemError):
    """Base class for Short-Term Memory errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="stm",
            **kwargs
        )


class STMStorageError(STMError):
    """Raised when STM message storage fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="message_storage",
            recovery_suggestion="Retry message storage or check database connection",
            error_code="MEM_STM_STORE_001",
            **kwargs
        )


class STMRetrievalError(STMError):
    """Raised when STM message retrieval fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.LOW,
            operation="message_retrieval",
            recovery_suggestion="Retry retrieval or use cached data if available",
            error_code="MEM_STM_RETR_001",
            **kwargs
        )


class STMSummarizationError(STMError):
    """Raised when STM summarization fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="summarization",
            recovery_suggestion="Use emergency summarization or skip summarization",
            error_code="MEM_STM_SUMM_001",
            **kwargs
        )


class STMTokenBudgetError(STMError):
    """Raised when STM token budget management fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="token_management",
            recovery_suggestion="Force message trimming or reset token counters",
            error_code="MEM_STM_TOKEN_001",
            **kwargs
        )


# LTM (Long-Term Memory) Errors

class LTMError(MemorySystemError):
    """Base class for Long-Term Memory errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="ltm",
            **kwargs
        )


class LTMStorageError(LTMError):
    """Raised when LTM memory storage fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="memory_storage",
            recovery_suggestion="Retry storage or check embedding generation",
            error_code="MEM_LTM_STORE_001",
            **kwargs
        )


class LTMRetrievalError(LTMError):
    """Raised when LTM memory retrieval fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.LOW,
            operation="memory_retrieval",
            recovery_suggestion="Retry retrieval or use text-based search fallback",
            error_code="MEM_LTM_RETR_001",
            **kwargs
        )


class LTMVectorSearchError(LTMError):
    """Raised when vector search operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="vector_search",
            recovery_suggestion="Use text-based search or check pgvector extension",
            error_code="MEM_LTM_VECTOR_001",
            **kwargs
        )


class LTMHybridSearchError(LTMError):
    """Raised when hybrid search operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="hybrid_search",
            recovery_suggestion="Fall back to simple vector search or text search",
            error_code="MEM_LTM_HYBRID_001",
            **kwargs
        )


# Embedding and AI Service Errors

class EmbeddingError(MemorySystemError):
    """Base class for embedding-related errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="embedding",
            **kwargs
        )


class EmbeddingConnectionError(EmbeddingError):
    """Raised when connection to embedding service fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.HIGH,
            operation="connection",
            recovery_suggestion="Check Ollama service status and network connectivity",
            error_code="MEM_EMB_CONN_001",
            **kwargs
        )


class EmbeddingTimeoutError(EmbeddingError):
    """Raised when embedding generation times out."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="generation",
            recovery_suggestion="Retry with shorter text or increase timeout",
            error_code="MEM_EMB_TIMEOUT_001",
            **kwargs
        )


class EmbeddingModelError(EmbeddingError):
    """Raised when embedding model is unavailable or fails."""
    
    def __init__(self, message: str, model_name: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.HIGH,
            operation="model_access",
            recovery_suggestion="Check model availability or switch to fallback model",
            error_code="MEM_EMB_MODEL_001",
            **kwargs
        )
        self.model_name = model_name


class EmbeddingGenerationError(EmbeddingError):
    """Raised when embedding generation fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=MemoryErrorSeverity.MEDIUM,
            operation="generation",
            recovery_suggestion="Retry with different text or skip embedding",
            error_code="MEM_EMB_GEN_001",
            **kwargs
        )


# Memory Extraction and Processing Errors

class MemoryExtractionError(MemorySystemError):
    """Raised when memory extraction from conversations fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="extraction",
            severity=MemoryErrorSeverity.LOW,
            recovery_suggestion="Skip extraction for this conversation or retry later",
            error_code="MEM_EXTRACT_001",
            **kwargs
        )


class MemoryImportanceError(MemorySystemError):
    """Raised when importance scoring fails."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="extraction",
            operation="importance_scoring",
            severity=MemoryErrorSeverity.LOW,
            recovery_suggestion="Use default importance score or skip memory",
            error_code="MEM_IMPORT_001",
            **kwargs
        )


# User Management and Privacy Errors

class MemoryPrivacyError(MemorySystemError):
    """Raised when privacy-related operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="privacy",
            severity=MemoryErrorSeverity.HIGH,
            recoverable=False,
            recovery_suggestion="Contact administrator for manual data handling",
            error_code="MEM_PRIVACY_001",
            **kwargs
        )


class MemoryExportError(MemorySystemError):
    """Raised when memory export operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="export",
            operation="data_export",
            severity=MemoryErrorSeverity.MEDIUM,
            recovery_suggestion="Retry export or check file system permissions",
            error_code="MEM_EXPORT_001",
            **kwargs
        )


class MemoryDeletionError(MemorySystemError):
    """Raised when memory deletion operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="deletion",
            operation="data_deletion",
            severity=MemoryErrorSeverity.HIGH,
            recovery_suggestion="Retry deletion or perform manual cleanup",
            error_code="MEM_DELETE_001",
            **kwargs
        )


# Resource and Performance Errors

class MemoryResourceError(MemorySystemError):
    """Raised when system resources are insufficient."""
    
    def __init__(self, message: str, resource_type: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            component="resources",
            severity=MemoryErrorSeverity.HIGH,
            recovery_suggestion="Free up resources or reduce memory system load",
            error_code="MEM_RESOURCE_001",
            **kwargs
        )
        self.resource_type = resource_type


class MemoryPerformanceError(MemorySystemError):
    """Raised when operations exceed performance thresholds."""
    
    def __init__(self, message: str, operation_time: Optional[float] = None, **kwargs):
        super().__init__(
            message,
            component="performance",
            severity=MemoryErrorSeverity.MEDIUM,
            recovery_suggestion="Optimize query or reduce data size",
            error_code="MEM_PERF_001",
            **kwargs
        )
        self.operation_time = operation_time


# Circuit Breaker and Degradation Errors

class MemoryCircuitBreakerError(MemorySystemError):
    """Raised when circuit breaker is open."""
    
    def __init__(self, message: str, circuit_name: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            component="circuit_breaker",
            severity=MemoryErrorSeverity.HIGH,
            recovery_suggestion="Wait for circuit breaker recovery or reset manually",
            error_code="MEM_CIRCUIT_001",
            **kwargs
        )
        self.circuit_name = circuit_name


class MemoryDegradationError(MemorySystemError):
    """Raised when system enters degraded mode."""
    
    def __init__(self, message: str, degradation_level: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            component="degradation",
            severity=MemoryErrorSeverity.MEDIUM,
            recovery_suggestion="Check component health and restore failed services",
            error_code="MEM_DEGRADE_001",
            **kwargs
        )
        self.degradation_level = degradation_level


# Validation and Data Integrity Errors

class MemoryValidationError(MemorySystemError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field_name: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            component="validation",
            severity=MemoryErrorSeverity.LOW,
            recovery_suggestion="Check input data format and constraints",
            error_code="MEM_VALID_001",
            **kwargs
        )
        self.field_name = field_name


class MemoryIntegrityError(MemorySystemError):
    """Raised when data integrity checks fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            component="integrity",
            severity=MemoryErrorSeverity.HIGH,
            recoverable=False,
            recovery_suggestion="Check data consistency and run integrity repairs",
            error_code="MEM_INTEGRITY_001",
            **kwargs
        )


# Utility functions for error handling

def classify_error_severity(error: Exception) -> MemoryErrorSeverity:
    """
    Classify the severity of an error based on its type and context.
    
    Args:
        error: Exception to classify
        
    Returns:
        MemoryErrorSeverity: Classified severity level
    """
    if isinstance(error, MemorySystemError):
        return error.severity
    
    # Classify standard exceptions
    error_name = error.__class__.__name__.lower()
    
    if any(keyword in error_name for keyword in ['connection', 'network', 'timeout']):
        return MemoryErrorSeverity.HIGH
    elif any(keyword in error_name for keyword in ['permission', 'access', 'auth']):
        return MemoryErrorSeverity.HIGH
    elif any(keyword in error_name for keyword in ['value', 'type', 'attribute']):
        return MemoryErrorSeverity.LOW
    elif any(keyword in error_name for keyword in ['memory', 'resource']):
        return MemoryErrorSeverity.HIGH
    else:
        return MemoryErrorSeverity.MEDIUM


def create_recovery_context(
    error: Exception,
    component: str,
    operation: str,
    attempt_count: int = 0,
    max_attempts: int = 3
) -> Dict[str, Any]:
    """
    Create context information for error recovery.
    
    Args:
        error: The original error
        component: Component where error occurred
        operation: Operation that failed
        attempt_count: Current attempt number
        max_attempts: Maximum retry attempts
        
    Returns:
        Dict containing recovery context
    """
    return {
        "error_type": error.__class__.__name__,
        "error_message": str(error),
        "component": component,
        "operation": operation,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "severity": classify_error_severity(error).value,
        "recoverable": attempt_count < max_attempts,
        "timestamp": __import__('time').time()
    }