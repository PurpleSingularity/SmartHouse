import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: str = "logs") -> None:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        filename=log_path / "boobiki.log",
        when="midnight",
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    boobiki_logger = logging.getLogger("boobiki")
    boobiki_logger.setLevel(logging.INFO)
    boobiki_logger.addHandler(file_handler)

    for uvicorn_name in ("uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_name)
        uv_logger.addHandler(file_handler)
