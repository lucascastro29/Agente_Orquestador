"""Tests para el ToolRegistry y handlers críticos."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tests.conftest  # noqa: F401


class TestToolRegistry:
    def test_all_critical_tools_registered(self):
        from app.tools.registry import registry

        critical = [
            "get_memoria", "update_memoria", "delete_memoria", "search_memoria",
            "run_claude_code", "get_workers_status", "cancel_worker",
            "create_subagent",
            "schedule_task", "list_scheduled_tasks", "delete_scheduled_task",
            "save_playbook", "list_playbooks", "get_playbook", "run_playbook",
        ]
        registered = set(registry.names())
        for tool in critical:
            assert tool in registered, f"Tool '{tool}' no está registrada"

    def test_run_claude_code_has_required_fields(self):
        from app.tools.registry import registry

        tool = registry.get("run_claude_code")
        assert tool is not None
        required = tool.input_schema.get("required", [])
        assert "prompt" in required
        assert "working_dir" in required

    def test_create_subagent_no_confirmation(self):
        from app.tools.registry import registry

        tool = registry.get("create_subagent")
        assert tool is not None
        assert tool.requires_confirmation is False


class TestRunClaudeCodeHandler:
    @pytest.mark.asyncio
    async def test_blocks_invalid_working_dir(self):
        from app.tools import registry as reg_mod
        from unittest.mock import patch

        mock_wm = AsyncMock()
        with patch.object(
            reg_mod.registry.get("run_claude_code"), "handler",
            wraps=reg_mod._handle_run_claude_code,
        ):
            with patch("app.config.settings") as mock_settings:
                mock_settings.allowed_working_dirs = ["/workspace"]
                result = await reg_mod._handle_run_claude_code(
                    worker_manager=mock_wm,
                    session_id="sess-1",
                    prompt="test",
                    working_dir="/etc/malicious",
                )
        assert "error" in result
        assert "no está permitido" in result["error"]
        mock_wm.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_valid_working_dir(self):
        from app.tools import registry as reg_mod

        mock_wm = AsyncMock()
        mock_wm.create.return_value = MagicMock(id="worker-123")

        with patch("app.tools.registry.settings") as mock_settings:
            mock_settings.allowed_working_dirs = ["/workspace"]
            with patch("app.tools.registry.execute_claude_code") as mock_task:
                mock_task.delay = MagicMock()
                result = await reg_mod._handle_run_claude_code(
                    worker_manager=mock_wm,
                    session_id="sess-1",
                    prompt="test",
                    working_dir="/workspace/myproject",
                )
        assert "error" not in result
        assert result["worker_id"] == "worker-123"

    @pytest.mark.asyncio
    async def test_no_restriction_when_allowed_dirs_empty(self):
        from app.tools import registry as reg_mod

        mock_wm = AsyncMock()
        mock_wm.create.return_value = MagicMock(id="worker-456")

        with patch("app.tools.registry.settings") as mock_settings:
            mock_settings.allowed_working_dirs = []
            with patch("app.tools.registry.execute_claude_code") as mock_task:
                mock_task.delay = MagicMock()
                result = await reg_mod._handle_run_claude_code(
                    worker_manager=mock_wm,
                    session_id="sess-1",
                    prompt="test",
                    working_dir="/anywhere",
                )
        assert "error" not in result


class TestScheduleTaskHandler:
    @pytest.mark.asyncio
    async def test_invalid_cron_returns_error(self):
        from app.tools.registry import _handle_schedule_task

        mock_db = AsyncMock()
        result = await _handle_schedule_task(
            db=mock_db,
            name="test",
            cron_expr="not-a-cron",
            action_type="message",
            action_config={"message": "hola"},
        )
        assert "error" in result
        assert "cron" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_action_type_returns_error(self):
        from app.tools.registry import _handle_schedule_task

        mock_db = AsyncMock()
        result = await _handle_schedule_task(
            db=mock_db,
            name="test",
            cron_expr="0 9 * * *",
            action_type="invalid_type",
            action_config={},
        )
        assert "error" in result
        assert "action_type" in result["error"]
