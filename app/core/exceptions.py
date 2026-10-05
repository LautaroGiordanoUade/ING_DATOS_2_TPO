class ApplicationError(Exception):
    """Base class for expected application errors."""


class FeatureNotImplementedError(ApplicationError):
    def __init__(self, feature: str) -> None:
        self.feature = feature
        super().__init__(f"La funcionalidad '{feature}' está pendiente como TODO(TP).")


class ResourceNotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class InvalidOperationError(ApplicationError):
    pass

