from fastapi import APIRouter, status

from app.deps import CurrentUserDep, GatewayDep
from app.errors import NotFound
from app.presenters import present_appointment, present_queue
from app.schemas import (
    AppointmentEnvelope,
    AppointmentOut,
    AppointmentRequest,
    ErrorBody,
    QueueEnvelope,
    QueueOut,
)

router = APIRouter(
    prefix="/appointments", tags=["appointments"], responses={401: {"model": ErrorBody}}
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AppointmentEnvelope,
    responses={
        400: {"model": ErrorBody},
        409: {"model": ErrorBody},
        412: {"model": ErrorBody},
        422: {"model": ErrorBody},
    },
)
def book(
    body: AppointmentRequest, user: CurrentUserDep, gateway: GatewayDep
) -> AppointmentEnvelope:
    row = gateway.book_appointment(user.access_token, body.doctor_id, body.date, body.time)
    return AppointmentEnvelope(appointment=AppointmentOut.model_validate(present_appointment(row)))


@router.get("/current", response_model=AppointmentEnvelope, responses={404: {"model": ErrorBody}})
def current(user: CurrentUserDep, gateway: GatewayDep) -> AppointmentEnvelope:
    row = gateway.current_appointment(user.access_token)
    if row is None:
        raise NotFound()
    return AppointmentEnvelope(appointment=AppointmentOut.model_validate(present_appointment(row)))


@router.get("/current/queue", response_model=QueueEnvelope, responses={404: {"model": ErrorBody}})
def current_queue(user: CurrentUserDep, gateway: GatewayDep) -> QueueEnvelope:
    appointment = gateway.current_appointment(user.access_token)
    if appointment is None:
        raise NotFound()
    snapshot = gateway.queue_snapshot(user.access_token, str(appointment["id"]))
    return QueueEnvelope(queue=QueueOut.model_validate(present_queue(snapshot, appointment)))
