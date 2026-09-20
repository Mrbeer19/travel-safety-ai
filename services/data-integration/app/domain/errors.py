"""Domain errors."""


class SnapshotConflictError(ValueError):
    """The same idempotency key was used for differing immutable content."""
