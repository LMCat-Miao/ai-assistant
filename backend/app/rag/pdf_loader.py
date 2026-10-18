from pathlib import Path
import pymupdf

def extract_pdf_pages(pdf_path: str | Path) -> list[dict]:
    """提取PDF每一页的文本
    提取格式：
    [
        {"page": 1, "text": "第一页的文本"},
        {"page": 2, "text": "第二页的文本"},
    ]
    """
    #将字符串路径统一转换成PATH对象
    file_path = Path(pdf_path)
    #文件不在时立即报错，避免后续出现问题
    if not file_path.is_file():
        raise ValueError(f"PDF文件不存在:{file_path}")

    #以只读方式打开PDF
    pages = []
    with pymupdf.open(file_path) as pdf:
        for page_index,page in enumerate(pdf):
            #提取当前页的文本内容
            text = page.get_text("text")
            #清理首位空白
            text = text.strip()
            #空白页不加入结果
            if text:
                pages.append({
                    #PDF页码从1开始，python索引从0开始
                    "page":page_index + 1,
                    "text":text,
                })
    #有些PDF是纯图片扫描件，提取不到文字
    if not pages:
        raise ValueError("PDF中没有有提取到文本，请确认文件是否为扫描件")
    return pages