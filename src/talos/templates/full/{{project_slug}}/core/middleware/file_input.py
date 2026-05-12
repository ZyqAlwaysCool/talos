"""文件上传中间件 — 支持 multipart 和 base64 文件输入."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class FileInputMiddleware(BaseHTTPMiddleware):
    """将 base64 文件输入转换为 request.state.file_inputs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.file_inputs = []
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    data = json.loads(body)
                    request.state.file_inputs = self._extract_files(data)
                except Exception:
                    pass
        return await call_next(request)

    def _extract_files(self, data: Any) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith("file_") and isinstance(value, str):
                    files.append({"field": key, "base64": value})
        return files
