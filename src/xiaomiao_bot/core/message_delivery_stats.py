"""Message delivery statistics for send audit logs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MessageDeliveryStats:
    chunk_count: int
    total_chars: int
    max_chunk_chars: int


def build_message_delivery_stats(messages: Sequence[Any]) -> MessageDeliveryStats:
    lengths = [len(str(message)) for message in messages]
    return MessageDeliveryStats(
        chunk_count=len(lengths),
        total_chars=sum(lengths),
        max_chunk_chars=max(lengths, default=0),
    )
