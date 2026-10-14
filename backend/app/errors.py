"""Domain errors. Each carries a user-safe message and the HTTP status it maps to."""

from typing import ClassVar

LOGIN_REQUIRED_MESSAGE = "Please log in to continue."


class AppError(Exception):
    status_code: ClassVar[int] = 500
    default_message: ClassVar[str] = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotAuthenticated(AppError):
    status_code = 401
    default_message = "Your session has expired. Please log in again."


class InvalidCredentials(AppError):
    status_code = 401
    default_message = "Invalid email or password."


class RateLimited(AppError):
    status_code = 429
    default_message = "Too many attempts. Please wait a moment and try again."


class InvalidInput(AppError):
    status_code = 400
    default_message = "Please check your details and try again."


class SlotTaken(AppError):
    status_code = 409
    default_message = "That time slot has just been booked. Please choose another."


class PatientDetailsRequired(AppError):
    status_code = 412
    default_message = "Please complete your patient details first."


class NotFound(AppError):
    status_code = 404
    default_message = "No upcoming appointment found."


class RegistrationFailed(AppError):
    status_code = 400
    default_message = (
        "Unable to create an account with those details. "
        "If you already have an account, please log in."
    )


class ServiceUnavailable(AppError):
    status_code = 503
    default_message = "The service is temporarily unavailable. Please try again shortly."
