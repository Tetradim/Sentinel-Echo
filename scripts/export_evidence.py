"""Create a credential-sanitized archive of Echo trading evidence."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable
import zipfile


SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "credential",
    "access_token",
    "refresh_token",
    "discord_token",
    "authorization",
)
TEXT_PATTERNS = (
    re.compile(
        r"(?i)((?:[\"']?)(?:APCA_[A-Z_]*KEY|API[_ -]?KEY|SECRET(?:[_ -]?KEY)?|PASSWORD|DISCORD[_ -]?TOKEN)(?:[\"']?)\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,}\]]+)"
    ),
    re.compile(r"(?i)(\bAuthorization\s*:\s*Bearer\s+)[^\s]+"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bPK[A-Z0-9]{16,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b"),
)
DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)")
TEXT_SUFFIXES = {".log", ".jsonl", ".json", ".txt", ".md"}
DB_SUFFIXES = {".sqlite3", ".db"}


def sanitize_text(value: str) -> str:
    sanitized = str(value)
    for pattern in TEXT_PATTERNS:
        if pattern.groups:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def sanitize_value(value: Any, *, key: str = "") -> Any:
    normalized_key = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(child_key): sanitize_value(child, key=str(child_key)) for child_key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, bytes):
        return {"redacted_binary_bytes": len(value)}
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def _date_from_path(path: Path) -> date | None:
    match = DATE_IN_NAME.search(path.name)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _is_since(path: Path, cutoff: date) -> bool:
    named_date = _date_from_path(path)
    if named_date is not None:
        return named_date >= cutoff
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date() >= cutoff


def iter_text_sources(repo: Path, cutoff: date) -> Iterable[Path]:
    direct = [repo / "tradebot.log"]
    dated_roots = [
        repo / "backend" / "data" / "alert-capture",
        repo / "backend" / "data" / "event-bus",
    ]
    general_roots = [repo / "data"]
    report_roots = [repo / "docs" / "reports"]
    seen: set[Path] = set()
    for path in direct:
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            seen.add(path.resolve())
            yield path
    for root in dated_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and _is_since(path, cutoff):
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield path
    for root in general_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and _is_since(path, cutoff):
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield path
    for root in report_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield path


def iter_database_sources(repo: Path) -> Iterable[Path]:
    candidates = [repo / "tradebot.db", *(repo / "data").rglob("*")]
    seen: set[Path] = set()
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in DB_SUFFIXES:
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield path


def _safe_relative(path: Path, repo: Path) -> Path:
    try:
        return path.resolve().relative_to(repo.resolve())
    except ValueError:
        return Path(path.name)


def _write_sanitized_text(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8", errors="replace") as reader, destination.open(
        "w", encoding="utf-8", newline=""
    ) as writer:
        for line in reader:
            writer.write(sanitize_text(line))


def _decoded_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[:1] not in {"{", "["}:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _export_database(source: Path, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                continue
            output = destination / f"{table}.jsonl"
            with output.open("w", encoding="utf-8", newline="\n") as writer:
                for row in connection.execute(f'SELECT * FROM "{table}"'):
                    record = {}
                    for key in row.keys():
                        decoded = _decoded_json(row[key])
                        record[key] = sanitize_value(decoded, key=key)
                    writer.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
            written.append(output)
    except sqlite3.DatabaseError as exc:
        error_file = destination / "EXPORT_ERROR.txt"
        error_file.write_text(f"SQLite export failed: {exc}\n", encoding="utf-8")
        written.append(error_file)
    finally:
        if "connection" in locals():
            connection.close()
    return written


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_archive(repo: Path, output: Path, *, cutoff: date) -> dict[str, Any]:
    repo = repo.resolve()
    output = output.resolve()
    text_sources = sorted(iter_text_sources(repo, cutoff))
    database_sources = sorted(iter_database_sources(repo))
    with tempfile.TemporaryDirectory(prefix="echo-evidence-") as temporary:
        staging = Path(temporary) / "Echo-Evidence"
        written: list[tuple[Path, str]] = []

        for source in text_sources:
            relative = _safe_relative(source, repo)
            destination = staging / "logs-and-reports" / relative
            _write_sanitized_text(source, destination)
            written.append((destination, str(relative).replace("\\", "/")))

        for index, source in enumerate(database_sources, start=1):
            relative = _safe_relative(source, repo)
            label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(relative).replace("\\", "__").replace("/", "__"))
            destination = staging / "database-exports" / f"{index:03d}-{label}"
            for exported in _export_database(source, destination):
                written.append((exported, str(relative).replace("\\", "/")))

        readme = staging / "README.txt"
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "Sentinel Echo evidence archive\n"
            f"Created: {datetime.now(timezone.utc).isoformat()}\n"
            f"Experiment log cutoff: {cutoff.isoformat()}\n\n"
            "Contents include retained Echo runtime logs, Discord alert captures, event-bus records, "
            "analysis reports, and sanitized JSONL exports of every retained SQLite snapshot.\n\n"
            "Security: raw SQLite files, .env files, and credential stores are not included. "
            "Credential-shaped values and sensitive JSON fields are replaced with [REDACTED].\n\n"
            "Scope: event-bus and alert-capture files begin at the experiment start on 2026-08-26. "
            "Earlier event-bus files include more than 40 GB of unrelated pre-experiment output and are intentionally excluded.\n",
            encoding="utf-8",
        )
        written.append((readme, "generated"))

        manifest_entries = []
        for path, source_name in written:
            manifest_entries.append(
                {
                    "archive_path": str(path.relative_to(staging)).replace("\\", "/"),
                    "source": source_name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cutoff": cutoff.isoformat(),
            "text_source_count": len(text_sources),
            "database_source_count": len(database_sources),
            "file_count": len(manifest_entries),
            "files": manifest_entries,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, Path("Echo-Evidence") / path.relative_to(staging))

    return {
        **manifest,
        "output": str(output),
        "archive_bytes": output.stat().st_size,
        "archive_sha256": _sha256(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", default="2026-08-26")
    args = parser.parse_args()
    result = create_archive(args.repo, args.output, cutoff=date.fromisoformat(args.since))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
