class PixelVaultError(Exception):
    """Base exception for all application errors."""


# ─── Domain errors ────────────────────────────────────────────────────────────


class DomainError(PixelVaultError):
    """Base for domain-layer errors."""


class QuotaExceededError(DomainError):
    """User has exceeded their storage quota."""


class InvalidStateError(DomainError):
    """Entity is in a state that does not allow the requested operation."""


class AuthorizationError(DomainError):
    """Caller is not permitted to perform this operation."""


# ─── Application errors ───────────────────────────────────────────────────────


class ApplicationError(PixelVaultError):
    """Base for service-layer errors."""


class ResourceNotFoundError(ApplicationError):
    """Requested resource does not exist."""


class ConflictError(ApplicationError):
    """Operation conflicts with existing state (e.g. duplicate email)."""


class InvalidCredentialsError(ApplicationError):
    """Supplied credentials are incorrect."""


class AccountNotActiveError(ApplicationError):
    """Account exists but is not in active state (pending or suspended)."""


# ─── Infrastructure errors ────────────────────────────────────────────────────


class InfrastructureError(PixelVaultError):
    """Base for infrastructure-layer errors."""


class StorageError(InfrastructureError):
    """File storage operation failed."""


class DatabaseError(InfrastructureError):
    """Database operation failed."""
