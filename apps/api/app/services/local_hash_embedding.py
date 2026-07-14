import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class LocalHashEmbedding:
    """A deterministic lexical vector baseline for local development and tests."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            index, sign = self._bucket(token)
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def _bucket(self, token: str) -> tuple[int, int]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, byteorder="big")
        return number % self.dimension, 1 if number & 1 else -1
