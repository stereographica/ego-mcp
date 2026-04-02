from __future__ import annotations

from pathlib import Path


def test_backend_mounts_ego_mcp_data_dir_with_write_access() -> None:
    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    text = compose_file.read_text(encoding="utf-8")

    assert "- ${DASHBOARD_EGO_MCP_DATA_DIR:-/tmp}:${DASHBOARD_EGO_MCP_DATA_DIR:-/tmp}\n" in text
    assert (
        "- ${DASHBOARD_EGO_MCP_DATA_DIR:-/tmp}:${DASHBOARD_EGO_MCP_DATA_DIR:-/tmp}:ro" not in text
    )
