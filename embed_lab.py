"""Embeddings mini-lab: watch meaning turn into numbers, then into similarity.

Run it:  python embed_lab.py
"""
from chromadb.utils import embedding_functions
import numpy as np

# A pre-trained embedding model (downloads once, then runs locally & free).
embed = embedding_functions.DefaultEmbeddingFunction()

phrases = [
    "who is the strongest avenger?",   # <-- the "question" we compare against
    "thor is the most muscular avenger",     # related in MEANING (different words!)
    "antman is the smallest avenger",     # also loan-related
    "steve rogers is the oldest avenger",      # unrelated
    "hulk is the biggest avenger",               # unrelated
    "iron man is dead",               # unrelated
]

# Turn each phrase into a vector (a list of numbers).
vectors = embed(phrases)

print("Each phrase became a vector of", len(vectors[0]), "numbers.\n")
print("First 8 numbers of the question's vector:")
print(np.round(vectors[0][:8], 3), "...\n")


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return a.dot(b) / (np.linalg.norm(a) * np.linalg.norm(b))


query = phrases[0]
print(f'Comparing everything to:  "{query}"')
print("(1.0 = identical meaning, 0 = unrelated)\n")

scores = []
for i in range(1, len(phrases)):
    score = cosine_similarity(vectors[0], vectors[i])
    scores.append((score, phrases[i]))

# Show most-similar first.
for score, phrase in sorted(scores, reverse=True):
    print(f"  {score:.3f}   {phrase}")
