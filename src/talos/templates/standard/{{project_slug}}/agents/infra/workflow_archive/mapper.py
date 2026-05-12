from __future__ import annotations

from collections import defaultdict
from typing import Any

from loguru import logger

from agents.infra.workflow_archive.schemas import (
    WorkflowArchive,
    WorkflowArchiveNode,
    WorkflowArchiveRun,
)
from agents.infra.workflow_archive.view_schemas import (
    WorkflowNodeInfo,
    WorkflowTreeNodeInfo,
)


def load_workflow_archive(
    raw_archive: Any,
    *,
    task_id: str,
    agent_name: str = "",
    workflow_name: str = "",
) -> WorkflowArchive:
    if isinstance(raw_archive, WorkflowArchive):
        return raw_archive
    if isinstance(raw_archive, dict) and raw_archive:
        try:
            return WorkflowArchive(**raw_archive)
        except Exception as exc:
            logger.warning(
                "Invalid workflow archive payload. task_id={} error={}",
                task_id,
                str(exc),
            )
    return WorkflowArchive(
        task_id=task_id,
        agent_name=agent_name,
        workflow_name=workflow_name,
    )


def build_workflow_nodes_view(
    archive: WorkflowArchive,
    *,
    run_id: str = "",
) -> list[WorkflowNodeInfo]:
    """构建扁平节点视图（一维列表），用于前端按 parent_node_id 自行重建树。"""
    run = _pick_run(archive, run_id=run_id)
    if run is None:
        return []

    return [
        WorkflowNodeInfo(
            node_id=node.node_id,
            parent_node_id=node.parent_node_id,
            node_name=node.node_name,
            title=node.node_display_name or node.node_name,
            prompt_name=node.prompt_name,
            node_content=node.node_content,
            node_status=node.node_status,
            node_type=node.node_type,
            node_seq=node.node_seq,
            started_at=node.started_at,
            ended_at=node.ended_at,
            error_message=node.error_message,
        )
        for node in sorted(run.nodes, key=lambda item: int(item.node_seq))
    ]


def build_workflow_tree_view(
    archive: WorkflowArchive,
    *,
    run_id: str = "",
) -> list[WorkflowTreeNodeInfo]:
    run = _pick_run(archive, run_id=run_id)
    if run is None:
        return []

    node_map = {node.node_id: node for node in run.nodes}
    children_map = _build_children_map(run)
    roots = _pick_root_nodes(run, node_map=node_map)

    def _build_tree(node: WorkflowArchiveNode) -> WorkflowTreeNodeInfo:
        children = [_build_tree(child) for child in children_map.get(node.node_id, [])]
        return WorkflowTreeNodeInfo(
            node_id=node.node_id,
            parent_node_id=node.parent_node_id,
            node_name=node.node_name,
            title=node.node_display_name or node.node_name,
            prompt_name=node.prompt_name,
            node_content=node.node_content,
            node_status=node.node_status,
            node_type=node.node_type,
            node_seq=node.node_seq,
            started_at=node.started_at,
            ended_at=node.ended_at,
            error_message=node.error_message,
            sub_nodes=children,
        )

    return [_build_tree(root_node) for root_node in roots]


def _pick_run(archive: WorkflowArchive, *, run_id: str = "") -> WorkflowArchiveRun | None:
    if not archive.runs:
        return None
    if run_id:
        for run in archive.runs:
            if run.run_id == run_id:
                return run
    if archive.latest_run_id:
        for run in archive.runs:
            if run.run_id == archive.latest_run_id:
                return run
    return archive.runs[-1]


def _build_children_map(run: WorkflowArchiveRun) -> dict[str, list[WorkflowArchiveNode]]:
    children_map: dict[str, list[WorkflowArchiveNode]] = defaultdict(list)
    for node in run.nodes:
        children_map[node.parent_node_id].append(node)
    for children in children_map.values():
        children.sort(key=lambda item: int(item.node_seq))
    return children_map


def _pick_root_nodes(
    run: WorkflowArchiveRun,
    *,
    node_map: dict[str, WorkflowArchiveNode],
) -> list[WorkflowArchiveNode]:
    roots: list[WorkflowArchiveNode] = []
    for node in run.nodes:
        if node.parent_node_id == run.run_root_id:
            roots.append(node)
            continue
        if not node.parent_node_id:
            roots.append(node)
            continue
        if node.parent_node_id not in node_map:
            roots.append(node)
    roots.sort(key=lambda item: int(item.node_seq))
    return roots
