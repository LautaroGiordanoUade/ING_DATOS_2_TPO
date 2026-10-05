class DomainError(Exception):
    """Base domain invariant error."""


class SelfFollowError(DomainError):
    """A user cannot follow itself."""

