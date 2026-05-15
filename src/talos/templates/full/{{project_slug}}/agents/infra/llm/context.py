from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ThinkingContext:
    task_id: str = ""
    agent_name: str = ""
    workflow_name: str = ""
    node_name: str = ""
    node_display_name: str = ""
    prompt_name: str = ""
    trace_id: str = ""
    run_id: str = ""
    attempt: int = 1
    node_exec_id: str = ""
    parent_node_exec_id: str = ""
    node_seq: int = 0
    node_type: str = ""

    def with_prompt(self, prompt_name: str) -> ThinkingContext:
        node_name = self.node_name or prompt_name
        node_display_name = self.node_display_name or prompt_name
        return ThinkingContext(
            task_id=self.task_id,
            agent_name=self.agent_name,
            workflow_name=self.workflow_name,
            node_name=node_name,
            node_display_name=node_display_name,
            prompt_name=prompt_name,
            trace_id=self.trace_id,
            run_id=self.run_id,
            attempt=self.attempt,
            node_exec_id=self.node_exec_id,
            parent_node_exec_id=self.parent_node_exec_id,
            node_seq=self.node_seq,
            node_type=self.node_type,
        )

    def with_node_span(
        self,
        *,
        node_exec_id: str,
        parent_node_exec_id: str,
        node_seq: int,
        node_type: str | None = None,
        node_display_name: str | None = None,
    ) -> ThinkingContext:
        return ThinkingContext(
            task_id=self.task_id,
            agent_name=self.agent_name,
            workflow_name=self.workflow_name,
            node_name=self.node_name,
            node_display_name=(
                self.node_display_name
                if node_display_name is None
                else node_display_name
            ),
            prompt_name=self.prompt_name,
            trace_id=self.trace_id,
            run_id=self.run_id,
            attempt=self.attempt,
            node_exec_id=node_exec_id,
            parent_node_exec_id=parent_node_exec_id,
            node_seq=node_seq,
            node_type=self.node_type if node_type is None else node_type,
        )
