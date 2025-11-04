"""Structured logging system for MAMMON.

This module provides JSON-formatted structured logging with context
injection for better observability and debugging.
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Formats log records as JSON with timestamps and context.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages.

    Allows injecting common context (e.g., user_id, transaction_id)
    into all log messages.
    """

    def process(
        self,
        msg: str,
        kwargs: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """Process log message and kwargs.

        Args:
            msg: Log message
            kwargs: Keyword arguments

        Returns:
            Tuple of (message, kwargs) with context added
        """
        # Merge context into extra
        extra = kwargs.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}

        # Add context to extra
        extra_fields = {**self.extra, **extra}
        kwargs["extra"] = {"extra_fields": extra_fields}

        return msg, kwargs


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = True,
) -> logging.Logger:
    """Set up structured logging for MAMMON.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for file logging
        json_format: Use JSON formatting if True

    Returns:
        Configured root logger
    """
    # Get root logger
    logger = logging.getLogger("mammon")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Create formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(
    name: str,
    context: Optional[Dict[str, Any]] = None,
) -> ContextLogger:
    """Get a logger with optional context.

    Args:
        name: Logger name (usually __name__)
        context: Optional context dict to inject into all logs

    Returns:
        Logger instance with context
    """
    logger = logging.getLogger(f"mammon.{name}")
    if context:
        return ContextLogger(logger, context)
    return ContextLogger(logger, {})


# Convenience functions
def log_transaction(
    logger: logging.Logger,
    tx_hash: str,
    operation: str,
    amount: str,
    status: str,
    **kwargs: Any,
) -> None:
    """Log a transaction event with structured data.

    Args:
        logger: Logger instance
        tx_hash: Transaction hash
        operation: Operation type
        amount: Transaction amount
        status: Transaction status
        **kwargs: Additional context
    """
    logger.info(
        f"Transaction {status}: {operation}",
        extra={
            "extra_fields": {
                "tx_hash": tx_hash,
                "operation": operation,
                "amount": amount,
                "status": status,
                **kwargs,
            }
        },
    )


def log_decision(
    logger: logging.Logger,
    decision_type: str,
    rationale: str,
    **kwargs: Any,
) -> None:
    """Log an agent decision with structured data.

    Args:
        logger: Logger instance
        decision_type: Type of decision
        rationale: Decision rationale
        **kwargs: Additional context
    """
    logger.info(
        f"Decision: {decision_type}",
        extra={
            "extra_fields": {
                "decision_type": decision_type,
                "rationale": rationale,
                **kwargs,
            }
        },
    )


def log_error(
    logger: logging.Logger,
    error_message: str,
    error_type: str,
    **kwargs: Any,
) -> None:
    """Log an error with structured data.

    Args:
        logger: Logger instance
        error_message: Error message
        error_type: Error type/category
        **kwargs: Additional context
    """
    logger.error(
        error_message,
        extra={
            "extra_fields": {
                "error_type": error_type,
                **kwargs,
            }
        },
    )
