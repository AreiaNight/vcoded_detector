"""Export crawler and database scan results to a structured JSON report."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def build_report(scan_type, records, parameters=None):
    """Build a report dict from crawler records.

    Each record is either a successful scan ({"url", "status", "source", "total",
    "results"}) or a failure ({"url", "error"}).
    """
    successes = [r for r in records if "error" not in r]
    failures = [r for r in records if "error" in r]

    signals = {}
    for record in successes:
        for match in record.get("results", []):
            signals[match["word"]] = signals.get(match["word"], 0) + match["count"]

    return {
        "schema_version": SCHEMA_VERSION,
        "scan_type": scan_type,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parameters": parameters or {},
        "summary": {
            "urls": len(records),
            "fetched": len(successes),
            "failed": len(failures),
            "total_matches": sum(r.get("total", 0) for r in successes),
            "urls_with_matches": sum(1 for r in successes if r.get("total", 0) > 0),
            "signals": dict(sorted(signals.items(), key=lambda kv: kv[1], reverse=True)),
        },
        "results": [
            {
                "url": r.get("url"),
                "status": r["status"],
                "source": r["source"],
                "total": r["total"],
                "matches": r["results"],
                **({"assessment": r["assessment"]} if "assessment" in r else {}),
            }
            for r in successes
        ],
        "errors": [{"url": r.get("url"), "error": r["error"]} for r in failures],
    }


def write_report(path, report):
    """Write the report atomically so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def export_results(path, scan_type, records, parameters=None):
    """Build and write a report; returns the written path."""
    return write_report(path, build_report(scan_type, records, parameters))
