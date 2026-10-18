
"""知识库 API：接收用户上传的 PDF 并触发 RAG 入库。"""

import tempfile
from pathlib import Path
from pydantic import BaseModel,Field
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.dependencies import get_current_user
from app.services.rag_ingestion_service import ingest_pdf
from app.services.rag_retrieval_service import retrieve_knowledge

router = APIRouter(
    prefix="/api/knowledge",
    tags=["知识库"],
)

# 第一版先限制单个 PDF 最大为 10 MB。
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/upload", status_code=status.HTTP_200_OK)
async def upload_knowledge_pdf(
    file: UploadFile = File(..., description="需要导入知识库的 PDF 文件"),
    current_user: dict = Depends(get_current_user),
):
    """上传 PDF，提取文本并将向量写入当前用户的知识库。"""

    # 1. 检查文件名和扩展名。
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传 PDF 格式的文件。",
        )

    # 2. 读取文件内容，并限制上传大小。
    content = await file.read(MAX_FILE_SIZE + 1)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传的文件为空。",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF 文件不能超过 10 MB。",
        )

    # 3. 检查 PDF 文件头。此检查不能代替完整的文件安全校验。
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容不是有效的 PDF 文件格式。",
        )

    temp_path = None

    try:
        # 4. 使用临时文件保存上传内容，不直接使用用户提供的路径。
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".pdf",
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        # 5. 使用 JWT 认证解析出的用户 ID，而不是接收前端传来的 user_id。
        result = ingest_pdf(
            pdf_path=temp_path,
            user_id=str(current_user["user_id"]),
            original_filename=Path(file.filename).name,
        )

        return {
            "message": "PDF 已成功导入知识库。",
            "data": result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        # 不向客户端暴露服务器内部异常和文件路径。
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF 处理失败，请检查服务端日志后重试。",
        ) from exc

    finally:
        # 6. 无论处理成功还是失败，都尝试删除临时文件。
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

        await file.close()


class KnowledgeSearchRequest(BaseModel):
    """知识库检索请求参数。"""

    query: str = Field(
        min_length=1,
        max_length=2000,
        description="用户提出的问题",
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="最多返回的文本块数量",
    )
    filename: str | None = Field(
        default=None,
        description="可选，指定检索的 PDF 文件名",
    )


@router.post("/search")
def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """检索当前登录用户知识库中的相关文本。"""

    try:
        results = retrieve_knowledge(
            query=request.query,
            user_id=str(current_user["user_id"]),
            top_k=request.top_k,
            filename=request.filename,
        )

        return {
            "message": "知识检索完成。",
            "data": {
                "query": request.query,
                "count": len(results),
                "results": results,
            },
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
