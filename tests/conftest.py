from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def codex_text() -> str:
    return (FIXTURES / "codex_sample.jsonl").read_text(encoding="utf-8")


@pytest.fixture
def cc_text() -> str:
    return (FIXTURES / "claude_code_sample.jsonl").read_text(encoding="utf-8")


@pytest.fixture
def claudeai_text() -> str:
    return (FIXTURES / "claude_ai_sample.json").read_text(encoding="utf-8")


@pytest.fixture
def markdown_text() -> str:
    return (FIXTURES / "markdown_sample.md").read_text(encoding="utf-8")
