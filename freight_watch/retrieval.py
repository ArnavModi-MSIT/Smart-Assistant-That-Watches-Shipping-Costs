"""Small, auditable TF-IDF vector index; no external database for ten notes."""

from collections import Counter
import math
import re


def tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    # Bigrams retain route names, so Chennai-Bangalore is more than two cities.
    return words + [a + "_" + b for a, b in zip(words, words[1:])]


class NoteIndex:
    def __init__(self, notes):
        self.notes = sorted(notes, key=lambda n: n.note_id)
        docs = [tokens(n.applies_to + " " + n.text) for n in self.notes]
        frequency = Counter(term for doc in docs for term in set(doc))
        self.idf = {term: math.log((1 + len(docs)) / (1 + count)) + 1 for term, count in frequency.items()}
        self.vectors = [self.vector(doc) for doc in docs]

    def vector(self, terms):
        counts = Counter(terms)
        vector = {term: (1 + math.log(count)) * self.idf[term]
                  for term, count in counts.items() if term in self.idf}
        norm = math.sqrt(sum(v * v for v in vector.values()))
        return {term: value / norm for term, value in vector.items()} if norm else {}

    def search(self, query):
        vector = self.vector(tokens(query))
        scored = [(note, sum(value * stored.get(term, 0) for term, value in vector.items()))
                  for note, stored in zip(self.notes, self.vectors)]
        return sorted(scored, key=lambda pair: (-pair[1], pair[0].note_id))
