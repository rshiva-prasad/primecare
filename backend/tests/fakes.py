"""In-memory Gateway that mimics the SQL contract closely enough for routing tests."""

import datetime as dt
import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.errors import (
    InvalidCredentials,
    InvalidInput,
    NotAuthenticated,
    NotFound,
    PatientDetailsRequired,
    RegistrationFailed,
    SlotTaken,
)
from app.gateway import AuthResult, UserInfo

TODAY = dt.date(2026, 10, 13)
QUEUE_STATUSES = ("waiting", "in_consultation")
ALREADY_BOOKED = "You already have an upcoming appointment."

DOCTORS = [
    {"id": "dr-perera", "name": "Dr. Sarah Perera", "specialty": "General Practitioner", "avg": 10},
    {"id": "dr-fernando", "name": "Dr. James Fernando", "specialty": "Pediatrician", "avg": 12},
    {"id": "dr-sharma", "name": "Dr. Anita Sharma", "specialty": "Dermatologist", "avg": 15},
    {"id": "dr-desilva", "name": "Dr. Michael De Silva", "specialty": "Cardiologist", "avg": 20},
]
SLOTS = {
    "09:00": "09:00 AM",
    "09:30": "09:30 AM",
    "10:00": "10:00 AM",
    "10:30": "10:30 AM",
    "11:00": "11:00 AM",
    "14:00": "02:00 PM",
    "14:30": "02:30 PM",
    "15:00": "03:00 PM",
    "16:00": "04:00 PM",
}


@dataclass
class FakeUser:
    id: str
    email: str
    password: str


@dataclass
class FakeGateway:
    today: dt.date = TODAY
    now_time: str = "08:00"
    confirm_email: bool = False
    users: dict[str, FakeUser] = field(default_factory=dict)
    access: dict[str, str] = field(default_factory=dict)
    refresh_tokens: dict[str, str] = field(default_factory=dict)
    patients: dict[str, dict[str, Any]] = field(default_factory=dict)
    appointments: list[dict[str, Any]] = field(default_factory=list)
    failures: dict[str, Exception] = field(default_factory=dict)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    _counter: "itertools.count[int]" = field(default_factory=lambda: itertools.count(1))
    _tokens: dict[dt.date, int] = field(default_factory=dict)

    # helpers

    def _call(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if name in self.failures:
            raise self.failures[name]

    def called(self, name: str) -> list[tuple[Any, ...]]:
        return [args for call, args in self.calls if call == name]

    def _issue(self, user: FakeUser) -> AuthResult:
        n = next(self._counter)
        access, refresh = f"access-{n}", f"refresh-{n}"
        self.access[access] = user.id
        self.refresh_tokens[refresh] = user.id
        return AuthResult(user.id, user.email, access, refresh, 3600)

    def _user_for(self, token: str) -> FakeUser:
        user_id = self.access.get(token)
        if user_id is None:
            raise NotAuthenticated()  # like PGRST301 for an expired/invalid JWT
        return next(u for u in self.users.values() if u.id == user_id)

    def add_user(self, email: str = "pat@example.com", password: str = "s3cret-pass") -> FakeUser:
        user = FakeUser(str(uuid.uuid4()), email, password)
        self.users[email] = user
        return user

    def login(self, email: str = "pat@example.com") -> AuthResult:
        return self._issue(self.users[email])

    def expire(self, access_token: str) -> None:
        self.access.pop(access_token, None)

    # auth

    def sign_up(self, email: str, password: str) -> AuthResult:
        self._call("sign_up", email)
        if email in self.users:
            raise RegistrationFailed()
        user = self.add_user(email, password)
        if self.confirm_email:
            return AuthResult(user.id, email)
        return self._issue(user)

    def sign_in(self, email: str, password: str) -> AuthResult:
        self._call("sign_in", email)
        user = self.users.get(email)
        if user is None or user.password != password:
            raise InvalidCredentials()
        return self._issue(user)

    def get_user(self, access_token: str) -> UserInfo | None:
        self._call("get_user", access_token)
        try:
            user = self._user_for(access_token)
        except NotAuthenticated:
            return None
        return UserInfo(user.id, user.email)

    def refresh(self, refresh_token: str) -> AuthResult | None:
        self._call("refresh", refresh_token)
        user_id = self.refresh_tokens.pop(refresh_token, None)  # rotation: single use
        if user_id is None:
            return None
        return self._issue(next(u for u in self.users.values() if u.id == user_id))

    def sign_out(self, access_token: str) -> bool:
        self._call("sign_out", access_token)
        user_id = self.access.pop(access_token, None)
        if user_id is None:
            return False  # GoTrue rejects an expired/unknown JWT, so nothing is revoked
        self.refresh_tokens = {k: v for k, v in self.refresh_tokens.items() if v != user_id}
        return True

    # data

    def get_patient(self, token: str, user_id: str) -> dict[str, Any] | None:
        self._call("get_patient", token, user_id)
        user = self._user_for(token)
        row = self.patients.get(user.id)  # RLS: only ever the caller's row
        return None if row is None else dict(row)

    def upsert_patient(self, token: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._call("upsert_patient", token, user_id, data)
        user = self._user_for(token)
        self.patients[user.id] = {**data, "id": user.id}
        return dict(self.patients[user.id])

    def clinic_today(self, token: str) -> dt.date:
        self._call("clinic_today", token)
        self._user_for(token)
        return self.today

    def list_doctors(self, token: str) -> list[dict[str, Any]]:
        self._call("list_doctors", token)
        self._user_for(token)
        return [
            {k: d[k] for k in ("id", "name", "specialty")}
            for d in sorted(DOCTORS, key=lambda d: d["name"])
        ]

    def _taken(self, doctor_id: str, date: dt.date) -> set[str]:
        return {
            a["slot_time"][:5]
            for a in self.appointments
            if a["doctor_id"] == doctor_id
            and a["appointment_date"] == date.isoformat()
            and a["status"] != "cancelled"
        }

    def _bookable(self, doctor_id: str, date: dt.date) -> list[str]:
        if not any(d["id"] == doctor_id for d in DOCTORS):
            return []
        if date < self.today or date > self.today + dt.timedelta(days=90):
            return []
        slots = [s for s in SLOTS if s not in self._taken(doctor_id, date)]
        if date == self.today:
            slots = [s for s in slots if s > self.now_time]
        return slots

    def available_slots(self, token: str, doctor_id: str, date: dt.date) -> list[dict[str, Any]]:
        self._call("available_slots", token, doctor_id, date)
        self._user_for(token)
        return [
            {"slot_time": f"{s}:00", "label": SLOTS[s]} for s in self._bookable(doctor_id, date)
        ]

    def book_appointment(
        self, token: str, doctor_id: str, date: dt.date, time: str
    ) -> dict[str, Any]:
        self._call("book_appointment", token, doctor_id, date, time)
        user = self._user_for(token)
        if user.id not in self.patients:
            raise PatientDetailsRequired()
        if self._upcoming(user.id):  # SQL: one active upcoming appointment per patient (PC400)
            raise InvalidInput(ALREADY_BOOKED)
        doctor = next((d for d in DOCTORS if d["id"] == doctor_id), None)
        if doctor is None or time not in SLOTS:
            raise InvalidInput("Please choose an available doctor and time.")
        if date < self.today or date > self.today + dt.timedelta(days=90):
            raise InvalidInput("Please choose a date within the next 90 days.")
        if date == self.today and time <= self.now_time:
            raise InvalidInput("That time has already passed. Please choose a later slot.")
        if time in self._taken(doctor_id, date):
            raise SlotTaken()  # the SQL rolls the token counter back too
        number = self._tokens.get(date, 0) + 1
        self._tokens[date] = number
        row = {
            "id": str(uuid.uuid4()),
            "patient_id": user.id,
            "token": f"PC-{number:03d}",
            "token_number": number,
            "appointment_date": date.isoformat(),
            "slot_time": f"{time}:00",
            "slot_label": SLOTS[time],
            "status": "waiting",
            "doctor_id": doctor_id,
            "doctor_name": doctor["name"],
            "doctor_specialty": doctor["specialty"],
            "created_at": f"2026-10-13T08:{len(self.appointments):02d}:00+00:00",
        }
        self.appointments.append(row)
        return dict(row)

    def _upcoming(self, user_id: str) -> list[dict[str, Any]]:
        return [
            a
            for a in self.appointments
            if a["patient_id"] == user_id
            and a["status"] in QUEUE_STATUSES
            and a["appointment_date"] >= self.today.isoformat()
        ]

    def current_appointment(self, token: str) -> dict[str, Any] | None:
        self._call("current_appointment", token)
        user = self._user_for(token)
        mine = self._upcoming(user.id)
        return dict(max(mine, key=lambda a: a["created_at"])) if mine else None

    def queue_snapshot(self, token: str, appointment_id: str) -> dict[str, Any]:
        self._call("queue_snapshot", token, appointment_id)
        user = self._user_for(token)
        mine = next(
            (a for a in self.appointments if a["id"] == appointment_id),
            None,
        )
        if mine is None or mine["patient_id"] != user.id:
            raise NotFound()
        queue = sorted(
            (
                a
                for a in self.appointments
                if a["doctor_id"] == mine["doctor_id"]
                and a["appointment_date"] == mine["appointment_date"]
                and a["status"] in QUEUE_STATUSES
            ),
            key=lambda a: (a["slot_time"], a["token_number"]),
        )
        ids = [a["id"] for a in queue]
        doctor = next(d for d in DOCTORS if d["id"] == mine["doctor_id"])
        return {
            "token": mine["token"],
            "queue_position": ids.index(mine["id"]) + 1 if mine["id"] in ids else None,
            "total_in_queue": len(queue),
            "now_serving_token": queue[0]["token"] if queue else None,
            "avg_consult_minutes": doctor["avg"],
            "is_today": mine["appointment_date"] == self.today.isoformat(),
            "status": mine["status"],
        }
