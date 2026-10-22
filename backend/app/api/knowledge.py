"""知识库 API：上传、检索、文档列表与全文总结。"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.services.rag_document_service import (
    DocumentNotFoundError,
    DocumentVersionConflictError,
    list_user_documents,
)
from app.services.rag_ingestion_service import ingest_pdf
from app.services.rag_retrieval_service import retrieve_knowledge
from app.services.rag_summarize_service import (
    DocumentTooLargeError,
    SummarizeModelError,
    summarize_document,
)

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


@router.get("/documents")
def get_knowledge_documents(
    current_user: dict = Depends(get_current_user),
):
    """列出当前登录用户知识库中的文档。

    返回字段（data.documents[]）：
    - filename: 文件名（source）
    - chunk_count / page_count
    - file_hash: 可唯一确定时的版本哈希；版本冲突时为 null
    - version_conflict: 同名多版本或新旧混杂时为 true
    """

    try:
        documents = list_user_documents(
            user_id=str(current_user["user_id"]),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": "文档列表获取完成。",
        "data": {
            "count": len(documents),
            "documents": documents,
        },
    }


class KnowledgeSummarizeRequest(BaseModel):
    """指定 PDF 全文总结请求。"""

    filename: str = Field(
        min_length=1,
        max_length=255,
        description="要总结的 PDF 文件名（需已上传到当前用户知识库）",
    )
    focus: str | None = Field(
        default=None,
        max_length=1000,
        description="可选，补充总结侧重点或要求",
    )


@router.post("/summarize")
def summarize_knowledge_document(
    request: KnowledgeSummarizeRequest,
    current_user: dict = Depends(get_current_user),
):
    """对当前用户指定 PDF 做全文总结（短文一次，长文 Map-Reduce）。

    与 /search、/chat/stream 的知识问答相互独立：本接口拉取全文 Chunk，
    不使用语义 top_k 检索。

    成功 data 字段：
    - filename / file_hash / chunk_count / page_count
    - batch_count / mode（oneshot | map_reduce）/ partial_count
    - summary：终稿文本

    错误语义：
    - 400：参数错误或文档过长超过批次数上限
    - 404：当前用户下文档不存在或无可用文本
    - 409：同名多版本 / 新旧混杂，无法可靠定位
    - 502：模型调用失败或某批次失败（不返回伪完整终稿）
    """

    try:
        result = summarize_document(
            user_id=str(current_user["user_id"]),
            filename=request.filename,
            focus=request.focus,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SummarizeModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {
        "message": "文档总结完成。",
        "data": result,
    }
