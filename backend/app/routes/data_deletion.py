from fastapi import APIRouter, Header

from ..schemas.data_deletion import DataDeletionRequest, DataDeletionResponse
from ..services.data_deletion_service import DataDeletionService

router = APIRouter(prefix='/api/data-deletion', tags=['data deletion'])


@router.post('/request', response_model=DataDeletionResponse)
async def request_data_deletion(payload: DataDeletionRequest, authorization: str = Header(default='')) -> DataDeletionResponse:
    result = await DataDeletionService().submit_request(payload, authorization)
    return DataDeletionResponse(**result)
