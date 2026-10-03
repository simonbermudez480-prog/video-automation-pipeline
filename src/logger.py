"""
Módulo de logging centralizado para el pipeline multimedia.
Configura loguru con formato profesional en consola y archivo rotativo.
"""
import sys
from pathlib import Path
from loguru import logger

# Remover manejadores por defecto
logger.remove()

# Formato personalizado con marcas de tiempo claras y contexto
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} - "
    "{message}"
)

# Salida en consola
logger.add(
    sys.stderr,
    format=CONSOLE_FORMAT,
    level="INFO",
    colorize=True,
    backtrace=True,
    diagnose=True,
)

# Salida en archivo persistente
log_dir = Path("logs")
log_dir.mkdir(parents=True, exist_ok=True)
logger.add(
    log_dir / "pipeline.log",
    format=FILE_FORMAT,
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
)

__all__ = ["logger"]
