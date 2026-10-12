#!/usr/bin/env python
"""Privacy and secret scan for the repository.

Implements the "privacy & key scan" gate from the delivery checklist:

    python scripts/check_secrets.py            # scan the tracked files
    python scripts/check_secrets.py --all      # scan the working tree too
    python scripts/check_secrets.py --json     # machine-readable output

Exit code 0 means clean, 1 means at least one finding was reported. The scan
looks for four classes of problem:

1. **Secrets** — credential shapes (OpenAI-style keys, AWS keys, private key
   blocks, Slack/Google tokens) and assignments of a long, non-placeholder value
   to a key-like name.
2. **Environment files** — a committed `.env` (only `.env.example` may ship).
3. **Private context** — absolute developer paths (`C:\\Users\\<name>\\…`,
   `/home/<name>/…`) that would leak a machine or a person.
4. **Housekeeping** — accidentally committed build output, caches or artefacts
   larger than the size budget.

Placeholders are explicitly allowed: values wrapped in `<>`, or containing
`example`, `your`, `placeholder`, `changeme`, `dummy`, `xxxx` or `...` are
reported as *placeholders* (informational) rather than findings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # noqa: S404 - used only to list tracked files
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Console safety: this gate runs on Windows terminals whose code page cannot encode
# a typographic dash or a CJK path, so output is forced to UTF-8 and every message
# this script prints is kept ASCII-only.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):  # pragma: no cover - exotic stream
        pass

#: Files we never scan for "secret shapes" (they exist to describe them).
PATTERN_SOURCES = {
    "scripts/check_secrets.py",
    "services/api/tests/test_security_scan.py",
    "services/api/tests/test_agent_evaluation.py",
    "docs/agent-design.md",
    "docs/test-report.md",
    ".env.example",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("aws access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
)

#: `SOMETHING_KEY = "a-long-value"` / `SOMETHING_TOKEN: xxx`
ASSIGNMENT_PATTERN = re.compile(
    r"""(?P<name>[A-Za-z0-9_]{0,40}(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)[A-Za-z0-9_]{0,20})"""
    r"""\s*[:=]\s*["']?(?P<value>[^\s"',;)]{12,})["']?""",
    re.IGNORECASE,
)

PLACEHOLDER_MARKERS = ("<", ">", "example", "your", "placeholder", "changeme", "dummy", "xxxx", "...", "${")

PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("windows user path", re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s\"'|)]+")),
    ("posix home path", re.compile(r"(?<![\w.])/home/[A-Za-z0-9._-]+/")),
)

HOUSEKEEPING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("build output", re.compile(r"(^|/)(node_modules|dist|build|\.next|__pycache__|\.pytest_cache|\.vite)/")),
    ("coverage output", re.compile(r"(^|/)(htmlcov|coverage\.xml|\.coverage)$")),
    ("local env file", re.compile(r"(^|/)\.env(\.[A-Za-z0-9_.-]+)?$")),
    ("runtime artefacts", re.compile(r"(^|/)services/api/runtime/")),
)

MAX_FILE_BYTES = 5 * 1024 * 1024
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".txt", ".html", ".css", ".env", ".example", ".sh", ".ps1", ".sql", ".csv", ".lock", "",
}


@dataclass
class Finding:
    severity: str  # "error" | "info"
    kind: str
    path: str
    line: int | None
    detail: str

    def render(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else self.path
        line = f"[{self.severity.upper():5}] {self.kind:22} {location} - {self.detail}"
        # A CJK path or detail would crash a cp932/cp1252 console; escape instead.
        return line if line.isascii() else line.encode("unicode_escape").decode("ascii")


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def scan_text(text: str, path: str) -> list[Finding]:
    """Scan one file's content. ``path`` is repo-relative (used for reporting)."""
    findings: list[Finding] = []
    if path in PATTERN_SOURCES:
        # These files document the patterns themselves.
        return findings

    for index, line in enumerate(text.splitlines(), start=1):
        if "check_secrets" in line or "FORBIDDEN" in line:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(Finding("error", f"secret: {name}", path, index, "credential-shaped string"))
        match = ASSIGNMENT_PATTERN.search(line)
        if match and not _is_placeholder(match.group("value")):
            findings.append(
                Finding(
                    "error",
                    "secret: assignment",
                    path,
                    index,
                    f"{match.group('name')} is assigned a {len(match.group('value'))}-character value",
                )
            )
        for name, pattern in PATH_PATTERNS:
            found = pattern.search(line)
            if found:
                findings.append(Finding("error", f"privacy: {name}", path, index, found.group(0)))
    return findings


def _tracked_files(include_untracked: bool) -> list[str]:
    try:
        output = subprocess.run(  # noqa: S603 - fixed argument list
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = [name for name in output.split("\0") if name]
        if include_untracked:
            untracked = subprocess.run(  # noqa: S603 - fixed argument list
                ["git", "ls-files", "-z", "--others", "--exclude-standard"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            files += [name for name in untracked.split("\0") if name]
        return sorted(set(files))
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", "node_modules", "dist", "__pycache__", ".pytest_cache", "runtime", ".vite"}
        return sorted(
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in REPO_ROOT.rglob("*")
            if path.is_file() and not any(part in skip for part in path.parts)
        )


def scan_repo(include_untracked: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for relative in _tracked_files(include_untracked):
        for name, pattern in HOUSEKEEPING_PATTERNS:
            if pattern.search(relative):
                # `.env.example` is the documented template and is allowed.
                if name == "local env file" and relative.endswith(".env.example"):
                    continue
                findings.append(Finding("error", f"housekeeping: {name}", relative, None, "must not be committed"))
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append(
                Finding(
                    "error",
                    "housekeeping: large file",
                    relative,
                    None,
                    f"{path.stat().st_size / 1_048_576:.1f} MB exceeds the 5 MB budget",
                )
            )
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(text, relative))
    return findings


def summarise(findings: list[Finding]) -> dict:
    errors = [finding for finding in findings if finding.severity == "error"]
    return {
        "status": "clean" if not errors else "findings",
        "errors": len(errors),
        "infos": len(findings) - len(errors),
        "details": [asdict(finding) for finding in findings],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privacy and secret scan")
    parser.add_argument("--all", action="store_true", help="also scan untracked (non-ignored) files")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    findings = scan_repo(include_untracked=args.all)
    report = summarise(findings)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        scanned = len(_tracked_files(args.all))
        print(f"Privacy & secret scan - {scanned} file(s) scanned")
        for finding in findings:
            print(f"  {finding.render()}")
        if report["status"] == "clean":
            print("Result: clean - no secret, no committed .env, no absolute developer path, no oversized artefact.")
        else:
            print(f"Result: {report['errors']} finding(s) must be fixed before publishing.")

    return 0 if report["status"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
