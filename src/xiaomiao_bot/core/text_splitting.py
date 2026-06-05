"""Text splitting helpers for downstream message limits."""

from __future__ import annotations

import re


def split_text_chunks(text: str, *, max_chars: int) -> list[str]:
    """Split text into chunks without losing content."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    for token in re.split(r"(\n+)", text):
        if not token:
            continue
        while token:
            remaining = max_chars - len(current)
            if len(token) <= remaining:
                current += token
                token = ""
                continue
            if current:
                chunks.append(current)
                current = ""
                continue
            chunks.append(token[:max_chars])
            token = token[max_chars:]

    if current:
        chunks.append(current)
    return chunks
