from app.rag.document_loader import extract_text_from_pdf


pdf_path = r"D:\实习协议.pdf"

text = extract_text_from_pdf(pdf_path)

print("========== PDF 文本开始 ==========")
print(text[:3000])
print("========== PDF 文本结束 ==========")