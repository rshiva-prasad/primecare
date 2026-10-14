from fastapi import APIRouter

from app.deps import CurrentUserDep, GatewayDep
from app.presenters import present_patient
from app.schemas import ErrorBody, PatientEnvelope, PatientOut, PatientRequest

router = APIRouter(prefix="/patients", tags=["patients"], responses={401: {"model": ErrorBody}})


@router.get("/me", response_model=PatientEnvelope)
def get_my_details(user: CurrentUserDep, gateway: GatewayDep) -> PatientEnvelope:
    row = gateway.get_patient(user.access_token, user.id)
    return PatientEnvelope(
        patient=None if row is None else PatientOut.model_validate(present_patient(row))
    )


@router.put("/me", response_model=PatientEnvelope, responses={422: {"model": ErrorBody}})
def save_my_details(
    body: PatientRequest, user: CurrentUserDep, gateway: GatewayDep
) -> PatientEnvelope:
    row = gateway.upsert_patient(user.access_token, user.id, body.model_dump())
    return PatientEnvelope(patient=PatientOut.model_validate(present_patient(row)))
