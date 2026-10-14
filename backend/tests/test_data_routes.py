import datetime as dt
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.errors import InvalidInput, NotFound, ServiceUnavailable, SlotTaken
from tests.fakes import ALREADY_BOOKED, TODAY, FakeGateway

PATIENT = {
    "first_name": "Pat",
    "last_name": "Lee",
    "mobile": "+61 400 000 000",
    "email": "Pat@Example.com",
}
TOMORROW = (TODAY + dt.timedelta(days=1)).isoformat()

Login = Callable[..., Any]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/patients/me"),
        ("PUT", "/api/patients/me"),
        ("GET", "/api/doctors"),
        ("GET", f"/api/doctors/dr-perera/slots?date={TOMORROW}"),
        ("POST", "/api/appointments"),
        ("GET", "/api/appointments/current"),
        ("GET", "/api/appointments/current/queue"),
    ],
)
def test_protected_endpoints_require_login(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, json={})
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to continue."}


# patients


def test_get_patient_none_then_saved(client: TestClient, login: Login) -> None:
    login(with_patient=False)
    assert client.get("/api/patients/me").json() == {"patient": None}

    saved = client.put("/api/patients/me", json=PATIENT)
    assert saved.status_code == 200
    expected = {**PATIENT, "email": "pat@example.com"}
    assert saved.json() == {"patient": expected}
    assert client.get("/api/patients/me").json() == {"patient": expected}


def test_put_patient_uses_current_user_id(
    client: TestClient, fake: FakeGateway, login: Login
) -> None:
    session = login(with_patient=False)
    client.put("/api/patients/me", json={**PATIENT, "id": "someone-else"})
    ((token, user_id, data),) = fake.called("upsert_patient")
    assert (token, user_id) == (session.access_token, session.user_id)
    assert "id" not in data


def test_put_patient_validation(client: TestClient, login: Login) -> None:
    login()
    response = client.put("/api/patients/me", json={**PATIENT, "mobile": "123", "first_name": " "})
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Please correct the highlighted fields.",
        "fields": {
            "first_name": "First name is required.",
            "mobile": "Please enter a valid mobile number.",
        },
    }


# doctors and slots


def test_list_doctors_ordered_by_name(client: TestClient, login: Login) -> None:
    login()
    response = client.get("/api/doctors")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"doctors", "today", "max_date"}
    assert (body["today"], body["max_date"]) == ("2026-10-13", "2027-01-11")  # today + 90 days
    doctors = body["doctors"]
    assert [d["name"] for d in doctors] == sorted(d["name"] for d in doctors)
    assert doctors[0] == {
        "id": "dr-sharma",
        "name": "Dr. Anita Sharma",
        "specialty": "Dermatologist",
    }
    assert set(doctors[0]) == {"id", "name", "specialty"}


def test_doctors_today_is_the_clinic_date_from_the_gateway(
    client: TestClient, fake: FakeGateway, login: Login
) -> None:
    session = login()
    fake.today = dt.date(2026, 12, 31)  # e.g. already the next day in Sydney
    body = client.get("/api/doctors").json()
    assert (body["today"], body["max_date"]) == ("2026-12-31", "2027-03-31")
    assert fake.called("clinic_today") == [(session.access_token,)]


def test_doctors_unavailable_when_clinic_date_fails(
    client: TestClient, fake: FakeGateway, login: Login
) -> None:
    login()
    fake.failures["clinic_today"] = ServiceUnavailable()
    response = client.get("/api/doctors")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "The service is temporarily unavailable. Please try again shortly."
    }


def test_slots_for_date(client: TestClient, fake: FakeGateway, login: Login) -> None:
    session = login()
    response = client.get(f"/api/doctors/dr-perera/slots?date={TOMORROW}")
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == TOMORROW
    assert body["slots"][0] == {"time": "09:00", "label": "09:00 AM"}
    assert {"time": "14:00", "label": "02:00 PM"} in body["slots"]
    assert fake.called("available_slots") == [
        (session.access_token, "dr-perera", TODAY + dt.timedelta(days=1))
    ]


def test_slots_empty_for_past_date(client: TestClient, login: Login) -> None:
    login()
    response = client.get("/api/doctors/dr-perera/slots?date=2020-01-01")
    assert response.json() == {"date": "2020-01-01", "slots": []}


@pytest.mark.parametrize(
    ("path", "fields"),
    [
        ("/api/doctors/dr-perera/slots?date=15-10-2026", {"date": "Please choose a valid date."}),
        ("/api/doctors/dr-perera/slots?date=2026-13-01", {"date": "Please choose a valid date."}),
        ("/api/doctors/dr-perera/slots", {"date": "Please choose a date."}),
        (
            f"/api/doctors/DR_X/slots?date={TOMORROW}",
            {"doctor_id": "Please choose a valid doctor."},
        ),
    ],
)
def test_slots_validation(
    client: TestClient, login: Login, path: str, fields: dict[str, str]
) -> None:
    login()
    response = client.get(path)
    assert response.status_code == 422
    assert response.json() == {"detail": "Please correct the highlighted fields.", "fields": fields}


# appointments


def book(client: TestClient, time: str = "10:00", date: str = TOMORROW) -> Any:
    return client.post(
        "/api/appointments", json={"doctor_id": "dr-perera", "date": date, "time": time}
    )


def test_book_appointment(client: TestClient, login: Login) -> None:
    login()
    response = book(client)
    assert response.status_code == 201
    appointment = response.json()["appointment"]
    assert appointment == {
        "id": appointment["id"],
        "token": "PC-001",
        "doctor": {
            "id": "dr-perera",
            "name": "Dr. Sarah Perera",
            "specialty": "General Practitioner",
        },
        "date": TOMORROW,
        "date_label": "14 October 2026",
        "time": "10:00",
        "time_label": "10:00 AM",
        "status": "waiting",
        "status_label": "Waiting for consultation",
        "created_at": appointment["created_at"],
    }
    slots = client.get(f"/api/doctors/dr-perera/slots?date={TOMORROW}").json()["slots"]
    assert {"time": "10:00", "label": "10:00 AM"} not in slots


def test_book_requires_patient_details(client: TestClient, login: Login) -> None:
    login(with_patient=False)
    response = book(client)
    assert response.status_code == 412
    assert response.json() == {"detail": "Please complete your patient details first."}


def test_book_taken_slot(client: TestClient, login: Login) -> None:
    login(email="first@example.com")
    assert book(client).status_code == 201
    login(email="second@example.com")
    response = book(client)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "That time slot has just been booked. Please choose another."
    }


def test_book_invalid_input_message_passes_through(client: TestClient, login: Login) -> None:
    login()
    response = book(client, date="2020-01-01")
    assert response.status_code == 400
    assert response.json() == {"detail": "Please choose a date within the next 90 days."}


def test_book_validation(client: TestClient, login: Login) -> None:
    login()
    response = client.post(
        "/api/appointments", json={"doctor_id": "dr perera", "date": "tomorrow", "time": "10"}
    )
    assert response.status_code == 422
    assert response.json()["fields"] == {
        "doctor_id": "Please choose a valid doctor.",
        "date": "Please choose a valid date.",
        "time": "Please choose a valid time slot.",
    }


@pytest.mark.parametrize(
    ("error", "status"),
    [(SlotTaken(), 409), (InvalidInput("Nope."), 400), (ServiceUnavailable(), 503)],
)
def test_book_error_mapping(
    client: TestClient, fake: FakeGateway, login: Login, error: Exception, status: int
) -> None:
    login()
    fake.failures["book_appointment"] = error
    response = book(client)
    assert response.status_code == status
    assert response.json() == {"detail": str(error)}


def test_second_active_upcoming_booking_is_rejected(
    client: TestClient, fake: FakeGateway, login: Login
) -> None:
    login()
    first = book(client).json()["appointment"]
    other_day = (TODAY + dt.timedelta(days=5)).isoformat()
    response = book(client, time="14:00", date=other_day)
    assert response.status_code == 400
    assert response.json() == {"detail": ALREADY_BOOKED}
    assert len(fake.appointments) == 1
    assert client.get("/api/appointments/current").json() == {"appointment": first}


@pytest.mark.parametrize(
    ("status", "date"),
    [
        ("completed", TOMORROW),
        ("cancelled", TOMORROW),
        ("waiting", (TODAY - dt.timedelta(days=1)).isoformat()),  # past-dated never blocks
    ],
)
def test_finished_or_past_appointment_does_not_block_booking(
    client: TestClient, fake: FakeGateway, login: Login, status: str, date: str
) -> None:
    login()
    assert book(client).status_code == 201
    fake.appointments[0].update(status=status, appointment_date=date)
    response = book(client, time="14:00")
    assert response.status_code == 201
    assert response.json()["appointment"]["token"] == "PC-002"


def test_current_appointment(client: TestClient, fake: FakeGateway, login: Login) -> None:
    session = login()
    missing = client.get("/api/appointments/current")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "No upcoming appointment found."}

    # An old appointment that is still "waiting" but in the past is neither current nor blocking.
    fake.appointments.append(
        {
            "id": "old-appt",
            "patient_id": session.user_id,
            "token": "PC-009",
            "token_number": 9,
            "appointment_date": (TODAY - dt.timedelta(days=1)).isoformat(),
            "slot_time": "09:00:00",
            "slot_label": "09:00 AM",
            "status": "waiting",
            "doctor_id": "dr-perera",
            "created_at": "2026-10-12T08:00:00+00:00",
        }
    )
    assert client.get("/api/appointments/current").status_code == 404
    booked = book(client, time="14:00").json()["appointment"]
    response = client.get("/api/appointments/current")
    assert response.status_code == 200
    assert response.json() == {"appointment": booked}
    assert booked["token"] == "PC-001"
    assert booked["time_label"] == "02:00 PM"


def test_queue_for_current_appointment(client: TestClient, login: Login) -> None:
    login(email="early@example.com")
    book(client, time="09:00", date=TODAY.isoformat())
    login(email="me@example.com")
    mine = book(client, time="10:00", date=TODAY.isoformat()).json()["appointment"]

    response = client.get("/api/appointments/current/queue")
    assert response.status_code == 200
    assert response.json() == {
        "queue": {
            "token": "PC-002",
            "position": 2,
            "ahead": 1,
            "total_in_queue": 2,
            "estimated_wait_minutes": 10,
            "now_serving": "PC-001",
            "serving_label": "Now serving",
            "is_today": True,
            "progress_percent": 0,
            "status": "waiting",
            "status_label": "Waiting for consultation",
            "appointment": mine,
        }
    }


def test_queue_for_future_day_is_first_in_line(client: TestClient, login: Login) -> None:
    login()
    book(client)
    queue = client.get("/api/appointments/current/queue").json()["queue"]
    assert (queue["position"], queue["ahead"], queue["now_serving"]) == (1, 0, "PC-001")
    assert queue["serving_label"] == "First in line"
    assert queue["is_today"] is False


def test_queue_not_found(client: TestClient, fake: FakeGateway, login: Login) -> None:
    login()
    assert client.get("/api/appointments/current/queue").status_code == 404
    book(client)
    fake.failures["queue_snapshot"] = NotFound()
    response = client.get("/api/appointments/current/queue")
    assert response.status_code == 404
    assert response.json() == {"detail": "No upcoming appointment found."}
