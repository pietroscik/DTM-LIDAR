import logging
import sys
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - loguru è opzionale
    from loguru import logger as _loguru_logger  # type: ignore
except Exception:  # pragma: no cover
    _loguru_logger = None


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configura il logging dell'applicazione.

    Se loguru è disponibile, usa loguru con output colorato su console
    ed eventualmente su file. In caso contrario, ricade sul logging
    standard di Python.
    """
    level = log_level.upper()

    if _loguru_logger is not None:
        # Rimuovi handler esistenti
        _loguru_logger.remove()

        # Console
        _loguru_logger.add(
            sys.stderr,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            level=level,
            colorize=True,
        )

        # File opzionale
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _loguru_logger.add(
                log_path,
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                    "{name}:{function}:{line} - {message}"
                ),
                level=level,
                rotation="10 MB",
                retention="7 days",
            )
    else:
        # Fallback: logging standard
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        )


def get_logger(name: Optional[str] = None):
    """
    Ritorna un logger configurato.

    Se loguru è disponibile, ritorna il logger loguru globale, altrimenti
    un logger standard di Python.
    """
    if _loguru_logger is not None:
        return _loguru_logger
    return logging.getLogger(name or __name__)

