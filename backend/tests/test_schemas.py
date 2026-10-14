from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import (
    AppointmentRequest,
    LoginRequest,
    PatientRequest,
    RegisterRequest,
    field_errors,
)

VALID_PATIENT = {
    "first_name": "  Pat ",
    "last_name": "Lee",
    "mobile": " +61 (400) 000-000 ",
    "email": "  Pat.Lee@Example.COM ",
}


def errors_for(model: Any, data: dict[str, Any]) -> dict[str, str]:
    with pytest.raises(ValidationError) as info:
        model.model_validate(data)
    return field_errors(info.value.errors())


def test_patient_is_stripped_and_email_lowercased() -> None:
    patient = PatientRequest.model_validate(VALID_PATIENT)
    assert patient.model_dump() == {
        "first_name": "Pat",
        "last_name": "Lee",
        "mobile": "+61 (400) 000-000",
        "email": "pat.lee@example.com",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("first_name", "   ", "First name is required."),
        ("last_name", "", "Last name is required."),
        ("first_name", "x" * 81, "First name must be 80 characters or fewer."),
        ("last_name", "Lee\x00", "Last name contains characters that are not allowed."),
        ("first_name", "Pat‮", "First name contains characters that are not allowed."),
        ("mobile", "", "Mobile number is required."),
        ("mobile", "12345", "Please enter a valid mobile number."),
        ("mobile", "+61 abc 000", "Please enter a valid mobile number."),
        ("mobile", "(((--)))  1", "Please enter a valid mobile number."),
        ("mobile", "1" * 21, "Please enter a valid mobile number."),
        ("email", " ", "Email is required."),
        ("email", "not-an-email", "Please enter a valid email address."),
        ("email", "a b@example.com", "Please enter a valid email address."),
        ("email", "pat@exa_mple..com", "Please enter a valid email address."),
        ("email", "a@" + "b" * 250 + ".com", "Email must be 254 characters or fewer."),
        ("first_name", 42, "Please enter a valid first name."),
    ],
)
def test_patient_field_errors(field: str, value: Any, message: str) -> None:
    assert errors_for(PatientRequest, {**VALID_PATIENT, field: value}) == {field: message}


def test_patient_names_allow_unicode_and_punctuation() -> None:
    data = {**VALID_PATIENT, "first_name": "Zoë-Ánne", "last_name": "O'Brien de Silva"}
    assert PatientRequest.model_validate(data).first_name == "Zoë-Ánne"


def test_missing_fields_use_required_messages() -> None:
    assert errors_for(PatientRequest, {}) == {
        "first_name": "First name is required.",
        "last_name": "Last name is required.",
        "mobile": "Mobile number is required.",
        "email": "Email is required.",
    }


def test_register_password_rules() -> None:
    ok = RegisterRequest.model_validate({"email": "a@example.com", "password": " spaced pw "})
    assert ok.password == " spaced pw "  # passwords are never stripped
    base = {"email": "a@example.com"}
    assert errors_for(RegisterRequest, {**base, "password": ""}) == {
        "password": "Password is required."
    }
    assert errors_for(RegisterRequest, {**base, "password": "short"}) == {
        "password": "Password must be at least 8 characters."
    }
    assert errors_for(RegisterRequest, {**base, "password": "x" * 73}) == {
        "password": "Password must be 72 characters or fewer."
    }
    # 72 characters but more than 72 bytes (bcrypt limit)
    assert errors_for(RegisterRequest, {**base, "password": "é" * 40}) == {
        "password": "Password must be 72 characters or fewer."
    }


def test_login_password_rules() -> None:
    assert LoginRequest.model_validate({"email": "a@example.com", "password": "x"}).password == "x"
    assert errors_for(LoginRequest, {"email": "a@example.com", "password": ""}) == {
        "password": "Password is required."
    }
    assert errors_for(LoginRequest, {"email": "a@example.com", "password": "x" * 100}) == {
        "password": "Password must be 72 characters or fewer."
    }


def test_appointment_request_valid() -> None:
    body = AppointmentRequest.model_validate(
        {"doctor_id": " dr-perera ", "date": "2026-10-15", "time": "10:00"}
    )
    assert (body.doctor_id, body.date, body.time) == ("dr-perera", date(2026, 10, 15), "10:00")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("doctor_id", "", "Please choose a doctor."),
        ("doctor_id", "Dr Perera", "Please choose a valid doctor."),
        ("doctor_id", "x" * 41, "Please choose a valid doctor."),
        ("date", "15/10/2026", "Please choose a valid date."),
        ("date", "2026-02-30", "Please choose a valid date."),
        ("date", "20261015", "Please choose a valid date."),
        ("date", 1760000000, "Please choose a valid date."),
        ("time", "", "Please choose a time slot."),
        ("time", "10:00:00", "Please choose a valid time slot."),
        ("time", "25:00", "Please choose a valid time slot."),
        ("time", "9:00", "Please choose a valid time slot."),
    ],
)
def test_appointment_field_errors(field: str, value: Any, message: str) -> None:
    data = {"doctor_id": "dr-perera", "date": "2026-10-15", "time": "10:00", field: value}
    assert errors_for(AppointmentRequest, data) == {field: message}


def test_appointment_missing_fields() -> None:
    assert errors_for(AppointmentRequest, {}) == {
        "doctor_id": "Please choose a doctor.",
        "date": "Please choose a date.",
        "time": "Please choose a time slot.",
    }


def test_field_errors_shapes_without_echoing_input() -> None:
    errors = [
        {"type": "json_invalid", "loc": ("body", 3), "msg": "JSON decode error", "input": {}},
        {"type": "missing", "loc": ("body", "email"), "msg": "x", "input": "secret"},
        {"type": "string_type", "loc": ("body", "email"), "msg": "second error ignored"},
        {"type": "model_attributes_type", "loc": ("query",), "msg": "x"},
        {"type": "string_type", "loc": ("body", "nickname"), "msg": "x"},
        {"type": "missing", "loc": ("query", "page"), "msg": "x"},
    ]
    assert field_errors(errors) == {
        "body": "The request body must be valid JSON.",
        "email": "Email is required.",
        "nickname": "Please enter a valid value.",
        "page": "This field is required.",
    }
