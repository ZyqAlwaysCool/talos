"""text_processor Agent 数据模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextProcessorCreateRequest(BaseModel):
    """创建文本处理任务请求."""

    text: str = Field(
        ...,
        description="待处理的文本内容",
        examples=["Visit https://example.com for more info. Contact admin@test.com."],
    )
    options: dict = Field(
        default_factory=dict,
        description="可选的处理选项",
        examples=[{"language": "en", "max_summary_words": 50}],
    )


class TextProcessorQueryResponseData(BaseModel):
    """查询文本处理任务响应数据."""

    task_id: str = Field(..., description="任务ID")
    task_status: str = Field(..., description="任务状态")
    failed_reason: str = Field("", description="失败原因")
    result: dict = Field(default_factory=dict, description="处理结果")


    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "text_processor_20260512_test",
                    "task_status": "completed",
                    "failed_reason": "",
                    "result": {
                        "extracted": {
                            "word_count": 12,
                            "char_count": 75,
                            "entities": {"urls": ["https://example.com"], "emails": ["admin@test.com"]},
                        },
                        "summary": {
                            "preview": "Visit https://example.com for info.",
                            "total_words": 12,
                        },
                    },
                }
            ]
        }
    }
