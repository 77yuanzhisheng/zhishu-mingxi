"""Management-domain exceptions mapped to HTTP status codes by the router."""


class ManagementError(RuntimeError):
    status_code = 400


class ResourceNotFoundError(ManagementError):
    status_code = 404


class PermissionDeniedError(ManagementError):
    status_code = 403


class ConflictError(ManagementError):
    status_code = 409
