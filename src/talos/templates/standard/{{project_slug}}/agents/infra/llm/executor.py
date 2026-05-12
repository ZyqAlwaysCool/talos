from __future__ import annotations

import asyncio
import itertools
import json
import os
from pathlib import Path
from typing import Any, TypeVar, cast

from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    ModelSettings,
    PartDeltaEvent,
    PartStartEvent,
    PromptedOutput,
    ThinkingPart,
    ThinkingPartDelta,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from agents.infra.llm.context import ThinkingContext
from agents.infra.llm.thinking.base import ThinkingSink
from agents.infra.llm.thinking.runtime import (
    ThinkingTraceRuntime,
    get_current_workflow_node_context,
)
from core.config.config_center import get_app_config

OutputT = TypeVar("OutputT")


def _load_prompt_sections(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    sections = {"system": "", "user": "", "output_schema": ""}
    current: str | None = None
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        header = line.strip().lower()
        if header == "# system":
            current = "system"
            continue
        if header == "# user":
            current = "user"
            continue
        if header == "# output_schema":
            current = "output_schema"
            continue
        if current:
            sections[current] += line + "\n"
    return {key: value.strip() for key, value in sections.items()}


def _render_template(text: str, variables: dict[str, Any]) -> str:
    rendered = text
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


def _format_prompt_debug_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        ordered_sections = ("system", "user", "output_schema")
        normalized_sections: list[str] = []
        for section_name in ordered_sections:
            section_content = content.get(section_name, "")
            if not isinstance(section_content, str):
                section_content = json.dumps(
                    section_content, ensure_ascii=False, indent=2
                )
            section_text = section_content.strip()
            if section_text:
                normalized_sections.append(f"# {section_name}\n{section_text}")
            else:
                normalized_sections.append(f"# {section_name}")
        return "\n\n".join(normalized_sections) + "\n"
    return str(content)


def _write_prompt_debug_file(filedir: str, filename: str, content: Any) -> None:
    # 输出完整的提示词内容到debug目录，方便调试和回放。仅在enable_file_write=true时启用，避免泄露敏感信息。
    config = get_app_config()
    if not config.enable_file_write:
        return
    os.makedirs(filedir, exist_ok=True)
    serialized_content = _format_prompt_debug_content(content)
    with open(file=f"{filedir}/{filename}", mode="w", encoding="utf-8") as file_obj:
        file_obj.write(serialized_content)


class LLMExecutor:
    def __init__(
        self,
        prompt_dir: Path,
        biz_name: str | None = None,
        thinking_sink: ThinkingSink | None = None,
        thinking_enabled: bool = False,
        thinking_context: ThinkingContext | None = None,
    ):
        self.prompt_dir = prompt_dir
        self.config = get_app_config()
        self.biz_name = biz_name
        self.model_name = self.config.resolve_llm_model(self.biz_name)
        self.thinking_sink = thinking_sink
        self.thinking_enabled = thinking_enabled
        self.thinking_context = thinking_context
        self.model = self._build_model()
        self.model_settings = self._build_model_settings()
        self.output_retries = self.config.llm_output_retries
        self._node_seq_counter = itertools.count(start=1)
        self._thinking_trace_runtime: ThinkingTraceRuntime | None = None
        logger.info(
            "init llm executor. provider={} biz_name={} model={} model_settings={} output_retries={} thinking_enabled={}",
            self.config.llm_provider,
            self.biz_name or "default",
            self.model.model_name,
            self.model_settings,
            self.output_retries,
            self.thinking_enabled,
        )

    def _build_model_settings(self) -> ModelSettings:
        settings: ModelSettings = {
            "temperature": self.config.llm_temperature,
            "max_tokens": self.config.llm_max_tokens,
            "timeout": self.config.llm_timeout,
        }
        extra_body: dict[str, Any] = dict(self.config.llm_extra_body or {})
        if self.thinking_enabled:
            # 开启thinking stream时，自动打开模型thinking能力，避免额外配置负担。
            extra_body["enable_thinking"] = True
        if extra_body:
            settings["extra_body"] = extra_body
        return settings

    def _is_model_thinking_mode(self) -> bool:
        extra_body = self.model_settings.get("extra_body")
        return bool(isinstance(extra_body, dict) and extra_body.get("enable_thinking"))

    def _resolve_agent_output_type(self, output_type: type[OutputT] | Any) -> Any:
        if isinstance(output_type, PromptedOutput):
            return output_type
        if self._is_model_thinking_mode():
            logger.info(
                "Thinking mode detected, using PromptedOutput to avoid tool_choice conflict."
            )
            return PromptedOutput(output_type)
        return output_type

    def _resolve_output_retries(self) -> int:
        if self._is_model_thinking_mode():
            # thinking模式下若结构化校验失败会触发整轮重试，耗时很高；默认关闭重试避免卡住。
            return 0
        return self.output_retries

    @staticmethod
    def _normalize_per_call_output_retries(value: int) -> int:
        # pydantic-ai 使用非负整数作为 output 校验重试上限。
        return max(0, int(value))

    def _build_model(self) -> OpenAIChatModel:
        if self.config.llm_provider == "openai":
            provider = OpenAIProvider(
                api_key=self.config.llm_api_key,
                base_url=self.config.llm_base_url,
            )
        else:
            provider = AlibabaProvider(
                api_key=self.config.llm_api_key,
                base_url=self.config.llm_base_url,
            )
        return OpenAIChatModel(self.model_name, provider=provider)

    def set_thinking_trace_runtime(
        self,
        runtime: ThinkingTraceRuntime | None,
    ) -> None:
        self._thinking_trace_runtime = runtime

    def _resolve_thinking_trace_runtime(
        self,
        *,
        base_context: ThinkingContext,
    ) -> ThinkingTraceRuntime | None:
        if self._thinking_trace_runtime is not None:
            return self._thinking_trace_runtime
        if self.thinking_sink is None:
            return None
        # 兜底：允许LLMExecutor独立运行时仍能输出thinking事件。
        logger.warning("init new thinking trace runtime for thinking sink. should not happen.")
        return ThinkingTraceRuntime(
            sink=self.thinking_sink,
            base_context=base_context,
        )

    def _build_node_thinking_context(
        self,
        *,
        prompt_name: str,
        base_context: ThinkingContext,
        trace_runtime: ThinkingTraceRuntime | None,
    ) -> ThinkingContext:
        prompt_context = base_context.with_prompt(prompt_name)
        fallback_display = (
            prompt_context.node_display_name or prompt_context.node_name or prompt_name
        )
        active_workflow = get_current_workflow_node_context()
        # LLM 节点归档/SSE 展示名优先继承外层 workflow 中文名，并追加英文 prompt 键区分同节点多轮调用。
        workflow_title = (
            str(active_workflow.node_display_name).strip()
            if active_workflow is not None
            else ""
        )
        if workflow_title:
            llm_display_name = f"{workflow_title}-{prompt_name}"
        else:
            llm_display_name = fallback_display

        if isinstance(trace_runtime, ThinkingTraceRuntime):
            parent_node_exec_id = (
                active_workflow.node_exec_id
                if active_workflow is not None
                and active_workflow.node_exec_id
                else prompt_context.parent_node_exec_id
            )
            return trace_runtime.build_node_context(
                node_name=prompt_context.node_name or prompt_name,
                node_display_name=llm_display_name,
                prompt_name=prompt_name,
                node_type="llm",
                parent_node_exec_id=parent_node_exec_id,
            )
        run_id = prompt_context.run_id or prompt_context.task_id or "run"
        node_seq = next(self._node_seq_counter)
        node_exec_id = f"{run_id}:node:{node_seq}"
        parent_node_exec_id = prompt_context.parent_node_exec_id or f"{run_id}:root"
        return prompt_context.with_node_span(
            node_exec_id=node_exec_id,
            parent_node_exec_id=parent_node_exec_id,
            node_seq=node_seq,
            node_type="llm",
            node_display_name=llm_display_name,
        )

    def _prepare_prompt_content(
        self,
        *,
        prompt_name: str,
        variables: dict[str, Any],
    ) -> tuple[str, str]:
        prompt_path = self.prompt_dir / f"{prompt_name}.md"
        sections = _load_prompt_sections(prompt_path)
        system_prompt = _render_template(sections.get("system", ""), variables)
        user_prompt = _render_template(sections.get("user", ""), variables)
        output_schema_prompt = _render_template(
            sections.get("output_schema", ""), variables
        )
        _write_prompt_debug_file(
            "./debug",
            f"{prompt_name}.md",
            {
                "system": system_prompt,
                "user": user_prompt,
                "output_schema": output_schema_prompt,
            },
        )
        return system_prompt, user_prompt

    def _resolve_effective_output_retries(
        self, *, per_call_output_retries: int | None = None
    ) -> int:
        if per_call_output_retries is not None:
            effective = self._normalize_per_call_output_retries(per_call_output_retries)
            logger.info(
                "Per-call output_retries={} prompt_run (thinking_mode={}). global_llm_output_retries={}",
                effective,
                self._is_model_thinking_mode(),
                self.output_retries,
            )
            return effective
        effective_output_retries = self._resolve_output_retries()
        if effective_output_retries != self.output_retries:
            logger.info(
                "Override output_retries for thinking mode. original={} effective={}",
                self.output_retries,
                effective_output_retries,
            )
        return effective_output_retries

    def _build_agent(
        self,
        *,
        system_prompt: str,
        output_type: type[OutputT],
        output_retries: int,
    ) -> Agent:
        return Agent(
            model=self.model,
            output_type=self._resolve_agent_output_type(output_type),
            system_prompt=system_prompt,
            model_settings=self.model_settings,
            output_retries=output_retries,
        )

    async def _run_blocking_mode(
        self,
        *,
        agent: Agent,
        user_prompt: str,
        prompt_name: str,
    ) -> Any:
        # 阻塞模式：维持原始 agent.run 行为，不输出中间thinking事件。
        result = await agent.run(user_prompt)
        logger.debug(
            "LLM prompt executed: {} call model: {}",
            prompt_name,
            self.model.model_name,
        )
        return result.output

    async def _emit_node_start(
        self,
        *,
        trace_runtime: ThinkingTraceRuntime,
        run_context: ThinkingContext,
    ) -> bool:
        return await trace_runtime.safe_sink_call(
            "on_node_start",
            run_context,
        )

    async def _emit_node_error(
        self,
        *,
        trace_runtime: ThinkingTraceRuntime,
        run_context: ThinkingContext,
        error_message: str,
        sink_available: bool,
    ) -> None:
        if not sink_available:
            return
        await trace_runtime.safe_sink_call(
            "on_node_error",
            run_context,
            error_message,
        )

    async def _emit_node_end(
        self,
        *,
        trace_runtime: ThinkingTraceRuntime,
        run_context: ThinkingContext,
        sink_available: bool,
    ) -> None:
        if not sink_available:
            return
        await trace_runtime.safe_sink_call(
            "on_node_end",
            run_context,
        )

    async def _collect_stream_output(
        self,
        *,
        agent: Agent,
        user_prompt: str,
        prompt_name: str,
        run_context: ThinkingContext,
        trace_runtime: ThinkingTraceRuntime,
        sink_available: bool,
    ) -> tuple[Any, bool]:
        first_chunk_received = False
        sink_state = sink_available

        # 流式模式：逐条消费官方事件流，抽取ThinkingPart增量即时写入sink。
        async for event in agent.run_stream_events(user_prompt):
            if isinstance(event, AgentRunResultEvent):
                return event.result.output, sink_state

            thinking_delta = self._extract_thinking_delta_from_event(event)
            if not thinking_delta:
                continue
            if not first_chunk_received:
                first_chunk_received = True
                logger.info(
                    "Thinking stream node first chunk received. task_id={} run_id={} node_exec_id={} prompt={}",
                    run_context.task_id,
                    run_context.run_id,
                    run_context.node_exec_id,
                    prompt_name,
                )
            if sink_state:
                sink_state = await trace_runtime.safe_sink_call(
                    "on_node_delta",
                    run_context,
                    thinking_delta,
                )
        raise RuntimeError("No AgentRunResultEvent received from run_stream_events")

    async def _run_thinking_stream_mode(
        self,
        *,
        agent: Agent,
        user_prompt: str,
        prompt_name: str,
        thinking_context: ThinkingContext | None,
    ) -> Any:
        base_context = thinking_context or self.thinking_context or ThinkingContext()
        trace_runtime = self._resolve_thinking_trace_runtime(base_context=base_context)
        if trace_runtime is None:
            raise RuntimeError("Thinking trace runtime is required in thinking mode")

        run_context = self._build_node_thinking_context(
            prompt_name=prompt_name,
            base_context=base_context,
            trace_runtime=trace_runtime,
        )
        stream_timeout_seconds = max(int(self.config.llm_timeout) + 15, 60)
        logger.info(
            "Thinking stream node run begin. task_id={} run_id={} attempt={} node_exec_id={} prompt={} timeout={}s",
            run_context.task_id,
            run_context.run_id,
            run_context.attempt,
            run_context.node_exec_id,
            prompt_name,
            stream_timeout_seconds,
        )

        sink_available = await self._emit_node_start(
            trace_runtime=trace_runtime,
            run_context=run_context,
        )
        try:
            output, sink_available = await asyncio.wait_for(
                self._collect_stream_output(
                    agent=agent,
                    user_prompt=user_prompt,
                    prompt_name=prompt_name,
                    run_context=run_context,
                    trace_runtime=trace_runtime,
                    sink_available=sink_available,
                ),
                timeout=stream_timeout_seconds,
            )
        except Exception as exc:
            await self._emit_node_error(
                trace_runtime=trace_runtime,
                run_context=run_context,
                error_message=str(exc),
                sink_available=sink_available,
            )
            raise

        await self._emit_node_end(
            trace_runtime=trace_runtime,
            run_context=run_context,
            sink_available=sink_available,
        )
        logger.info(
            "LLM prompt executed with thinking stream: task_id={} run_id={} node_exec_id={} prompt={} model={}",
            run_context.task_id,
            run_context.run_id,
            run_context.node_exec_id,
            prompt_name,
            self.model.model_name,
        )
        return output

    async def run(
        self,
        prompt_name: str,
        variables: dict[str, Any],
        output_type: type[OutputT],
        *,
        thinking_context: ThinkingContext | None = None,
        output_retries: int | None = None,
    ) -> OutputT:
        # run负责总流程编排：准备提示词 -> 创建agent -> 分发阻塞/流式两种执行模式。
        # output_retries: 单次调用的结构化输出校验重试次数；None 表示沿用全局规则（thinking 下默认为 0）。

        # 准备提示词
        system_prompt, user_prompt = self._prepare_prompt_content(
            prompt_name=prompt_name,
            variables=variables,
        )
        effective_output_retries = self._resolve_effective_output_retries(
            per_call_output_retries=output_retries,
        )

        # 构建agent
        agent = self._build_agent(
            system_prompt=system_prompt,
            output_retries=effective_output_retries,
            output_type=output_type,
        )

        # 确认执行模式
        if not self.thinking_enabled or self.thinking_sink is None:
            return cast(
                OutputT,
                await self._run_blocking_mode(
                    agent=agent,
                    user_prompt=user_prompt,
                    prompt_name=prompt_name,
                ),
            )

        return cast(
            OutputT,
            await self._run_thinking_stream_mode(
                agent=agent,
                user_prompt=user_prompt,
                prompt_name=prompt_name,
                thinking_context=thinking_context,
            ),
        )

    @staticmethod
    def _extract_thinking_delta_from_event(event: Any) -> str:
        if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
            return event.part.content or ""
        if isinstance(event, PartDeltaEvent) and isinstance(
            event.delta, ThinkingPartDelta
        ):
            return event.delta.content_delta or ""
        return ""
