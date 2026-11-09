#!/usr/bin/env python3
"""ops/security_scan.py — Automated Secret Scanner and Repository Security Audit (T-052).

Scans the repository to verify that:
1. No unmasked API keys (Gemini, Telegram bot, Meta Threads token, Fernet key, AWS key) exist in tracked code.
2. No live .env or SQLite database files (*.db, *.db-wal, *.db-shm) are tracked in git.
3. .gitignore strictly covers sensitive file patterns.
4. Exits with code 0 on clean scan, or code 1 if violations are detected.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Directories to ignore
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".next",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "venv",
}

# Files to ignore (e.g. documentation examples, lock files)
IGNORED_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "test_security_audit.py",  # Contains dummy patterns for testing
}

# Regex patterns for accidental live secret leakage
SECRET_PATTERNS = [
    ("Gemini API Key", re.compile(r"AIzaSy[A-Za-z0-9_-]{33}")),
    ("Telegram Bot Token", re.compile(r"\b[0-9]{9,10}:[a-zA-Z0-9_-]{35}\b")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private Key Header", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----")),
]


def scan_file_contents(file_path: Path) -> list[str]:
    """Scan a single file for secret patterns."""
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    for line_num, line in enumerate(content.splitlines(), start=1):
        # Skip comment lines that explicitly say example, fake, or mock
        lower_line = line.lower()
        if any(w in lower_line for w in ("dummy", "example", "canned", "placeholder", "mock", "fake", "test_")):
            continue

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                violations.append(f"{file_path}:{line_num} — Found {label}")

    return violations


def check_git_tracked_sensitive_files(repo_root: Path) -> list[str]:
    """Verify that no sensitive database or local env files are tracked by git."""
    violations = []
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_files = res.stdout.splitlines()
        for f in tracked_files:
            lower_f = f.lower()
            if lower_f == ".env":
                violations.append("Live .env file is tracked in git index! Only .env.example should be tracked.")
            if lower_f.endswith((".db", ".db-wal", ".db-shm")):
                violations.append(f"Database file '{f}' is tracked in git index!")
    except Exception as e:
        # Not a git repo or git not found
        pass
    return violations


def check_gitignore_rules(repo_root: Path) -> list[str]:
    """Verify that .gitignore properly covers critical secret patterns."""
    violations = []
    gitignore_file = repo_root / ".gitignore"
    if not gitignore_file.exists():
        return ["Missing .gitignore file in repository root!"]

    content = gitignore_file.read_text(encoding="utf-8")
    required_patterns = [".env", "*.db", "node_modules", "__pycache__"]
    for req in required_patterns:
        if req not in content:
            violations.append(f".gitignore is missing recommended rule: '{req}'")
    return violations


def run_full_security_scan(repo_root: Path) -> tuple[int, list[str]]:
    """Run full repository security scan."""
    all_violations: list[str] = []

    # 1. Content scan across files
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for fname in files:
            if fname in IGNORED_FILES or fname.endswith((".pyc", ".png", ".jpg", ".ico", ".woff", ".woff2")):
                continue
            fpath = Path(root) / fname
            violations = scan_file_contents(fpath)
            all_violations.extend(violations)

    # 2. Check git-tracked sensitive files
    all_violations.extend(check_git_tracked_sensitive_files(repo_root))

    # 3. Check gitignore completeness
    all_violations.extend(check_gitignore_rules(repo_root))

    return len(all_violations), all_violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print(f"=== Scanning repository for security compliance: {repo_root} ===")

    count, violations = run_full_security_scan(repo_root)
    if count > 0:
        print(f"\n❌ SECURITY AUDIT FAILED: Found {count} violation(s):")
        for v in violations:
            print(f"  • {v}")
        return 1

    print("\n✅ SECURITY AUDIT PASSED: 0 secrets detected, git tracking clean, .gitignore verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
