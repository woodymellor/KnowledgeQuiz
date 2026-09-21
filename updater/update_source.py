#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, shutil, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://wizann.uk/apps/wizpoints/"
MANIFEST = urllib.parse.urljoin(BASE, "timestamps-v2.php")
UA = "KnowledgeSourceUpdater/1.0"

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=30) as r: return r.read()

def parse_manifest(raw):
    text=raw.decode("utf-8",errors="replace")
    text=re.sub(r"<br\s*/?>","",text,flags=re.I)
    text=re.sub(r"<[^>]+>","",text)
    starts=[m.start() for m in re.finditer(r"data/",text)]
    out={}
    for i,pos in enumerate(starts):
        chunk=text[pos:starts[i+1] if i+1<len(starts) else len(text)]
        m=re.match(r"(.+)\|(\d+)\s*$",chunk)
        if m: out[m.group(1).strip()]=m.group(2)
    if not out: raise RuntimeError("Could not parse source manifest.")
    return out

def safe_path(rel):
    p=Path(rel.replace("\\","/"))
    if p.is_absolute() or ".." in p.parts: raise ValueError(f"Unsafe source path: {rel}")
    return p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="knowledge-source")
    args=ap.parse_args()
    root=Path(args.root); current=root/"current"; snapshots=root/"snapshots"
    state_file=root/"state.json"; root.mkdir(parents=True,exist_ok=True)
    previous={}
    if state_file.exists():
        previous=json.loads(state_file.read_text(encoding="utf-8")).get("timestamps",{})

    raw=fetch(MANIFEST); manifest=parse_manifest(raw)
    core={"data/Questions.txt","data/PointsInfo.txt","data/Examiners.txt"}
    wanted={k:v for k,v in manifest.items() if k in core}
    if len(wanted)!=3: raise RuntimeError("Expected three core source files.")

    changed={p:t for p,t in wanted.items() if previous.get(p)!=t}
    if not changed:
        print("No Knowledge Source changes detected.")
        return

    now=datetime.now(timezone.utc); stamp=now.strftime("%Y%m%dT%H%M%SZ")
    snapshot=snapshots/stamp; downloaded=[]
    for rel,server_stamp in changed.items():
        data=fetch(urllib.parse.urljoin(BASE,rel)); relpath=safe_path(rel)
        snap=snapshot/relpath; snap.parent.mkdir(parents=True,exist_ok=True); snap.write_bytes(data)
        dest=current/relpath; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(snap,dest)
        downloaded.append({"path":rel,"server_timestamp":server_stamp,"bytes":len(data),
                           "sha256":hashlib.sha256(data).hexdigest()})

    manifests=root/"manifests"; manifests.mkdir(exist_ok=True)
    (manifests/f"{stamp}.txt").write_bytes(raw)
    state={"updated_at_utc":now.isoformat(),"timestamps":{**previous,**wanted},
           "last_downloads":downloaded}
    state_file.write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    print(f"Updated {len(downloaded)} Knowledge Source file(s).")

if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr); raise SystemExit(1)
