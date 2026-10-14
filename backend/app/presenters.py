"""Pure formatting of database rows into API shapes: labels and queue maths."""

from collections.abc import Mapping
from datetime import date, time
from typing import Any

Row = Mapping[str, Any]

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

STATUS_LABELS = {
    "waiting": "Waiting for consultation",
    "in_consultation": "In consultation",
    "completed": "Consultation completed",
    "cancelled": "Cancelled",
}


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _as_time(value: time | str) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def date_label(value: date | str) -> str:
    """'5 October 2026' (no leading zero, locale independent)."""
    day = _as_date(value)
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def normalise_time(value: time | str) -> str:
    """Postgres 'HH:MM:SS' -> 'HH:MM'."""
    return _as_time(value).strftime("%H:%M")


def time_label(value: time | str, label: str | None = None) -> str:
    """DB label when present, else the equivalent of strftime('%I:%M %p') without locale."""
    if label:
        return label
    moment = _as_time(value)
    hour = moment.hour % 12 or 12
    return f"{hour:02d}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def queue_ahead(position: int | None) -> int:
    return 0 if position is None else max(position - 1, 0)


def estimated_wait_minutes(ahead: int, avg_consult_minutes: int) -> int:
    return ahead * avg_consult_minutes


def progress_percent(total: int, position: int | None) -> int:
    """clamp(round((total - position) / total * 100), 0, 100); rounds half up like JS Math.round."""
    if not total or position is None:
        return 0
    rounded = (200 * (total - position) + total) // (2 * total)
    return min(max(rounded, 0), 100)


def serving_label(is_today: bool) -> str:
    return "Now serving" if is_today else "First in line"


def present_doctor(row: Row) -> dict[str, str]:
    return {
        "id": str(row["id"]),
        "name": str(row.get("name") or ""),
        "specialty": str(row.get("specialty") or ""),
    }


def present_patient(row: Row) -> dict[str, str]:
    return {key: str(row.get(key) or "") for key in ("first_name", "last_name", "mobile", "email")}


def present_slot(row: Row) -> dict[str, str]:
    return {
        "time": normalise_time(row["slot_time"]),
        "label": time_label(row["slot_time"], row.get("label")),
    }


def present_appointment(row: Row) -> dict[str, Any]:
    """Row shape of current_appointment(); doctor/slot names may be absent."""
    day = _as_date(row["appointment_date"])
    status = str(row["status"])
    return {
        "id": str(row["id"]),
        "token": str(row["token"]),
        "doctor": {
            "id": str(row["doctor_id"]),
            "name": str(row.get("doctor_name") or ""),
            "specialty": str(row.get("doctor_specialty") or ""),
        },
        "date": day.isoformat(),
        "date_label": date_label(day),
        "time": normalise_time(row["slot_time"]),
        "time_label": time_label(row["slot_time"], row.get("slot_label")),
        "status": status,
        "status_label": status_label(status),
        "created_at": str(row.get("created_at") or ""),
    }


def present_queue(snapshot: Row, appointment: Row) -> dict[str, Any]:
    raw_position = snapshot.get("queue_position")
    position = None if raw_position is None else int(raw_position)
    total = int(snapshot.get("total_in_queue") or 0)
    ahead = queue_ahead(position)
    is_today = bool(snapshot.get("is_today"))
    status = str(snapshot.get("status") or appointment["status"])
    return {
        "token": str(snapshot.get("token") or appointment["token"]),
        "position": position,
        "ahead": ahead,
        "total_in_queue": total,
        "estimated_wait_minutes": estimated_wait_minutes(
            ahead, int(snapshot.get("avg_consult_minutes") or 0)
        ),
        "now_serving": snapshot.get("now_serving_token"),
        "serving_label": serving_label(is_today),
        "is_today": is_today,
        "progress_percent": progress_percent(total, position),
        "status": status,
        "status_label": status_label(status),
        "appointment": present_appointment(appointment),
    }
