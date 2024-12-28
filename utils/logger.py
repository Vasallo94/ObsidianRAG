import logging
import os
import sys


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Handler para la consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # Path para el archivo de logs
        log_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_directory, exist_ok=True)
        log_file = os.path.join(log_directory, 'app.log')

        # Handler para el archivo de logs
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Agregar handlers al logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    return logger