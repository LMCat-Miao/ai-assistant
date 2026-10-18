
import hashlib
from pathlib import Path

from sentence_transformers import SentenceTransformer

from app.rag.pdf_loader import extract_pdf_pages
from app.rag.text_splitter import spilt_text
from app.rag.vector_store import VectorStore


# 当前脚本所在目录是 backend/experiments。
BASE_DIR = Path(__file__).resolve().parents[1]

# 测试 PDF 存放目录。
PDF_DIR = BASE_DIR / "experiments" / "pdfs"

# 使用之前验证过的中文向量模型。
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def ingest_pdf(pdf_path: str | Path) -> int:
    """提取 PDF、切分文本、生成向量并保存到 Chroma。"""

    file_path = Path(pdf_path)

    print(f"\n开始处理 PDF：{file_path.name}")

    # 第一步：提取每一页的文字。
    pages = extract_pdf_pages(file_path)
    print(f"成功提取 {len(pages)} 个有文本的页面")

    # 第二步：按页分块，同时保存页码。
    documents = []
    metadatas = []

    for page_data in pages:
        chunks = spilt_text(
            page_data["text"],
            chunk_size=500,
            chunk_overlap=80,
        )

        for chunk in chunks:
            documents.append(chunk)
            metadatas.append({
                "source": file_path.name,
                "page": page_data["page"],
                "file_type": "pdf",
            })

    if not documents:
        raise ValueError("PDF 没有生成任何有效文本块")

    print(f"文本分块完成，共 {len(documents)} 块")

    # 第三步：根据文件内容生成稳定的文档标识。
    # 同一文件重复执行时，可以生成相同的 ID。
    file_hash = hashlib.sha256(
        file_path.read_bytes()
    ).hexdigest()[:16]

    ids = [
        f"pdf_{file_hash}_chunk_{index:04d}"
        for index in range(len(documents))
    ]

    # 第四步：生成每个文本块的向量。
    print("正在加载向量模型……")
    model = SentenceTransformer(MODEL_NAME)

    print("正在生成文本向量……")
    embeddings = model.encode(
        documents,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).tolist()

    # 第五步：保存文本、向量和元数据。
    store = VectorStore()

    store.add_chunks(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print("PDF 入库成功")
    print(f"本次写入文本块数：{len(documents)}")
    print(f"文档标识：{file_hash}")
    print(f"Chroma 当前记录总数：{store.collection.count()}")

    return len(documents)


if __name__ == "__main__":
    # 找出测试目录中的 PDF 文件。
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"没有找到 PDF，请将测试文件放入：{PDF_DIR}"
        )

    # 本节先处理第一份 PDF，避免一次性导入整个目录。
    ingest_pdf(pdf_files[0])