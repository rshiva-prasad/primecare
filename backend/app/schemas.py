"""Request/response models. Validation mirrors the A2 client rules; inputs are stripped."""

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import date, time
from typing import Annotated, Any, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, BeforeValidator, WithJsonSchema

VALIDATION_DETAIL = "Please correct the highlighted fields."

REQUIRED_MESSAGES = {
    "first_name": "First name is required.",
    "last_name": "Last name is required.",
    "mobile": "Mobile number is required.",
    "email": "Email is required.",
    "password": "Password is required.",
    "doctor_id": "Please choose a doctor.",
    "date": "Please choose a date.",
    "time": "Please choose a time slot.",
    "body": "A JSON request body is required.",
}
INVALID_MESSAGES = {
    "first_name": "Please enter a valid first name.",
    "last_name": "Please enter a valid last name.",
    "mobile": "Please enter a valid mobile number.",
    "email": "Please enter a valid email address.",
    "password": "Please enter a valid password.",
    "doctor_id": "Please choose a valid doctor.",
    "date": "Please choose a valid date.",
    "time": "Please choose a valid time slot.",
    "body": "The request body must be a JSON object.",
}

NAME_MAX = 80
EMAIL_MAX = 254
PASSWORD_MIN = 8
PASSWORD_MAX = 72  # bcrypt limit used by Supabase Auth

_A2_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MOBILE = re.compile(r"^\+?[0-9 ()-]{7,20}$")
_DOCTOR_ID = re.compile(r"^[a-z0-9-]{1,40}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HH_MM = re.compile(r"^\d{2}:\d{2}$")
_REQUEST_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})
_BIDI_CONTROLS = frozenset("‪‫‬‭‮⁦⁧⁨⁩")


def _has_control_chars(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" or ch in _BIDI_CONTROLS for ch in value)


def _name_validator(field: str) -> Callable[[str], str]:
    label = REQUIRED_MESSAGES[field].removesuffix(" is required.")

    def validate(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(REQUIRED_MESSAGES[field])
        if len(value) > NAME_MAX:
            raise ValueError(f"{label} must be {NAME_MAX} characters or fewer.")
        if _has_control_chars(value):
            raise ValueError(f"{label} contains characters that are not allowed.")
        return value

    return validate


def clean_mobile(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(REQUIRED_MESSAGES["mobile"])
    if not _MOBILE.fullmatch(value) or sum(ch.isdigit() for ch in value) < 7:
        raise ValueError(INVALID_MESSAGES["mobile"])
    return value


def clean_email(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(REQUIRED_MESSAGES["email"])
    if len(value) > EMAIL_MAX:
        raise ValueError(f"Email must be {EMAIL_MAX} characters or fewer.")
    if not _A2_EMAIL.fullmatch(value):
        raise ValueError(INVALID_MESSAGES["email"])
    try:
        normalized = validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        raise ValueError(INVALID_MESSAGES["email"]) from None
    return normalized.lower()


def _password_too_long(value: str) -> bool:
    return len(value) > PASSWORD_MAX or len(value.encode("utf-8")) > PASSWORD_MAX


def check_new_password(value: str) -> str:
    if not value:
        raise ValueError(REQUIRED_MESSAGES["password"])
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
    if _password_too_long(value):
        raise ValueError(f"Password must be {PASSWORD_MAX} characters or fewer.")
    return value


def check_login_password(value: str) -> str:
    if not value:
        raise ValueError(REQUIRED_MESSAGES["password"])
    if _password_too_long(value):
        raise ValueError(f"Password must be {PASSWORD_MAX} characters or fewer.")
    return value


def clean_doctor_id(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(REQUIRED_MESSAGES["doctor_id"])
    if not _DOCTOR_ID.fullmatch(value):
        raise ValueError(INVALID_MESSAGES["doctor_id"])
    return value


def parse_iso_date(value: Any) -> Any:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value.strip()):
        raise ValueError(INVALID_MESSAGES["date"])
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(INVALID_MESSAGES["date"]) from None


def clean_slot_time(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(REQUIRED_MESSAGES["time"])
    if not _HH_MM.fullmatch(value):
        raise ValueError(INVALID_MESSAGES["time"])
    try:
        time.fromisoformat(value)
    except ValueError:
        raise ValueError(INVALID_MESSAGES["time"]) from None
    return value


FirstName = Annotated[str, AfterValidator(_name_validator("first_name"))]
LastName = Annotated[str, AfterValidator(_name_validator("last_name"))]
Mobile = Annotated[str, AfterValidator(clean_mobile)]
Email = Annotated[
    str,
    AfterValidator(clean_email),
    WithJsonSchema({"type": "string", "format": "email", "maxLength": EMAIL_MAX}),
]
NewPassword = Annotated[str, AfterValidator(check_new_password)]
LoginPassword = Annotated[str, AfterValidator(check_login_password)]
DoctorId = Annotated[str, AfterValidator(clean_doctor_id)]
IsoDate = Annotated[
    date,
    BeforeValidator(parse_iso_date),
    WithJsonSchema({"type": "string", "format": "date"}),
]
SlotTime = Annotated[
    str,
    AfterValidator(clean_slot_time),
    WithJsonSchema({"type": "string", "pattern": _HH_MM.pattern}),
]


def _field_name(loc: Iterable[Any]) -> str:
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOCATIONS:
        parts = parts[1:]
    names = [part for part in parts if isinstance(part, str)]
    return names[-1] if names else "body"


def _field_message(field: str, error: Mapping[str, Any]) -> str:
    kind = error.get("type")
    ctx_error = (error.get("ctx") or {}).get("error")
    if kind == "value_error" and ctx_error is not None:
        return str(ctx_error)
    if kind == "missing":
        return REQUIRED_MESSAGES.get(field, "This field is required.")
    if kind == "json_invalid":
        return "The request body must be valid JSON."
    return INVALID_MESSAGES.get(field, "Please enter a valid value.")


def field_errors(errors: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """First user-safe message per field. Never echoes the submitted input."""
    fields: dict[str, str] = {}
    for error in errors:
        field = _field_name(error.get("loc", ()))
        fields.setdefault(field, _field_message(field, error))
    return fields


# Requests


class LoginRequest(BaseModel):
    email: Email
    password: LoginPassword


class RegisterRequest(BaseModel):
    email: Email
    password: NewPassword


class PatientRequest(BaseModel):
    first_name: FirstName
    last_name: LastName
    mobile: Mobile
    email: Email


class AppointmentRequest(BaseModel):
    doctor_id: DoctorId
    date: IsoDate
    time: SlotTime


# Responses


class ErrorBody(BaseModel):
    detail: str
    fields: dict[str, str] | None = None


class HealthStatus(BaseModel):
    status: Literal["ok"]
    supabase_configured: bool


class UserOut(BaseModel):
    id: str
    email: str


class UserEnvelope(BaseModel):
    user: UserOut


class RegisterResult(BaseModel):
    user: UserOut | None
    session_started: bool
    detail: str | None = None


class PatientOut(BaseModel):
    first_name: str
    last_name: str
    mobile: str
    email: str


class PatientEnvelope(BaseModel):
    patient: PatientOut | None


class DoctorOut(BaseModel):
    id: str
    name: str
    specialty: str


class DoctorsEnvelope(BaseModel):
    doctors: list[DoctorOut]
    today: str
    max_date: str


class SlotOut(BaseModel):
    time: str
    label: str


class SlotsEnvelope(BaseModel):
    date: str
    slots: list[SlotOut]


class AppointmentOut(BaseModel):
    id: str
    token: str
    doctor: DoctorOut
    date: str
    date_label: str
    time: str
    time_label: str
    status: str
    status_label: str
    created_at: str


class AppointmentEnvelope(BaseModel):
    appointment: AppointmentOut


class QueueOut(BaseModel):
    token: str
    position: int | None
    ahead: int
    total_in_queue: int
    estimated_wait_minutes: int
    now_serving: str | None
    serving_label: str
    is_today: bool
    progress_percent: int
    status: str
    status_label: str
    appointment: AppointmentOut


class QueueEnvelope(BaseModel):
    queue: QueueOut
