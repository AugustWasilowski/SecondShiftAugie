import logging
import logging.handlers
import os


class CustomFormatter(logging.Formatter):
    LEVEL_COLORS = [
        (logging.DEBUG, '\x1b[40;1m'),
        (logging.INFO, '\x1b[34;1m'),
        (logging.WARNING, '\x1b[33;1m'),
        (logging.ERROR, '\x1b[31m'),
        (logging.CRITICAL, '\x1b[41m'),
    ]
    FORMATS = {
        level: logging.Formatter(
            f'\x1b[30;1m%(asctime)s\x1b[0m {color}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m -> %(message)s',
            '%Y-%m-%d %H:%M:%S'
        )
        for level, color in LEVEL_COLORS
    }


    def format(self, record):
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]

        # Override the traceback to always print in red
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f'\x1b[31m{text}\x1b[0m'

        output = formatter.format(record)
        # Remove the cache layer
        record.exc_text = None
        return output


def setup_logger(module_name:str) -> logging.Logger:
    # create logger
    library, _, _ = module_name.partition('.py')
    logger = logging.getLogger(library)
    logger.setLevel(logging.INFO)

    log_level = "INFO"
    level = logging.getLevelName(log_level.upper())

    # create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(CustomFormatter())
    # Add console handler to logger
    logger.addHandler(console_handler)

    if os.getenv("LOGGING") == "True":  # Check if logging is enabled
        # specify that the log file path is the same as `main.py` file path
        grandparent_dir = os.path.abspath(f"{__file__}/../../")
        log_name = 'second_shift_augie.log'
        log_path = os.path.join(grandparent_dir, log_name)
        # create local log handler
        log_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            encoding='utf-8',
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=2,  # Rotate through 5 files
        )
        log_handler.setFormatter(CustomFormatter())
        log_handler.setLevel(level)
        logger.addHandler(log_handler)

    return logger
