import logging
from typing import Any


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_external_service_error(logger: logging.Logger, service: str, exc: Exception) -> None:
    logger.warning("External service unavailable", extra={"service": service, "error": str(exc)})


def logging_extra(**values: Any) -> dict[str, Any]:
    return values

