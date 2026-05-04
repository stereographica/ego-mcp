from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import Counter, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast

import chromadb
import networkx as nx
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ego_dashboard.desire_catalog import load_desire_catalog
from ego_dashboard.ingestor import tail_jsonl_file
from ego_dashboard.settings import DashboardSettings, load_settings
from ego_dashboard.sql_store import SqlTelemetryStore
from ego_dashboard.store import TelemetryStore

_MEMORY_NETWORK_BATCH_SIZE = 512
logger = logging.getLogger(__name__)


class StoreProtocol(Protocol):
    def tool_usage(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def metric_history(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def string_timeline(self, key: str, start: datetime, end: datetime) -> list[dict[str, str]]: ...

    def string_heatmap(
        self, key: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def logs(
        self,
        start: datetime,
        end: datetime,
        level: str | None = None,
        *,
        search: str | None = None,
    ) -> list[dict[str, object]]: ...

    def anomaly_alerts(
        self, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def current(self) -> dict[str, object]: ...

    def notion_history(
        self, notion_id: str, start: datetime, end: datetime, bucket: str
    ) -> list[dict[str, object]]: ...

    def desire_metric_keys(self, start: datetime, end: datetime) -> list[str]: ...

    def surface_timeline(self, start: datetime, end: datetime) -> list[dict[str, str]]: ...

    def relationship_detail(
        self, person_id: str, start: datetime, end: datetime
    ) -> dict[str, object]: ...


class _MemoryLinkPayload(TypedDict):
    target_id: str
    link_type: str
    confidence: float
    note: str


class _GraphMetrics(TypedDict):
    degree: dict[object, int]
    betweenness: dict[object, float]


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _clamp_float(value: object, default: float = 0.0) -> float:
    parsed = _coerce_float(value, default)
    return max(0.0, min(1.0, parsed))


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_bool(value: object) -> bool:
    return value in (True, 1, "1", "true", "True")


def _memory_label(document: object, metadata: object, *, limit: int = 72) -> str | None:
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    private_raw = metadata_dict.get("is_private") if isinstance(metadata_dict, dict) else False
    if _coerce_bool(private_raw):
        return "REDACTED"
    if not isinstance(document, str):
        return None
    compact = " ".join(document.split()).strip()
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _memory_content_preview(
    document: object,
    metadata: object,
    *,
    limit: int = 80,
) -> str | None:
    return _memory_label(document, metadata, limit=limit)


def _coerce_tags(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, list):
        candidates = [item for item in value if isinstance(item, str)]
    else:
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        tag = candidate.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _calculate_memory_decay(
    timestamp: object,
    *,
    link_confidence_max: float = 0.0,
    access_count: int = 0,
    now: datetime | None = None,
) -> float:
    memory_time = _parse_iso_timestamp(timestamp)
    if memory_time is None:
        return 1.0

    current = now or datetime.now(tz=UTC)
    age_seconds = (current - memory_time).total_seconds()
    if age_seconds < 0:
        return 1.0

    age_days = age_seconds / 86400
    access_bonus = min(max(access_count, 0) * 5, 60)
    effective_half_life = (30.0 + access_bonus) * (1.0 + _clamp_float(link_confidence_max) * 0.5)
    return max(0.0, min(1.0, 2 ** (-age_days / max(effective_half_life, 1e-6))))


def _load_link_metadata(value: object) -> list[_MemoryLinkPayload]:
    if not isinstance(value, str) or not value:
        return []
    try:
        payload = json.loads(value)
    except TypeError, json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []

    links: list[_MemoryLinkPayload] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            continue
        link_type = item.get("link_type")
        links.append(
            {
                "target_id": target_id,
                "link_type": link_type if isinstance(link_type, str) and link_type else "related",
                "confidence": _clamp_float(item.get("confidence"), 0.5),
                "note": str(item.get("note", "")),
            }
        )
    return links


def _is_valid_meta_field(value: object) -> bool:
    """Check whether a meta_field entry matches the expected union shape."""
    if not isinstance(value, dict):
        return False
    field_type = value.get("type")
    if field_type not in ("text", "file_path", "notion_ids"):
        return False
    if field_type == "text":
        return isinstance(value.get("value"), str)
    if field_type == "file_path":
        return isinstance(value.get("path"), str)
    if field_type == "notion_ids":
        ids = value.get("notion_ids")
        return isinstance(ids, list) and all(isinstance(i, str) for i in ids)
    return False


def _sanitize_meta_fields(raw: dict[str, object]) -> dict[str, object]:
    """Filter out malformed meta_field entries."""
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and _is_valid_meta_field(value)
    }


def _load_notion_rows(settings: DashboardSettings) -> list[dict[str, object]]:
    if not settings.ego_mcp_data_dir:
        return []
    notion_path = Path(settings.ego_mcp_data_dir) / "notions.json"
    if not notion_path.exists():
        return []
    try:
        payload = json.loads(notion_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return []
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, object]] = []
    for notion_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        source_ids = [
            memory_id
            for memory_id in raw.get("source_memory_ids", [])
            if isinstance(memory_id, str) and memory_id
        ]
        related_ids = [
            related_notion_id
            for related_notion_id in raw.get("related_notion_ids", [])
            if isinstance(related_notion_id, str) and related_notion_id
        ]
        reinforcement_count = _coerce_int(raw.get("reinforcement_count"), 0)
        person_id = raw.get("person_id")
        confidence = float(raw.get("confidence", 0.5))
        meta_fields = _sanitize_meta_fields(raw.get("meta_fields", {}))
        rows.append(
            {
                "id": str(notion_id),
                "label": str(raw.get("label", "")),
                "emotion_tone": str(raw.get("emotion_tone", "neutral")),
                "confidence": confidence,
                "source_count": len(source_ids),
                "source_memory_ids": source_ids,
                "related_notion_ids": related_ids,
                "related_count": len(related_ids),
                "reinforcement_count": reinforcement_count,
                "person_id": str(person_id) if isinstance(person_id, str) else "",
                "is_conviction": confidence >= 0.7 and reinforcement_count >= 5,
                "created": str(raw.get("created", "")),
                "last_reinforced": str(raw.get("last_reinforced", "")),
                "tags": _coerce_tags(raw.get("tags", [])),
                "meta_fields": meta_fields,
            }
        )
    rows.sort(key=lambda row: str(row.get("created", "")), reverse=True)
    return rows


def _load_memory_rows(settings: DashboardSettings) -> list[dict[str, object]]:
    if not settings.ego_mcp_data_dir:
        return []

    chroma_dir = Path(settings.ego_mcp_data_dir) / "chroma"
    if not chroma_dir.exists():
        logger.warning(
            "Memory network skipped because Chroma directory does not exist: %s", chroma_dir
        )
        return []

    rows: list[dict[str, object]] = []
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name="ego_memories")
        offset = 0
        while True:
            batch = collection.get(
                limit=_MEMORY_NETWORK_BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas"],
            )

            ids = batch.get("ids", [])
            documents = batch.get("documents", [])
            metadatas = batch.get("metadatas", [])
            if not isinstance(ids, list) or not ids:
                break

            document_rows = documents if isinstance(documents, list) else []
            metadata_rows = metadatas if isinstance(metadatas, list) else []
            for index, memory_id in enumerate(ids):
                if not isinstance(memory_id, str):
                    continue
                document = document_rows[index] if index < len(document_rows) else None
                metadata = metadata_rows[index] if index < len(metadata_rows) else {}
                if not isinstance(metadata, dict):
                    continue
                linked_ids = _load_link_metadata(metadata.get("linked_ids"))
                max_confidence = max((link["confidence"] for link in linked_ids), default=0.0)
                access_count = _coerce_int(metadata.get("access_count"), 0)
                category = metadata.get("category")
                rows.append(
                    {
                        "id": memory_id,
                        "content": document if isinstance(document, str) else "",
                        "label": _memory_label(document, metadata),
                        "content_preview": _memory_content_preview(document, metadata),
                        "category": (
                            str(category) if isinstance(category, str) and category else "daily"
                        ),
                        "timestamp": (
                            str(metadata.get("timestamp"))
                            if isinstance(metadata.get("timestamp"), str)
                            else ""
                        ),
                        "decay": _calculate_memory_decay(
                            metadata.get("timestamp"),
                            link_confidence_max=max_confidence,
                            access_count=access_count,
                        ),
                        "access_count": access_count,
                        "importance": max(1, min(5, _coerce_int(metadata.get("importance"), 3))),
                        "tags": _coerce_tags(metadata.get("tags")),
                        "is_private": _coerce_bool(metadata.get("is_private")),
                        "last_accessed": (
                            str(metadata.get("last_accessed"))
                            if isinstance(metadata.get("last_accessed"), str)
                            else ""
                        ),
                        "emotional_valence": _coerce_float(metadata.get("valence"), 0.0),
                        "emotional_arousal": _clamp_float(metadata.get("arousal"), 0.5),
                        "emotional_intensity": _clamp_float(metadata.get("intensity"), 0.5),
                        "linked_ids": linked_ids,
                    }
                )

            if len(ids) < _MEMORY_NETWORK_BATCH_SIZE:
                break
            offset += len(ids)
    except Exception:
        logger.exception("Failed to load memory nodes for Memory Network from %s", chroma_dir)
    return rows


def _edge_identity(source: str, target: str, link_type: str) -> tuple[str, str, str]:
    normalized_type = link_type.strip().lower() or "related"
    if normalized_type in {"related", "similar", "notion_related"}:
        ordered_source, ordered_target = sorted((source, target))
        return ordered_source, ordered_target, normalized_type
    return source, target, normalized_type


def _build_network_edges(
    memory_rows: list[dict[str, object]],
    notion_rows: list[dict[str, object]],
    node_ids: set[str],
) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for memory in memory_rows:
        source_id = str(memory["id"])
        linked_ids = memory.get("linked_ids", [])
        if not isinstance(linked_ids, list):
            continue
        for link in linked_ids:
            if not isinstance(link, dict):
                continue
            target_id = str(link.get("target_id", ""))
            link_type = str(link.get("link_type", "related"))
            if not target_id or source_id not in node_ids or target_id not in node_ids:
                continue
            edge_key = _edge_identity(source_id, target_id, link_type)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "link_type": link_type,
                    "confidence": _clamp_float(link.get("confidence"), 0.5),
                }
            )

    for notion in notion_rows:
        notion_id = str(notion["id"])
        source_memory_ids = notion.get("source_memory_ids", [])
        if isinstance(source_memory_ids, list):
            for source_memory_id in source_memory_ids:
                if not isinstance(source_memory_id, str):
                    continue
                if source_memory_id not in node_ids or notion_id not in node_ids:
                    continue
                edge_key = _edge_identity(source_memory_id, notion_id, "notion_source")
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append(
                    {
                        "source": source_memory_id,
                        "target": notion_id,
                        "link_type": "notion_source",
                        "confidence": _clamp_float(notion.get("confidence"), 0.5),
                    }
                )

        related_notion_ids = notion.get("related_notion_ids", [])
        if not isinstance(related_notion_ids, list):
            continue
        for related_notion_id in related_notion_ids:
            if not isinstance(related_notion_id, str):
                continue
            if related_notion_id not in node_ids or notion_id not in node_ids:
                continue
            edge_key = _edge_identity(notion_id, related_notion_id, "notion_related")
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append(
                {
                    "source": notion_id,
                    "target": related_notion_id,
                    "link_type": "notion_related",
                    "confidence": _clamp_float(notion.get("confidence"), 0.5),
                }
            )

        # Add edges from meta_fields notion_ids
        meta_fields = notion.get("meta_fields", {})
        if not isinstance(meta_fields, dict):
            continue
        for key, meta_field in meta_fields.items():
            if not isinstance(meta_field, dict):
                continue
            if meta_field.get("type") != "notion_ids":
                continue
            for target_id in meta_field.get("notion_ids", []):
                if not isinstance(target_id, str):
                    continue
                if target_id == notion_id:
                    continue
                if target_id not in node_ids or notion_id not in node_ids:
                    continue
                edge_key = _edge_identity(notion_id, target_id, "meta_notion_link")
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append(
                    {
                        "source": notion_id,
                        "target": target_id,
                        "link_type": "meta_notion_link",
                        "confidence": _clamp_float(notion.get("confidence"), 0.5),
                    }
                )
    return edges


def _build_graph(node_ids: set[str], edges: list[dict[str, object]]) -> nx.Graph[str]:
    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(node_ids)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        graph.add_edge(source, target, weight=_clamp_float(edge.get("confidence"), 0.5))
    return graph


def _compute_graph_metrics(graph: nx.Graph[Any]) -> dict[str, dict[str, int] | dict[str, float]]:
    degree: dict[str, int] = {str(node_id): int(value) for node_id, value in graph.degree()}
    if graph.number_of_nodes() <= 500:
        betweenness_raw = nx.betweenness_centrality(graph, normalized=True)
    else:
        betweenness_raw = nx.betweenness_centrality(graph, k=100, normalized=True)
    betweenness = {str(node_id): float(value) for node_id, value in betweenness_raw.items()}
    return {"degree": degree, "betweenness": betweenness}


def _build_memory_network_stats(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    graph: nx.Graph[Any],
) -> dict[str, object]:
    memory_nodes = [node for node in nodes if node.get("is_notion") is not True]
    notion_nodes = [node for node in nodes if node.get("is_notion") is True]
    conviction_count = sum(1 for node in notion_nodes if node.get("is_conviction") is True)
    avg_memory_decay = (
        sum(_coerce_float(node.get("decay"), 0.0) for node in memory_nodes) / len(memory_nodes)
        if memory_nodes
        else 0.0
    )

    top_hub_id: str | None = None
    top_hub_degree = 0
    if nodes:
        top_hub_degree_neg, top_hub_key = min(
            (-_coerce_int(node.get("degree"), 0), str(node["id"])) for node in nodes
        )
        top_hub_id = top_hub_key
        top_hub_degree = -top_hub_degree_neg

    category_counts = Counter(str(node.get("category", "")) for node in memory_nodes)
    category_counts.pop("", None)
    if category_counts:
        top_category_name = min((-count, category) for category, count in category_counts.items())[
            1
        ]
        top_category_ratio = category_counts[top_category_name] / len(memory_nodes)
    else:
        top_category_name = None
        top_category_ratio = 0.0

    return {
        "node_count": len(nodes),
        "memory_count": len(memory_nodes),
        "notion_count": len(notion_nodes),
        "edge_count": len(edges),
        "conviction_count": conviction_count,
        "avg_memory_decay": avg_memory_decay,
        "graph_density": float(nx.density(graph)) if graph.number_of_nodes() > 1 else 0.0,
        "top_hub_id": top_hub_id,
        "top_hub_degree": top_hub_degree,
        "top_category": top_category_name,
        "top_category_ratio": top_category_ratio,
    }


def _build_memory_network(
    memory_rows: list[dict[str, object]],
    notion_rows: list[dict[str, object]],
) -> dict[str, object]:
    node_ids = {
        str(row["id"])
        for row in [*memory_rows, *notion_rows]
        if isinstance(row.get("id"), str) and row.get("id")
    }
    edges = _build_network_edges(memory_rows, notion_rows, node_ids)
    graph = _build_graph(node_ids, edges)
    metrics = _compute_graph_metrics(graph)
    degree = cast(dict[str, int], metrics["degree"])
    betweenness = cast(dict[str, float], metrics["betweenness"])

    nodes: list[dict[str, object]] = []
    for memory in memory_rows:
        memory_id = str(memory["id"])
        nodes.append(
            {
                "id": memory_id,
                "label": memory.get("label"),
                "category": memory.get("category"),
                "is_notion": False,
                "content_preview": memory.get("content_preview"),
                "importance": memory.get("importance"),
                "tags": memory.get("tags", []),
                "is_private": memory.get("is_private", False),
                "confidence": None,
                "access_count": memory.get("access_count"),
                "decay": memory.get("decay"),
                "reinforcement_count": None,
                "person_id": None,
                "related_count": None,
                "is_conviction": False,
                "source_count": None,
                "degree": degree.get(memory_id, 0),
                "betweenness": betweenness.get(memory_id, 0.0),
                "emotional_valence": memory.get("emotional_valence"),
                "emotional_arousal": memory.get("emotional_arousal"),
                "last_accessed": memory.get("last_accessed") or None,
                "created": None,
                "last_reinforced": None,
            }
        )

    for notion in notion_rows:
        notion_id = str(notion["id"])
        nodes.append(
            {
                "id": notion_id,
                "label": notion.get("label"),
                "category": "notion",
                "is_notion": True,
                "content_preview": None,
                "importance": None,
                "tags": notion.get("tags", []),
                "is_private": False,
                "confidence": notion.get("confidence"),
                "emotion_tone": notion.get("emotion_tone"),
                "access_count": None,
                "decay": None,
                "reinforcement_count": notion.get("reinforcement_count"),
                "person_id": notion.get("person_id"),
                "related_count": notion.get("related_count"),
                "is_conviction": notion.get("is_conviction", False),
                "source_count": notion.get("source_count"),
                "degree": degree.get(notion_id, 0),
                "betweenness": betweenness.get(notion_id, 0.0),
                "emotional_valence": None,
                "emotional_arousal": None,
                "last_accessed": None,
                "created": notion.get("created") or None,
                "last_reinforced": notion.get("last_reinforced") or None,
                "meta_fields": notion.get("meta_fields"),
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": _build_memory_network_stats(nodes, edges, graph),
    }


def _load_memory_network(settings: DashboardSettings) -> dict[str, object]:
    return _build_memory_network(_load_memory_rows(settings), _load_notion_rows(settings))


def _load_memory_detail(settings: DashboardSettings, memory_id: str) -> dict[str, object] | None:
    memory = next(
        (row for row in _load_memory_rows(settings) if str(row.get("id", "")) == memory_id),
        None,
    )
    if memory is None:
        return None

    generated_notion_ids: list[str] = []
    for notion in _load_notion_rows(settings):
        source_memory_ids = notion.get("source_memory_ids")
        if not isinstance(source_memory_ids, list):
            continue
        if memory_id in source_memory_ids:
            generated_notion_ids.append(str(notion["id"]))
    is_private = bool(memory.get("is_private", False))
    return {
        "id": memory_id,
        "content": "REDACTED" if is_private else str(memory.get("content", "")),
        "timestamp": str(memory.get("timestamp", "")),
        "category": str(memory.get("category", "")),
        "importance": _coerce_int(memory.get("importance"), 3),
        "tags": memory.get("tags", []),
        "is_private": is_private,
        "access_count": _coerce_int(memory.get("access_count"), 0),
        "last_accessed": str(memory.get("last_accessed", "")),
        "decay": _coerce_float(memory.get("decay"), 0.0),
        "emotional_trace": {
            "valence": _coerce_float(memory.get("emotional_valence"), 0.0),
            "arousal": _coerce_float(memory.get("emotional_arousal"), 0.5),
            "intensity": _coerce_float(memory.get("emotional_intensity"), 0.5),
        },
        "linked_ids": memory.get("linked_ids", []),
        "generated_notion_ids": generated_notion_ids,
    }


def _load_relationship_rows(settings: DashboardSettings) -> list[dict[str, object]]:
    if not settings.ego_mcp_data_dir:
        return []
    rel_path = Path(settings.ego_mcp_data_dir) / "relationships" / "models.json"
    if not rel_path.exists():
        return []
    try:
        payload = json.loads(rel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return []
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, object]] = []
    for pid, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        trust_raw = raw.get("trust_level")
        trust_val = None
        if isinstance(trust_raw, bool):
            pass
        elif isinstance(trust_raw, (int, float)):
            trust_val = float(trust_raw)
        elif isinstance(trust_raw, str):
            try:
                trust_val = float(trust_raw)
            except ValueError:
                pass
        total = _coerce_int(raw.get("total_interactions"), 0)
        shared_raw = raw.get("shared_episode_ids")
        shared = 0
        if isinstance(shared_raw, list):
            shared = len(shared_raw)
        else:
            shared = _coerce_int(raw.get("shared_episodes_count"), 0)
        aliases_raw = raw.get("aliases", [])
        aliases_list = []
        if isinstance(aliases_raw, list):
            for a in aliases_raw:
                if isinstance(a, str) and a:
                    aliases_list.append(a)
        name_raw = raw.get("name")
        name = str(name_raw) if isinstance(name_raw, str) and name_raw else pid
        last_int = raw.get("last_interaction")
        first_int = raw.get("first_interaction")
        rows.append(
            {
                "person_id": str(pid),
                "name": name,
                "relation_kind": str(raw.get("relation_kind", "interlocutor")),
                "trust_level": trust_val,
                "total_interactions": total,
                "shared_episodes_count": shared,
                "last_interaction": str(last_int) if isinstance(last_int, str) else "",
                "first_interaction": str(first_int) if isinstance(first_int, str) else "",
                "aliases": aliases_list,
            }
        )
    rows.sort(key=lambda r: str(r.get("person_id", "")))
    return rows


def _default_store(settings: DashboardSettings | None = None) -> StoreProtocol:
    app_settings = settings or load_settings()
    desire_catalog = load_desire_catalog(app_settings.ego_mcp_data_dir)
    if app_settings.use_external_store and app_settings.database_url and app_settings.redis_url:
        sql_store = SqlTelemetryStore(
            app_settings.database_url,
            app_settings.redis_url,
            desire_catalog=desire_catalog,
        )
        sql_store.initialize()
        return sql_store
    return TelemetryStore(desire_catalog=desire_catalog)


def create_app(
    store: StoreProtocol | None = None,
    settings: DashboardSettings | None = None,
) -> FastAPI:
    app_settings = settings or load_settings()
    telemetry = store or _default_store(app_settings)
    use_local_inmemory_ingestor = (
        store is None
        and not app_settings.use_external_store
        and isinstance(telemetry, TelemetryStore)
    )
    local_ingestor_thread: threading.Thread | None = None
    local_ingestor_stop_event: threading.Event | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        nonlocal local_ingestor_thread, local_ingestor_stop_event
        if use_local_inmemory_ingestor:
            if local_ingestor_thread is None or not local_ingestor_thread.is_alive():
                local_ingestor_stop_event = threading.Event()
                local_ingestor_thread = threading.Thread(
                    target=tail_jsonl_file,
                    kwargs={
                        "path": app_settings.log_path,
                        "store": telemetry,
                        "poll_seconds": app_settings.ingest_poll_seconds,
                        "stop_event": local_ingestor_stop_event,
                    },
                    name="ego-dashboard-local-ingestor",
                    daemon=True,
                )
                local_ingestor_thread.start()
        try:
            yield
        finally:
            if use_local_inmemory_ingestor:
                if local_ingestor_stop_event is not None:
                    local_ingestor_stop_event.set()
                if local_ingestor_thread is not None and local_ingestor_thread.is_alive():
                    local_ingestor_thread.join(
                        timeout=max(1.0, app_settings.ingest_poll_seconds * 2)
                    )
                local_ingestor_thread = None
                local_ingestor_stop_event = None

    app = FastAPI(title="ego-mcp dashboard api", lifespan=lifespan)
    if app_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _current_with_file_relationship() -> dict[str, object]:
        result = telemetry.current()
        rows = _load_relationship_rows(app_settings)
        if rows:
            best = max(
                rows,
                key=lambda r: (
                    _coerce_float(r.get("trust_level"), 0),
                    _coerce_int(r.get("shared_episodes_count"), 0),
                ),
            )
            result["latest_relationship"] = {
                "trust_level": _coerce_float(best.get("trust_level"), 0),
                "total_interactions": float(_coerce_int(best.get("total_interactions"), 0)),
                "shared_episodes_count": float(_coerce_int(best.get("shared_episodes_count"), 0)),
            }
        return result

    @app.get("/api/v1/current")
    def get_current() -> dict[str, object]:
        return _current_with_file_relationship()

    @app.get("/api/v1/usage/tools")
    def get_tool_usage(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "1m",
    ) -> dict[str, object]:
        return {"items": telemetry.tool_usage(from_ts, to_ts, bucket)}

    @app.get("/api/v1/metrics/{key}")
    def get_metric(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "1m",
    ) -> dict[str, object]:
        return {"items": telemetry.metric_history(key, from_ts, to_ts, bucket)}

    @app.get("/api/v1/metrics/{key}/string-timeline")
    def get_string_timeline(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return {"items": telemetry.string_timeline(key, from_ts, to_ts)}

    @app.get("/api/v1/metrics/{key}/heatmap")
    def get_string_heatmap(
        key: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "5m",
    ) -> dict[str, object]:
        return {"items": telemetry.string_heatmap(key, from_ts, to_ts, bucket)}

    @app.get("/api/v1/desires/keys")
    def get_desire_metric_keys(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return {"items": telemetry.desire_metric_keys(from_ts, to_ts)}

    @app.get("/api/v1/desires/catalog")
    def get_desire_catalog() -> dict[str, object]:
        return load_desire_catalog(app_settings.ego_mcp_data_dir).to_response()

    @app.get("/api/v1/logs")
    def get_logs(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        level: str | None = None,
        search: str | None = None,
    ) -> dict[str, object]:
        return {"items": telemetry.logs(from_ts, to_ts, level, search=search)}

    @app.get("/api/v1/alerts/anomalies")
    def get_anomalies(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "5m",
    ) -> dict[str, object]:
        return {"items": telemetry.anomaly_alerts(from_ts, to_ts, bucket)}

    @app.get("/api/v1/memory/network")
    def get_memory_network() -> dict[str, object]:
        return _load_memory_network(app_settings)

    @app.get("/api/v1/memory/{memory_id}")
    def get_memory_detail(memory_id: str) -> dict[str, object]:
        detail = _load_memory_detail(app_settings, memory_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return detail

    @app.get("/api/v1/memory/network/subgraph")
    def get_memory_subgraph(
        node_id: str,
        depth: int = Query(default=1, ge=1, le=3),
    ) -> dict[str, object]:
        memory_rows = _load_memory_rows(app_settings)
        notion_rows = _load_notion_rows(app_settings)
        full_network = _build_memory_network(memory_rows, notion_rows)
        full_nodes = cast(list[dict[str, object]], full_network["nodes"])
        full_edges = cast(list[dict[str, object]], full_network["edges"])
        full_graph = _build_graph(
            {
                str(node["id"])
                for node in full_nodes
                if isinstance(node.get("id"), str) and node.get("id")
            },
            full_edges,
        )
        if node_id not in full_graph:
            raise HTTPException(status_code=404, detail="Node not found")
        subgraph = nx.ego_graph(full_graph, node_id, radius=depth)
        subgraph_ids = {str(graph_node_id) for graph_node_id in subgraph.nodes}
        return _build_memory_network(
            [row for row in memory_rows if str(row.get("id", "")) in subgraph_ids],
            [row for row in notion_rows if str(row.get("id", "")) in subgraph_ids],
        )

    @app.get("/api/v1/memory/network/path")
    def get_memory_path(
        from_id: str = Query(alias="from"),
        to_id: str = Query(alias="to"),
    ) -> dict[str, object]:
        network = _load_memory_network(app_settings)
        nodes = cast(list[dict[str, object]], network["nodes"])
        edges = cast(list[dict[str, object]], network["edges"])
        graph = _build_graph(
            {
                str(node["id"])
                for node in nodes
                if isinstance(node.get("id"), str) and node.get("id")
            },
            edges,
        )
        if from_id not in graph or to_id not in graph:
            raise HTTPException(status_code=404, detail="Node not found")
        try:
            node_ids = [str(node_id) for node_id in nx.shortest_path(graph, from_id, to_id)]
        except nx.NetworkXNoPath:
            return {"node_ids": [], "edge_pairs": [], "length": 0, "exists": False}
        edge_pairs = [[node_ids[index], node_ids[index + 1]] for index in range(len(node_ids) - 1)]
        return {
            "node_ids": node_ids,
            "edge_pairs": edge_pairs,
            "length": len(edge_pairs),
            "exists": True,
        }

    @app.get("/api/v1/notions")
    def get_notions() -> dict[str, object]:
        return {"items": _load_notion_rows(app_settings)}

    @app.get("/api/v1/notions/{notion_id}/history")
    def get_notion_history(
        notion_id: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
        bucket: str = "15m",
    ) -> dict[str, object]:
        return {"items": telemetry.notion_history(notion_id, from_ts, to_ts, bucket)}

    @app.get("/api/v1/relationships/overview")
    def get_relationships_overview() -> dict[str, object]:
        return {"items": _load_relationship_rows(app_settings)}

    @app.get("/api/v1/relationships/surface-timeline")
    def get_surface_timeline(
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return {"items": telemetry.surface_timeline(from_ts, to_ts)}

    @app.get("/api/v1/relationships/{person_id}/detail")
    def get_relationship_detail(
        person_id: str,
        from_ts: datetime = Query(alias="from"),
        to_ts: datetime = Query(alias="to"),
    ) -> dict[str, object]:
        return telemetry.relationship_detail(person_id, from_ts, to_ts)

    @app.websocket("/ws/current")
    async def ws_current(websocket: WebSocket) -> None:
        await websocket.accept()
        recent_log_keys: deque[str] = deque(maxlen=512)
        recent_log_key_set: set[str] = set()
        try:
            while True:
                await websocket.send_json(
                    {
                        "type": "current_snapshot",
                        "at": datetime.now(tz=UTC).isoformat(),
                        "data": _current_with_file_relationship(),
                    }
                )
                end = datetime.now(tz=UTC)
                start = end - timedelta(minutes=5)
                logs = telemetry.logs(start, end)
                for log in logs:
                    log_key = json.dumps(
                        {
                            "ts": log.get("ts"),
                            "level": log.get("level"),
                            "logger": log.get("logger"),
                            "message": log.get("message"),
                            "fields": log.get("fields", {}),
                        },
                        sort_keys=True,
                        default=str,
                    )
                    if log_key in recent_log_key_set:
                        continue
                    payload = dict(log)
                    fields = payload.get("fields")
                    if isinstance(fields, dict) and "tool_name" in fields:
                        payload.setdefault("tool_name", fields["tool_name"])
                    if "ok" not in payload:
                        level = str(payload.get("level", "")).upper()
                        message = str(payload.get("message", ""))
                        payload["ok"] = not (level == "ERROR" or message == "Tool execution failed")
                    await websocket.send_json({"type": "log_line", "data": payload})
                    if len(recent_log_keys) == recent_log_keys.maxlen:
                        evicted = recent_log_keys[0]
                        recent_log_key_set.discard(evicted)
                    recent_log_keys.append(log_key)
                    recent_log_key_set.add(log_key)
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(2)
        except Exception:
            await websocket.close()

    return app
