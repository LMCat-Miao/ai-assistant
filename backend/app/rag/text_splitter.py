def spilt_text(
        text:str,
        chunk_size:500,
        chunk_overlap:80,
)-> list[str]:
    """讲一段文本切分成带重叠的文本块"""
    if chunk_size < 0:
        raise ValueError("chunk_size必须大于0")
    if chunk_overlap < 0 or chunk_size <= chunk_overlap :
        raise ValueError("chunk_overlap必须大于等于0且小于chunk_size")
    #去掉首位空白，避免生成空白文本块
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        #当前文本块的结束位置
        end = min(start + chunk_size,text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)
        #最后一块已经处理完成，不再继续
        if end == text_length:
            break
        #下一块回退chunk_overlap个字符，让相邻块共享一部分内容，减少上下文被截断的影响
        start = end - chunk_overlap
    return chunks
