
from pathlib import Path

from app.rag.pdf_loader import extract_pdf_pages


def main():
    # 当前 PDF 的真实路径
    pdf_path = Path("experiments/pdfs/agent.pdf")

    # 复用项目现有的 PDF 解析函数
    pages = extract_pdf_pages(pdf_path)

    print(f"PDF 路径：{pdf_path.resolve()}")
    print(f"成功提取 {len(pages)} 个有文本的页面")
    print("=" * 80)

    for item in pages:
        print(f"\n========== 第 {item['page']} 页 ==========\n")
        print(item["text"])
        print("\n" + "-" * 80)


if __name__ == "__main__":
    main()
