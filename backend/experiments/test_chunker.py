from app.rag.chunker import split_text


text = """
Vue 是一个用于构建用户界面的渐进式 JavaScript 框架。

Vue 3 的核心特性包括响应式系统、组件化和虚拟 DOM。

Vue 的响应式系统主要基于 Proxy 实现。
当响应式数据发生变化时，Vue 会通知相关依赖进行更新。

computed 用于声明计算属性。
watch 用于监听数据变化并执行副作用。
"""


chunks = split_text(
    text,
    chunk_size=100,
    chunk_overlap=20,
)


for index, chunk in enumerate(chunks, start=1):
    print(f"\n========== Chunk {index} ==========")
    print(chunk)