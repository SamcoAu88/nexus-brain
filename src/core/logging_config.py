"""
Structured Logging Configuration
"""

import logging
import logging.config
from pythonjsonlogger import jsonlogger



def setup_logging():
    """Setup structured logging with JSON output"""
    
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": jsonlogger.JsonFormatter,
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
            "verbose": {
                "format": "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "verbose",
                "stream": "ext://sys.stdout",
            },
            "json_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": "logs/nexus.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 10,
            },
        },
        "loggers": {
            "": {  # root logger
                "level": "INFO",
                "handlers": ["console", "json_file"],
            },
            "uvicorn.access": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }
    
    logging.config.dictConfig(logging_config)
    
    # Create logs directory if needed
    import os
    os.makedirs("logs", exist_ok=True)
