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
    @pytest.mark.anyio
    async def test_blocks_invalid_working_dir(self):
        from app.tools import registry as reg_mod
        import app.config as cfg_mod

        mock_wm = AsyncMock()
        with patch.object(cfg_mod.settings, "allowed_working_dirs", ["/workspace"]):
            result = await reg_mod._handle_run_claude_code(
                worker_manager=mock_wm,
                session_id="sess-1",
                prompt="test",
                working_dir="/etc/malicious",
            )
        assert "error" in result
        assert "no está permitido" in result["error"]
        mock_wm.create.assert_not_called()

    @pytest.mark.anyio
    async def test_allows_valid_working_dir(self):
        import sys
        from app.tools import registry as reg_mod
        import app.config as cfg_mod

        mock_wm = AsyncMock()
        mock_wm.create.return_value = MagicMock(id="worker-123")

        mock_tasks = MagicMock()
        mock_tasks.execute_claude_code = MagicMock()

        with patch.object(cfg_mod.settings, "allowed_working_dirs", ["/workspace"]):
            with patch.dict(sys.modules, {"app.workers.tasks": mock_tasks}):
                result = await reg_mod._handle_run_claude_code(
                    worker_manager=mock_wm,
                    session_id="sess-1",
                    prompt="test",
                    working_dir="/workspace/myproject",
                )
        assert "error" not in result
        assert result["worker_id"] == "worker-123"

    @pytest.mark.anyio
    async def test_no_restriction_when_allowed_dirs_empty(self):
        import sys
        from app.tools import registry as reg_mod
        import app.config as cfg_mod

        mock_wm = AsyncMock()
        mock_wm.create.return_value = MagicMock(id="worker-456")

        mock_tasks = MagicMock()
        mock_tasks.execute_claude_code = MagicMock()

        with patch.object(cfg_mod.settings, "allowed_working_dirs", []):
            with patch.dict(sys.modules, {"app.workers.tasks": mock_tasks}):
                result = await reg_mod._handle_run_claude_code(
                    worker_manager=mock_wm,
                    session_id="sess-1",
                    prompt="test",
                    working_dir="/anywhere",
                )
        assert "error" not in result


def _make_croniter_mock(raise_on_init: bool = False):
    """Mock del módulo croniter para tests locales (no instalado fuera de Docker)."""
    import sys
    mock_module = MagicMock()
    mock_module.CroniterBadCronError = ValueError
    if raise_on_init:
        mock_module.croniter.side_effect = ValueError("bad cron expression")
    else:
        mock_itr = MagicMock()
        mock_itr.get_next.return_value = MagicMock()
        mock_module.croniter.return_value = mock_itr
    return mock_module


class TestScheduleTaskHandler:
    @pytest.mark.anyio
    async def test_invalid_cron_returns_error(self):
        import sys
        with patch.dict(sys.modules, {"croniter": _make_croniter_mock(raise_on_init=True)}):
            from app.tools.registry import _handle_schedule_task
            import importlib, app.tools.registry as reg_mod
            importlib.reload(reg_mod)
            mock_db = AsyncMock()
            result = await reg_mod._handle_schedule_task(
                db=mock_db,
                name="test",
                cron_expr="not-a-cron",
                action_type="message",
                action_config={"message": "hola"},
            )
        assert "error" in result
        assert "cron" in result["error"].lower()

    @pytest.mark.anyio
    async def test_invalid_action_type_returns_error(self):
        import sys
        with patch.dict(sys.modules, {"croniter": _make_croniter_mock(raise_on_init=False)}):
            import importlib, app.tools.registry as reg_mod
            importlib.reload(reg_mod)
            mock_db = AsyncMock()
            result = await reg_mod._handle_schedule_task(
                db=mock_db,
                name="test",
                cron_expr="0 9 * * *",
                action_type="invalid_type",
                action_config={},
            )
        assert "error" in result
        assert "action_type" in result["error"]
