"""QQ 图片 URL 下载缓存。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ..core.logging import get_logger

logger = get_logger("ImageCacheStore")


class ImageCacheStore:
    """按 URL 下载并缓存图片，返回可直接给多模态模型使用的 data URL。"""

    def __init__(
        self,
        *,
        cache_dir: str | Path,
        ttl_seconds: int = 24 * 60 * 60,
        max_bytes: int = 2 * 1024 * 1024,
        timeout_seconds: int = 12,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.timeout_seconds = max(3, int(timeout_seconds))
        self._last_cleanup_at = 0.0

    async def resolve_for_model(self, url: str) -> str | None:
        """将图片 URL 解析成可复用的 data URL。"""
        normalized = str(url or "").strip()
        if not normalized:
            return None
        try:
            return await asyncio.to_thread(self._resolve_sync, normalized)
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片缓存解析失败，回退原始 URL: %s, err=%s", normalized, exc)
            return None

    def _resolve_sync(self, url: str) -> str:
        self._cleanup_expired_if_needed()
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        meta_path = self.cache_dir / f"{cache_key}.json"
        meta = self._load_meta(meta_path)
        now = time.time()

        if meta:
            data_path = self.cache_dir / str(meta.get("file_name") or "")
            saved_at = float(meta.get("saved_at") or 0)
            mime_type = str(meta.get("mime_type") or "").strip().lower()
            if now - saved_at <= self.ttl_seconds and data_path.exists():
                payload = data_path.read_bytes()
                if payload and len(payload) <= self.max_bytes:
                    return self._to_data_url(payload, mime_type or self._guess_mime(payload, url))

        payload, mime_type = self._download_image(url)
        extension = self._guess_extension(mime_type, url)
        file_name = f"{cache_key}{extension}"
        data_path = self.cache_dir / file_name
        data_path.write_bytes(payload)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "saved_at": now,
                    "size_bytes": len(payload),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return self._to_data_url(payload, mime_type)

    def _download_image(self, url: str) -> tuple[bytes, str]:
        request = Request(
            url=url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; QQCatBot/1.0)",
                "Accept": "image/*,*/*;q=0.8",
            },
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read(self.max_bytes + 1)
            if len(payload) > self.max_bytes:
                raise ValueError(f"图片过大，超过限制 {self.max_bytes} bytes")
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        mime_type = content_type if content_type.startswith("image/") else self._guess_mime(payload, url)
        if not mime_type.startswith("image/"):
            raise ValueError(f"非图片内容: content_type={content_type or 'unknown'}")
        return payload, mime_type

    @staticmethod
    def _load_meta(meta_path: Path) -> dict[str, Any] | None:
        if not meta_path.exists():
            return None
        try:
            raw = meta_path.read_text(encoding="utf-8").strip()
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _guess_mime(payload: bytes, url: str) -> str:
        if payload.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
            return "image/gif"
        if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
            return "image/webp"
        if payload.startswith(b"BM"):
            return "image/bmp"
        guessed, _ = mimetypes.guess_type(url)
        return str(guessed or "application/octet-stream").lower()

    @staticmethod
    def _guess_extension(mime_type: str, url: str) -> str:
        ext = mimetypes.guess_extension(mime_type or "", strict=False)
        if ext:
            return ext
        from_url = os.path.splitext(url.split("?", 1)[0])[1]
        return from_url if from_url else ".img"

    @staticmethod
    def _to_data_url(payload: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(payload).decode("ascii")
        safe_mime = mime_type if mime_type.startswith("image/") else "image/png"
        return f"data:{safe_mime};base64,{encoded}"

    def _cleanup_expired_if_needed(self) -> None:
        now = time.time()
        if now - self._last_cleanup_at < 300:
            return
        self._last_cleanup_at = now
        for meta_path in self.cache_dir.glob("*.json"):
            try:
                meta = self._load_meta(meta_path)
                if not meta:
                    meta_path.unlink(missing_ok=True)
                    continue
                saved_at = float(meta.get("saved_at") or 0)
                if now - saved_at <= self.ttl_seconds:
                    continue
                file_name = str(meta.get("file_name") or "")
                if file_name:
                    (self.cache_dir / file_name).unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                continue
