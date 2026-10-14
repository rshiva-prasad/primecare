"""FastAPI dependencies: settings, gateway and the cookie-backed current user."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.errors import LOGIN_REQUIRED_MESSAGE, NotAuthenticated
from app.gateway import Gateway
from app.throttle import AuthThrottle

# request.state key read by the security middleware, which writes the rotated session cookies
# onto whatever response is finally sent (including error responses).
REFRESHED_SESSION_STATE = "pc_refreshed_session"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    access_token: str


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway = request.app.state.gateway
    return gateway


def get_auth_throttle(request: Request) -> AuthThrottle:
    throttle: AuthThrottle = request.app.state.auth_throttle
    return throttle


def get_current_user(
    request: Request, gateway: Annotated[Gateway, Depends(get_gateway)]
) -> CurrentUser:
    access_token = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not access_token and not refresh_token:
        raise NotAuthenticated(LOGIN_REQUIRED_MESSAGE)

    if access_token:
        user = gateway.get_user(access_token)
        if user is not None:
            return CurrentUser(id=user.id, email=user.email, access_token=access_token)

    # The access cookie expires with the JWT, so a missing or rejected access token with a
    # refresh token present means "refresh", not "logged out".
    if refresh_token:
        session = gateway.refresh(refresh_token)
        if session is not None and session.access_token and session.refresh_token:
            setattr(request.state, REFRESHED_SESSION_STATE, session)
            return CurrentUser(
                id=session.user_id, email=session.email, access_token=session.access_token
            )

    raise NotAuthenticated()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
GatewayDep = Annotated[Gateway, Depends(get_gateway)]
AuthThrottleDep = Annotated[AuthThrottle, Depends(get_auth_throttle)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
