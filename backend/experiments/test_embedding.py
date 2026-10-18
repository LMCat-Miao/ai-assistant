from app.rag.embeddings import fake_embedding


text = "Vue 的响应式系统基于 Proxy 实现。"

vector = fake_embedding(text)

print("原始文本：")
print(text)

print("\nEmbedding 向量：")
print(vector)

print("\n向量维度：")
print(len(vector))