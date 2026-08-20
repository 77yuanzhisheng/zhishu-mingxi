"""FastAPI routes for account registration and authentication."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.models import AuthResponse, AuthUser, LoginRequest, RegisterRequest
from backend.auth.service import AuthError, get_user_from_token, login_user, register_user


router = APIRouter(prefix="/api/auth", tags=["认证"])
bearer_scheme = HTTPBearer(auto_error=False)


def _raise_http(exc: AuthError) -> None:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    raise HTTPException(status_code=exc.status_code, detail=str(exc), headers=headers) from exc


@router.post("/register", response_model=AuthResponse)
def register_endpoint(request: RegisterRequest) -> AuthResponse:
    try:
        return register_user(request.username, request.password, request.name, request.role)
    except AuthError as exc:
        _raise_http(exc)


@router.post("/login", response_model=AuthResponse)
def login_endpoint(request: LoginRequest) -> AuthResponse:
    try:
        return login_user(request.username, request.password)
    except AuthError as exc:
        _raise_http(exc)


@router.get("/me", response_model=AuthUser)
def me_endpoint(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="需要 Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return get_user_from_token(credentials.credentials)
    except AuthError as exc:
        _raise_http(exc)
