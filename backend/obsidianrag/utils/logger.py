"""Logging utilities for ObsidianRAG"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str, level: int = logging.INFO, log_dir: Optional[str] = None
) -> logging.Logger:
    """Set up a logger with console and file handlers.

    Args:
        name: Logger name (usually __name__)
        level: Logging level
        log_dir: Optional directory for log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # File handler (if log_dir provided)
        if log_dir:
            log_directory = Path(log_dir)
            log_directory.mkdir(parents=True, exist_ok=True)
            log_file = log_directory / "obsidianrag.log"

            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)

            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        # Console formatter WITH TIMESTAMP
        console_formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s - %(message)s", datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger by name.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
