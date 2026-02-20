#!/usr/bin/env python3
"""Extract metadata from HAR files without loading full response bodies into memory.

Outputs a JSON summary or a Markdown companion file describing what a HAR trace
contains (domains, request counts, methods, status codes, time range) and how
one might recapture it.
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse


def extract_metadata(har_path: str) -> dict:
    """Parse a HAR file and return a metadata dict."""
    with open(har_path, "r", encoding="utf-8", errors="replace") as f:
        try:
            har = json.load(f)
        except json.JSONDecodeError:
            # Some HAR files are truncated or contain control chars — try strict=False
            f.seek(0)
            raw = f.read()
            try:
                har = json.loads(raw, strict=False)
            except json.JSONDecodeError:
                # Last resort: return minimal metadata from file size alone
                return {
                    "file": os.path.basename(har_path),
                    "size_bytes": os.path.getsize(har_path),
                    "size_human": _human_size(os.path.getsize(har_path)),
                    "total_requests": 0,
                    "domains": {},
                    "methods": {},
                    "status_codes": {},
                    "time_range": {"earliest": None, "latest": None},
                    "parse_error": "HAR file contains malformed JSON",
                }

    entries = har.get("log", {}).get("entries", [])
    domains: Counter = Counter()
    methods: Counter = Counter()
    statuses: Counter = Counter()
    timestamps: list[str] = []

    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})

        url = req.get("url", "")
        parsed = urlparse(url)
        if parsed.hostname:
            domains[parsed.hostname] += 1

        method = req.get("method", "UNKNOWN")
        methods[method] += 1

        status = resp.get("status", 0)
        statuses[str(status)] += 1

        started = entry.get("startedDateTime", "")
        if started:
            timestamps.append(started)

    timestamps.sort()
    size_bytes = os.path.getsize(har_path)

    return {
        "file": os.path.basename(har_path),
        "size_bytes": size_bytes,
        "size_human": _human_size(size_bytes),
        "total_requests": len(entries),
        "domains": dict(domains.most_common()),
        "methods": dict(methods.most_common()),
        "status_codes": dict(statuses.most_common()),
        "time_range": {
            "earliest": timestamps[0] if timestamps else None,
            "latest": timestamps[-1] if timestamps else None,
        },
    }


def to_markdown(meta: dict, archive_path: str | None = None) -> str:
    """Render metadata as a Markdown companion file."""
    lines = [f"# {meta['file']}", ""]

    if archive_path:
        lines.append(f"**Offloaded to:** `{archive_path}`  ")
    lines.append(f"**Original size:** {meta['size_human']}  ")
    lines.append(f"**Moved on:** {datetime.now().strftime('%Y-%m-%d')}  ")
    lines.append("")

    lines.append("## Contents Summary")
    lines.append("")

    top_domains = list(meta["domains"].keys())[:8]
    lines.append(f"- **Domains captured:** {', '.join(top_domains)}")
    lines.append(f"- **Total requests:** {meta['total_requests']}")

    method_parts = [f"{m} ({c})" for m, c in meta["methods"].items()]
    lines.append(f"- **Methods:** {', '.join(method_parts)}")

    status_parts = [f"{s} ({c})" for s, c in meta["status_codes"].items()]
    lines.append(f"- **Status codes:** {', '.join(status_parts)}")

    tr = meta["time_range"]
    if tr["earliest"] and tr["latest"]:
        lines.append(f"- **Date range:** {tr['earliest']} — {tr['latest']}")

    lines.append("")
    lines.append("## How to Recapture")
    lines.append("")
    lines.append("1. Open browser DevTools (F12) → Network tab")
    lines.append('2. Check "Preserve log"')
    lines.append("3. Navigate to the relevant page/API")
    lines.append('4. Right-click in the network list → "Save all as HAR with content"')
    lines.append(f"5. Save as `{meta['file']}`")
    lines.append("")

    return "\n".join(lines)


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.0f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Extract metadata from a HAR file")
    parser.add_argument("har_file", help="Path to the HAR file")
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--archive-path",
        help="Destination path (shown in Markdown output)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write output to file instead of stdout",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.har_file):
        print(f"Error: {args.har_file} not found", file=sys.stderr)
        sys.exit(1)

    meta = extract_metadata(args.har_file)

    if args.format == "json":
        content = json.dumps(meta, indent=2)
    else:
        content = to_markdown(meta, archive_path=args.archive_path)

    if args.output:
        with open(args.output, "w") as f:
            f.write(content)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    main()
