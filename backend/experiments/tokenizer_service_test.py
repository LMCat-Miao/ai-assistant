from app.services.tokenizer_service import count_tokens

texts = [
    "人工智能正在改变软件开发的方式。",
    "Artificial intelligence is changing software development.",
    "def hello(name):\n    return f'Hello, {name}'",
]

for text in texts:
    print("=" * 50)

    print("文本：")
    print(text)

    print("Token 数量：")
    print(count_tokens(text))