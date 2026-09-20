from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
SKIP_DIRS = {
    ".git",
    ".venv",
    "build",
    "dist",
    "release",
    "__pycache__",
    ".pytest_cache",
}

private_ipv4 = re.compile(
    r"\b(?:"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")\b"
)

credential_patterns = [
    re.compile(
        r"(?i)\b(?:password|passwd|secret|token)\s*=\s*"
        r"['\"][^'\"]{8,}['\"]"
    ),
    re.compile(
        r"(?i)['\"](?:password|passwd|secret|token)['\"]\s*:\s*"
        r"['\"][^'\"]{8,}['\"]"
    ),
]

findings = []
for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    if path.resolve() == SELF:
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.suffix.lower() in {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".zip", ".rar"
    }:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue

    rel = path.relative_to(ROOT)

    for match in private_ipv4.finditer(text):
        findings.append(f"{rel}: private IPv4 address: {match.group(0)}")

    for pattern in credential_patterns:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{rel}:{line}: possible hard-coded credential")

if findings:
    print("PUBLIC SAFETY CHECK FAILED")
    for item in findings:
        print("-", item)
    sys.exit(1)

print("PUBLIC SAFETY CHECK PASSED")
