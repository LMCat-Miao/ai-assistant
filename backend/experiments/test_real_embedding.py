
from sentence_transformers import SentenceTransformer

# 1. 加载中文文本 Embedding 模型
# 首次运行需要下载模型文件，等待时间可能比较长
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

# 2. 准备一段测试文本
text = "Vue 的响应式系统基于 Proxy 实现。"

# 3. 将文本转换为真实的 Embedding 向量
vector = model.encode(text)

# 4. 查看转换结果
print("原始文本：")
print(text)

print("\n向量的数据类型：")
print(type(vector))

print("\n向量维度：")
print(len(vector))

print("\n向量前 10 个数字：")
print(vector[:10])