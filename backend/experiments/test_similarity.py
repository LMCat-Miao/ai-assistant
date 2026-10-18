from app.rag.similarity import cosine_similarity

vector_a = [1, 0]

vector_b = [1, 0]

vector_c = [0, 1]

vector_d = [-1, 0]


print("A 和 B：")
print(cosine_similarity(vector_a, vector_b))

print("\nA 和 C：")
print(cosine_similarity(vector_a, vector_c))

print("\nA 和 D：")
print(cosine_similarity(vector_a, vector_d))