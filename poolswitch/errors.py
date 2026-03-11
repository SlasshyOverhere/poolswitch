class PoolSwitchError(Exception):
    """Base exception for pool errors."""


class NoHealthyKeysError(PoolSwitchError):
    """Raised when there are no keys available for routing."""


class StorageError(PoolSwitchError):
    """Raised when the configured storage backend fails."""


