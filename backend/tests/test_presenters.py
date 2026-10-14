from datetime import date, time

import pytest

from app import presenters as p


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 10, 5), "5 October 2026"),
        ("2026-10-15", "15 October 2026"),
        ("2026-01-01T00:00:00+00:00", "1 January 2026"),
        (date(2026, 12, 31), "31 December 2026"),
    ],
)
def test_date_label(value: date | str, expected: str) -> None:
    assert p.date_label(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("10:00:00", "10:00"), ("09:30", "09:30"), (time(14, 0), "14:00"), ("16:00:00.000", "16:00")],
)
def test_normalise_time(value: str | time, expected: str) -> None:
    assert p.normalise_time(value) == expected


@pytest.mark.parametrize(
    ("value", "label", "expected"),
    [
        ("10:00:00", "10:00 AM", "10:00 AM"),
        ("09:00:00", None, "09:00 AM"),
        ("14:30:00", "", "02:30 PM"),
        (time(0, 5), None, "12:05 AM"),
        (time(12, 0), None, "12:00 PM"),
    ],
)
def test_time_label(value: str | time, label: str | None, expected: str) -> None:
    assert p.time_label(value, label) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("waiting", "Waiting for consultation"),
        ("in_consultation", "In consultation"),
        ("completed", "Consultation completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No show"),
    ],
)
def test_status_label(status: str, expected: str) -> None:
    assert p.status_label(status) == expected


@pytest.mark.parametrize(("position", "ahead"), [(None, 0), (1, 0), (2, 1), (5, 4), (0, 0)])
def test_queue_ahead(position: int | None, ahead: int) -> None:
    assert p.queue_ahead(position) == ahead


def test_estimated_wait_minutes() -> None:
    assert p.estimated_wait_minutes(4, 12) == 48
    assert p.estimated_wait_minutes(0, 20) == 0


@pytest.mark.parametrize(
    ("total", "position", "expected"),
    [
        (0, None, 0),
        (0, 1, 0),
        (5, None, 0),
        (1, 1, 0),
        (8, 4, 50),
        (5, 4, 20),
        (8, 1, 88),  # 87.5 rounds half up like Math.round
        (3, 2, 33),
        (3, 1, 67),
        (2, 5, 0),  # clamped low
        (4, -4, 100),  # clamped high
    ],
)
def test_progress_percent(total: int, position: int | None, expected: int) -> None:
    assert p.progress_percent(total, position) == expected


def test_serving_label() -> None:
    assert p.serving_label(True) == "Now serving"
    assert p.serving_label(False) == "First in line"


def test_present_doctor_and_patient_and_slot() -> None:
    assert p.present_doctor({"id": "dr-a", "name": "Dr. A", "specialty": None}) == {
        "id": "dr-a",
        "name": "Dr. A",
        "specialty": "",
    }
    patient = {"first_name": "Pat", "last_name": "Lee", "mobile": "0400 000 000", "id": "x"}
    assert p.present_patient(patient) == {
        "first_name": "Pat",
        "last_name": "Lee",
        "mobile": "0400 000 000",
        "email": "",
    }
    assert p.present_slot({"slot_time": "14:00:00", "label": "02:00 PM"}) == {
        "time": "14:00",
        "label": "02:00 PM",
    }
    assert p.present_slot({"slot_time": "16:00:00"}) == {"time": "16:00", "label": "04:00 PM"}


APPOINTMENT_ROW = {
    "id": "a1",
    "token": "PC-024",
    "token_number": 24,
    "appointment_date": "2026-10-15",
    "slot_time": "10:00:00",
    "slot_label": "10:00 AM",
    "status": "waiting",
    "doctor_id": "dr-perera",
    "doctor_name": "Dr. Sarah Perera",
    "doctor_specialty": "General Practitioner",
    "created_at": "2026-10-13T08:00:00+00:00",
}


def test_present_appointment() -> None:
    assert p.present_appointment(APPOINTMENT_ROW) == {
        "id": "a1",
        "token": "PC-024",
        "doctor": {
            "id": "dr-perera",
            "name": "Dr. Sarah Perera",
            "specialty": "General Practitioner",
        },
        "date": "2026-10-15",
        "date_label": "15 October 2026",
        "time": "10:00",
        "time_label": "10:00 AM",
        "status": "waiting",
        "status_label": "Waiting for consultation",
        "created_at": "2026-10-13T08:00:00+00:00",
    }


def test_present_appointment_from_bare_booking_row() -> None:
    row = {k: APPOINTMENT_ROW[k] for k in ("id", "token", "appointment_date", "slot_time")}
    row |= {"status": "waiting", "doctor_id": "dr-perera", "created_at": None}
    result = p.present_appointment(row)
    assert result["doctor"] == {"id": "dr-perera", "name": "", "specialty": ""}
    assert result["time_label"] == "10:00 AM"
    assert result["created_at"] == ""


def test_present_queue_today() -> None:
    snapshot = {
        "token": "PC-024",
        "queue_position": 5,
        "total_in_queue": 8,
        "now_serving_token": "PC-020",
        "avg_consult_minutes": 10,
        "is_today": True,
        "status": "waiting",
    }
    queue = p.present_queue(snapshot, APPOINTMENT_ROW)
    assert queue == {
        "token": "PC-024",
        "position": 5,
        "ahead": 4,
        "total_in_queue": 8,
        "estimated_wait_minutes": 40,
        "now_serving": "PC-020",
        "serving_label": "Now serving",
        "is_today": True,
        "progress_percent": 38,
        "status": "waiting",
        "status_label": "Waiting for consultation",
        "appointment": p.present_appointment(APPOINTMENT_ROW),
    }


def test_present_queue_future_and_out_of_queue() -> None:
    snapshot = {
        "token": None,
        "queue_position": None,
        "total_in_queue": 0,
        "now_serving_token": None,
        "avg_consult_minutes": None,
        "is_today": False,
        "status": "completed",
    }
    queue = p.present_queue(snapshot, APPOINTMENT_ROW)
    assert queue["token"] == "PC-024"
    assert queue["position"] is None
    assert queue["ahead"] == 0
    assert queue["estimated_wait_minutes"] == 0
    assert queue["progress_percent"] == 0
    assert queue["serving_label"] == "First in line"
    assert queue["status_label"] == "Consultation completed"
