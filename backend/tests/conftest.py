import os
import pytest

# Setear variables mínimas antes de que se importe cualquier módulo de app
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("APP_AUTH_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://agents:agents_local_dev@localhost:5432/agents")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
