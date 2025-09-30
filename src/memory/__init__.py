"""Memory system for SecondShiftAugie bot with comprehensive error handling."""

from .models import ThreadCtx, Msg, NewMemory, MemoryHit
from .config import MemoryConfig, MemoryConfigError
from .embedding_client import EmbeddingClient, EmbeddingError, OllamaConnectionError, EmbeddingTimeoutError
from .stm_store import STMStore, STMError
from .ltm_store import LTMStore, LTMError
from .summarizer import Summarizer, SummarizerError
from .memory_extractor import MemoryExtractor, MemoryExtractorError
from .memory_service import MemoryService, MemoryServiceError, MemoryMode

# Error handling and monitoring components
from .exceptions import (
    MemorySystemError, MemoryErrorSeverity, MemoryConfigurationError,
    MemoryInitializationError, MemoryDatabaseError, MemoryConnectionError,
    STMStorageError, STMRetrievalError, STMSummarizationError, STMTokenBudgetError,
    LTMStorageError, LTMRetrievalError, LTMVectorSearchError, LTMHybridSearchError,
    EmbeddingConnectionError, EmbeddingTimeoutError, EmbeddingModelError, EmbeddingGenerationError,
    MemoryExtractionError, MemoryImportanceError, MemoryPrivacyError,
    MemoryExportError, MemoryDeletionError, MemoryResourceError, MemoryPerformanceError,
    MemoryCircuitBreakerError, MemoryDegradationError, MemoryValidationError, MemoryIntegrityError
)
from .performance_monitor import (
    performance_monitor, PerformanceMonitor, monitor_performance, PerformanceTimer,
    MetricType, PerformanceMetric, OperationStats
)
from .health_checks import (
    health_checker, HealthChecker, HealthStatus, HealthCheckResult,
    check_database_health, check_embedding_service_health, check_memory_service_health
)
from .recovery_manager import (
    recovery_manager, RecoveryManager, RecoveryStrategy, DegradationLevel,
    RecoveryAction, RecoveryAttempt, register_default_recovery_actions
)
from .monitoring_endpoints import (
    monitoring_endpoints, MemoryMonitoringEndpoints, MonitoringLevel, MonitoringResponse,
    set_memory_service, get_health_embed_data, get_performance_summary_text
)
from .error_handling_setup import (
    initialize_error_handling_system, setup_memory_error_handling,
    setup_discord_error_notifications, setup_logging_for_error_handling,
    shutdown_error_handling_system
)

__all__ = [
    # Core memory system
    'ThreadCtx', 'Msg', 'NewMemory', 'MemoryHit', 
    'MemoryConfig', 'MemoryConfigError',
    'EmbeddingClient', 'EmbeddingError', 'OllamaConnectionError', 'EmbeddingTimeoutError',
    'STMStore', 'STMError',
    'LTMStore', 'LTMError',
    'Summarizer', 'SummarizerError',
    'MemoryExtractor', 'MemoryExtractorError',
    'MemoryService', 'MemoryServiceError', 'MemoryMode',
    
    # Exception classes
    'MemorySystemError', 'MemoryErrorSeverity', 'MemoryConfigurationError',
    'MemoryInitializationError', 'MemoryDatabaseError', 'MemoryConnectionError',
    'STMStorageError', 'STMRetrievalError', 'STMSummarizationError', 'STMTokenBudgetError',
    'LTMStorageError', 'LTMRetrievalError', 'LTMVectorSearchError', 'LTMHybridSearchError',
    'EmbeddingConnectionError', 'EmbeddingTimeoutError', 'EmbeddingModelError', 'EmbeddingGenerationError',
    'MemoryExtractionError', 'MemoryImportanceError', 'MemoryPrivacyError',
    'MemoryExportError', 'MemoryDeletionError', 'MemoryResourceError', 'MemoryPerformanceError',
    'MemoryCircuitBreakerError', 'MemoryDegradationError', 'MemoryValidationError', 'MemoryIntegrityError',
    
    # Performance monitoring
    'performance_monitor', 'PerformanceMonitor', 'monitor_performance', 'PerformanceTimer',
    'MetricType', 'PerformanceMetric', 'OperationStats',
    
    # Health checking
    'health_checker', 'HealthChecker', 'HealthStatus', 'HealthCheckResult',
    'check_database_health', 'check_embedding_service_health', 'check_memory_service_health',
    
    # Recovery management
    'recovery_manager', 'RecoveryManager', 'RecoveryStrategy', 'DegradationLevel',
    'RecoveryAction', 'RecoveryAttempt', 'register_default_recovery_actions',
    
    # Monitoring endpoints
    'monitoring_endpoints', 'MemoryMonitoringEndpoints', 'MonitoringLevel', 'MonitoringResponse',
    'set_memory_service', 'get_health_embed_data', 'get_performance_summary_text',
    
    # Setup and initialization
    'initialize_error_handling_system', 'setup_memory_error_handling',
    'setup_discord_error_notifications', 'setup_logging_for_error_handling',
    'shutdown_error_handling_system'
]