#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta

def rows(path, expected):
    result=[]
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        for n,line in enumerate(f,1):
            line=line.rstrip("\r\n")
            if not line: continue
            p=line.split("|")
            if len(p)!=expected:
                raise ValueError(f"{path}:{n}: expected {expected} fields, got {len(p)}")
            result.append(p)
    return result

def point_obj(p):
    return {
        "id": p[0], "name": p[1], "address": p[2], "postcode": p[3],
        "raw_fields": p[4:]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", default="knowledge-source/current/data")
    ap.add_argument("--output", default="knowledge-data.json")
    args=ap.parse_args()
    src=Path(args.input)

    pr=rows(src/"PointsInfo.txt",9)
    qr=rows(src/"Questions.txt",11)
    er=rows(src/"Examiners.txt",8)

    points={p[0]:point_obj(p) for p in pr}
    examiners={e[0]:{"id":e[0],"code":e[1],"display_name":e[2],"raw_fields":e[3:]} for e in er}

    questions=[]
    unresolved=Counter()
    appearances=defaultdict(list)
    for q in qr:
        start=points.get(q[6]); dest=points.get(q[7])
        if not start: unresolved[q[6]] += 1
        if q[7] != "0" and not dest: unresolved[q[7]] += 1
        obj={
            "question_id":q[0],
            "date":q[1],
            "examiner_id":q[2],
            "examiner":examiners.get(q[2]),
            "appearance_id":q[3],
            "appearance_note":q[4],
            "source_field_5":q[5],
            "start_point_id":q[6],
            "start_point":start,
            "destination_point_id":q[7],
            "destination_point":dest,
            "source_field_8":q[8],
            "source_field_9":q[9],
            "note":q[10],
        }
        questions.append(obj)
        appearances[(q[1],q[3])].append(obj)

    # Frequency counts are factual counts of occurrences in Questions.txt.
    valid_dates=[]
    for q in questions:
        try: valid_dates.append(datetime.strptime(q["date"],"%Y%m%d").date())
        except ValueError: pass
    latest=max(valid_dates) if valid_dates else None

    def freq(days=None):
        c=Counter()
        cutoff = latest-timedelta(days=days-1) if latest and days else None
        for q in questions:
            try: d=datetime.strptime(q["date"],"%Y%m%d").date()
            except ValueError: continue
            if cutoff and d < cutoff: continue
            for pid in (q["start_point_id"],q["destination_point_id"]):
                if pid and pid!="0": c[pid]+=1
        return c

    windows={"lifetime":freq()}
    if latest:
        windows.update({"30d":freq(30),"90d":freq(90),"12m":freq(365)})

    point_list=[]
    for pid,p in points.items():
        x=dict(p)
        x["question_frequency"]={k:v.get(pid,0) for k,v in windows.items()}
        point_list.append(x)

    app_list=[]
    for (date, aid), qs in appearances.items():
        app_list.append({
            "date":date, "appearance_id":aid,
            "examiner_id":qs[0]["examiner_id"],
            "examiner":qs[0]["examiner"],
            "appearance_note":qs[0]["appearance_note"],
            "source_field_5":qs[0]["source_field_5"],
            "questions":qs
        })

    data={
        "meta":{
            "generated_utc":datetime.utcnow().replace(microsecond=0).isoformat()+"Z",
            "source":"Knowledge source",
            "latest_question_date":latest.isoformat() if latest else None,
            "counts":{
                "points":len(points),"questions":len(questions),
                "appearances":len(app_list),"examiners":len(examiners),
                "unresolved_point_ids":len(unresolved)
            },
            "schema_note":"Unknown source columns are deliberately preserved as source_field_N/raw_fields rather than guessed."
        },
        "points":point_list,
        "examiners":list(examiners.values()),
        "appearances":sorted(app_list,key=lambda x:(x["date"],x["appearance_id"]),reverse=True),
        "unresolved_point_ids":dict(unresolved)
    }
    Path(args.output).write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(json.dumps(data["meta"],indent=2))

if __name__=="__main__":
    main()
