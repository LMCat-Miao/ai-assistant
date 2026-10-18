from pathlib import Path

import pymupdf


def extract_text_from_pdf(file_path: str) -> str:
    """
    从 PDF 文件中提取全部文本。

    Args:
        file_path: PDF 文件路径

    Returns:
        str: PDF 中提取出来的全部文本
    """

    pdf_path = Path(file_path)

    # 打开 PDF 文件
    document = pymupdf.open(pdf_path)

    text_parts: list[str] = []

    # 遍历 PDF 的每一页
    for page in document:
        page_text = page.get_text()

        if page_text:
            text_parts.append(page_text)

    # 关闭 PDF
    document.close()

    # 将所有页面文本拼接起来
    return "\n".join(text_parts)