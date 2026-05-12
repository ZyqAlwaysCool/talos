"""文件相关数据模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """文件信息."""
    filename: str = Field(..., description="文件名")
    content: bytes | str = Field(..., description="文件内容")
    content_type: str = Field("application/octet-stream", description="内容类型")


class FileInput(BaseModel):
    """文件输入."""
    file_info: FileInfo | None = Field(None, description="文件信息")
    base64_content: str | None = Field(None, description="Base64编码的文件内容")
