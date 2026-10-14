import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.deps import CurrentUserDep, GatewayDep
from app.presenters import present_doctor, present_slot
from app.schemas import (
    DoctorId,
    DoctorOut,
    DoctorsEnvelope,
    ErrorBody,
    IsoDate,
    SlotOut,
    SlotsEnvelope,
)

router = APIRouter(prefix="/doctors", tags=["doctors"], responses={401: {"model": ErrorBody}})

# Mirrors the SQL booking window (available_slots / book_appointment: clinic today .. today + 90).
BOOKING_WINDOW_DAYS = 90


@router.get("", response_model=DoctorsEnvelope)
def list_doctors(user: CurrentUserDep, gateway: GatewayDep) -> DoctorsEnvelope:
    rows = gateway.list_doctors(user.access_token)
    # The clinic's date comes from SQL so the date picker never guesses it from the browser clock.
    today = gateway.clinic_today(user.access_token)
    return DoctorsEnvelope(
        doctors=[DoctorOut.model_validate(present_doctor(row)) for row in rows],
        today=today.isoformat(),
        max_date=(today + dt.timedelta(days=BOOKING_WINDOW_DAYS)).isoformat(),
    )


@router.get(
    "/{doctor_id}/slots", response_model=SlotsEnvelope, responses={422: {"model": ErrorBody}}
)
def list_slots(
    doctor_id: Annotated[DoctorId, Path()],
    date: Annotated[IsoDate, Query()],
    user: CurrentUserDep,
    gateway: GatewayDep,
) -> SlotsEnvelope:
    rows = gateway.available_slots(user.access_token, doctor_id, date)
    slots = [SlotOut.model_validate(present_slot(row)) for row in rows]
    return SlotsEnvelope(date=date.isoformat(), slots=slots)
