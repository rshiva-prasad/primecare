import ipaddress
import logging

from fastapi import APIRouter, Request, Response, status

from app.config import Settings
from app.cookies import ACCESS_COOKIE, REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from app.deps import AuthThrottleDep, CurrentUserDep, GatewayDep, SettingsDep
from app.errors import AppError, InvalidCredentials, ServiceUnavailable
from app.gateway import AuthResult
from app.schemas import (
    ErrorBody,
    LoginRequest,
    RegisterRequest,
    RegisterResult,
    UserEnvelope,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

CONFIRM_EMAIL_DETAIL = "Check your email to confirm your account, then log in."


def _client_ip(request: Request, settings: Settings) -> str:
    """The client IP the throttle counts against.

    By default the socket peer. The dev script runs uvicorn with --no-proxy-headers, so a
    client-sent X-Forwarded-For cannot change it (locally every request arrives from the Vite proxy
    on 127.0.0.1, so the per-IP cap acts as one cap for the whole local app).

    Behind a proxy every request shares the proxy's peer address, so TRUSTED_CLIENT_IP_HEADER can
    name a header that proxy overwrites with the client's IP (on Vercel, x-vercel-forwarded-for).
    Its first value is used if it is an IP address; otherwise the socket peer is.
    """
    peer = request.client.host if request.client else "unknown"
    header = settings.trusted_client_ip_header
    value = request.headers.get(header) if header else None
    if value is None:
        return peer
    try:
        # Canonical form, so one address always maps to one throttle key.
        return str(ipaddress.ip_address(value.split(",", 1)[0].strip()))
    except ValueError:
        return peer


def _start_session(response: Response, result: AuthResult, *, secure: bool) -> None:
    if not result.access_token or not result.refresh_token:
        raise ServiceUnavailable()
    set_session_cookies(
        response,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
        secure=secure,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResult,
    response_model_exclude_unset=True,
    responses={
        202: {"model": RegisterResult, "description": "Email confirmation required"},
        400: {"model": ErrorBody},
        429: {"model": ErrorBody},
    },
)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    gateway: GatewayDep,
    settings: SettingsDep,
    throttle: AuthThrottleDep,
) -> RegisterResult:
    throttle.check_register(_client_ip(request, settings))
    result = gateway.sign_up(body.email, body.password)
    if result.access_token and result.refresh_token:
        _start_session(response, result, secure=settings.cookie_secure)
        return RegisterResult(
            user=UserOut(id=result.user_id, email=result.email), session_started=True
        )
    response.status_code = status.HTTP_202_ACCEPTED
    return RegisterResult(user=None, session_started=False, detail=CONFIRM_EMAIL_DETAIL)


@router.post(
    "/login",
    response_model=UserEnvelope,
    responses={401: {"model": ErrorBody}, 429: {"model": ErrorBody}},
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    gateway: GatewayDep,
    settings: SettingsDep,
    throttle: AuthThrottleDep,
) -> UserEnvelope:
    client_ip = _client_ip(request, settings)
    throttle.check_login(client_ip, body.email)
    try:
        result = gateway.sign_in(body.email, body.password)
    except InvalidCredentials:
        throttle.login_failed(client_ip, body.email)
        raise
    throttle.login_succeeded(client_ip, body.email)
    _start_session(response, result, secure=settings.cookie_secure)
    return UserEnvelope(user=UserOut(id=result.user_id, email=result.email))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(request: Request, gateway: GatewayDep, settings: SettingsDep) -> Response:
    access_token = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    try:
        revoked = gateway.sign_out(access_token) if access_token else False
        if not revoked and refresh_token:
            # The access token is missing or was rejected (usually expired): refresh once so the
            # session is still revoked server-side.
            refreshed = gateway.refresh(refresh_token)
            if refreshed is not None and refreshed.access_token:
                gateway.sign_out(refreshed.access_token)
    except AppError as exc:
        logger.info("Server-side sign-out skipped (%s)", type(exc).__name__)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, secure=settings.cookie_secure)
    return response


@router.get("/me", response_model=UserEnvelope, responses={401: {"model": ErrorBody}})
def me(user: CurrentUserDep) -> UserEnvelope:
    return UserEnvelope(user=UserOut(id=user.id, email=user.email))
