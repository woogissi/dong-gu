from fastapi import APIRouter

from app.schemas.common import BaseResponse
from app.schemas.search import SearchRequest
from app.services.retrieval_service import search_documents

router = APIRouter()


@router.post("/test", response_model=BaseResponse)
async def search_test(req: SearchRequest):
    result = await search_documents(req)

    return BaseResponse(
        success=True,
        code="SEARCH_SUCCESS",
        message="검색이 완료되었습니다.",
        data=result,
        meta={"top_k": req.top_k},
    )
