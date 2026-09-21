#!/usr/bin/env python3
"""
WizAnn core-data updater.

Checks WizPoints' public timestamp manifest, downloads changed files only,
keeps dated raw snapshots, and records hashes/metadata locally.

No WizAnn login/device credentials are used.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://wizann.uk/apps/wizpoints/"
MANIFEST = urllib.parse.urljoin(BASE, "timestamps-v2.php")
UA = "KnowledgeCoreUpdater/0.1"

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def parse_manifest(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8", errors="replace")
    # Actual live response is concatenated, e.g.
    # data/Examiners.txt|1789998907data/Questions.txt|1789998905
    # Filenames may contain spaces, so use "data/" as the record boundary.
    text = re.sub(r"<br\s*/?>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    starts = [m.start() for m in re.finditer(r"data/", text)]
    result = {}
    for i, pos in enumerate(starts):
        chunk = text[pos: starts[i+1] if i+1 < len(starts) else len(text)]
        m = re.match(r"(.+)\|(\d+)\s*$", chunk)
        if m:
            result[m.group(1).strip()] = m.group(2)
    if not result:
        raise RuntimeError("Could not parse any path|timestamp records from timestamps-v2.php")
    return result

def safe_path(rel: str) -> Path:
    p = Path(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Unsafe server path: {rel}")
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="wizann-data", help="Local data directory")
    ap.add_argument("--all", action="store_true",
                    help="Download every manifest file. Default: core Points/Questions/Examiners only.")
    args = ap.parse_args()

    root = Path(args.root)
    current = root / "current"
    snapshots = root / "snapshots"
    state_file = root / "state.json"
    root.mkdir(parents=True, exist_ok=True)

    previous = {}
    if state_file.exists():
        previous = json.loads(state_file.read_text(encoding="utf-8")).get("timestamps", {})

    manifest_raw = fetch(MANIFEST)
    manifest = parse_manifest(manifest_raw)

    core_names = {"data/Questions.txt", "data/PointsInfo.txt", "data/Examiners.txt"}
    wanted = manifest if args.all else {k:v for k,v in manifest.items() if k in core_names}

    if not wanted:
        raise RuntimeError("Manifest parsed, but expected core files were not present.")

    changed = {p:t for p,t in wanted.items() if previous.get(p) != t}
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = snapshots / stamp

    downloaded = []
    for rel, server_stamp in changed.items():
        relpath = safe_path(rel)
        url = urllib.parse.urljoin(BASE, rel)
        data = fetch(url)

        snap = snapshot_dir / relpath
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_bytes(data)

        dest = current / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snap, dest)

        downloaded.append({
            "path": rel,
            "server_timestamp": server_stamp,
            "bytes": len(data),
            "sha256": sha256(data),
        })

    # Save the raw manifest every run for auditability.
    manifests = root / "manifests"
    manifests.mkdir(exist_ok=True)
    (manifests / f"{stamp}.txt").write_bytes(manifest_raw)

    state = {
        "checked_at_utc": now.isoformat(),
        "manifest_url": MANIFEST,
        "timestamps": {**previous, **wanted},
        "last_downloads": downloaded,
    }
    state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if downloaded:
        print(f"Updated {len(downloaded)} file(s):")
        for x in downloaded:
            print(f"  {x['path']}  {x['bytes']:,} bytes  {x['sha256'][:12]}…")
        print(f"Raw snapshot: {snapshot_dir}")
    else:
        print("No core WizPoints changes detected.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
