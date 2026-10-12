"""Tests for the privacy & secret scan gate (`scripts/check_secrets.py`).

The last test is the acceptance gate: the shipped repository must be clean.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_secrets.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("check_secrets", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules, so register first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def _kinds(findings) -> set[str]:
    return {finding.kind for finding in findings}


def test_script_exists_and_is_importable() -> None:
    assert SCRIPT.exists()
    assert hasattr(scanner, "scan_repo")
    assert hasattr(scanner, "scan_text")


@pytest.mark.parametrize(
    ("line", "expected_kind"),
    [
        ("OPENAI_API_KEY=sk-" + "A" * 40, "secret: openai-style key"),
        ("aws_access_key_id = AKIAIOSFODNN7EXAMPLE", "secret: aws access key id"),
        ("key = AIza" + "b" * 35, "secret: google api key"),
        ("token = xoxb-1234567890-abcdefghij", "secret: slack token"),
        ("ghp_" + "c" * 40, "secret: github token"),
        ("-----BEGIN RSA PRIVATE KEY-----", "secret: private key block"),
        ("DATABASE_PASSWORD=sup3rs3cr3tvalue!", "secret: assignment"),
        ("path = C:\\Users\\realname\\projects\\secret", "privacy: windows user path"),
        ("bundler config at /home/realname/.bundle/config", "privacy: posix home path"),
    ],
)
def test_detects_real_shapes(line: str, expected_kind: str) -> None:
    findings = scanner.scan_text(line, "some/file.py")
    assert expected_kind in _kinds(findings), [finding.render() for finding in findings]


@pytest.mark.parametrize(
    "line",
    [
        "FRED_API_KEY=<your-free-key>",
        "RCA_LLM_API_KEY=",
        "RCA_LLM_API_KEY=",
        "api_key: your-key-here",
        "TOKEN=placeholder-value",
        "# set SECRET_KEY=example-value in .env",
        "PASSWORD=changeme",
        "client_secret = ...",
    ],
)
def test_allows_documented_placeholders(line: str) -> None:
    assert scanner.scan_text(line, "docs/example.md") == [], line


def test_ignores_pattern_definitions_in_scanner_sources() -> None:
    # The scanner and its tests document the patterns; they must not flag themselves.
    assert scanner.scan_text("OPENAI_API_KEY=sk-" + "A" * 40, "scripts/check_secrets.py") == []
    assert scanner.scan_text("OPENAI_API_KEY=sk-" + "A" * 40, "services/api/tests/test_security_scan.py") == []


def test_housekeeping_flags_a_committed_env_file(monkeypatch) -> None:
    monkeypatch.setattr(scanner, "_tracked_files", lambda include_untracked=False: [".env"])
    findings = scanner.scan_repo()
    assert "housekeeping: local env file" in _kinds(findings)


def test_env_example_is_explicitly_allowed(monkeypatch) -> None:
    monkeypatch.setattr(scanner, "_tracked_files", lambda include_untracked=False: [".env.example"])
    assert scanner.scan_repo() == []


def test_housekeeping_flags_build_output_and_runtime_artefacts(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner,
        "_tracked_files",
        lambda include_untracked=False: [
            "apps/web/node_modules/react/index.js",
            "apps/web/dist/assets/index.js",
            "services/api/runtime/reports/x.md",
            "services/api/app/__pycache__/x.pyc",
        ],
    )
    kinds = _kinds(scanner.scan_repo())
    assert "housekeeping: build output" in kinds
    assert "housekeeping: runtime artefacts" in kinds


def test_repository_is_clean() -> None:
    """Acceptance gate: no secret, no .env, no developer path, no oversized artefact."""
    findings = scanner.scan_repo()
    errors = [finding for finding in findings if finding.severity == "error"]
    assert errors == [], "\n".join(finding.render() for finding in errors)


def test_summary_shape() -> None:
    report = scanner.summarise([])
    assert report["status"] == "clean"
    assert report["errors"] == 0


def test_main_returns_non_zero_when_dirty(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        scanner,
        "scan_repo",
        lambda include_untracked=False: [scanner.Finding("error", "secret: test", "x.py", 1, "boom")],
    )
    assert scanner.main([]) == 1
    assert "must be fixed" in capsys.readouterr().out


def test_output_is_ascii_safe_for_windows_consoles() -> None:
    """A cp932/cp1252 terminal must not be able to crash the gate (regression)."""
    finding = scanner.Finding("error", "secret: assignment", "docs/示例.md", 3, "值含有中文")
    rendered = finding.render()
    assert rendered.isascii(), rendered
    assert "\\u" in rendered, "non-ASCII content must be escaped, not dropped"
    report = scanner.summarise([finding])
    assert json.dumps(report, ensure_ascii=False)


def test_cli_runs_end_to_end_without_an_encoding_crash() -> None:
    """Run `main()` for real: exit code 0, and the summary lines are ASCII."""
    import io
    import contextlib

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = scanner.main([])
    output = buffer.getvalue()
    assert code == 0, output
    assert "Result: clean" in output
    assert output.isascii(), output
