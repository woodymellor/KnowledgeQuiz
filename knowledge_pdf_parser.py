import fitz, re, json
from datetime import datetime

POSTCODE = re.compile(r'\s+(?:EC|WC|E|N|NW|SE|SW|W)\d{1,2}[A-Z]?\s*$', re.I)
LEVEL = re.compile(r'\b(?:56|28|21)s\b', re.I)

def clean(s):
    s = re.sub(r'\s+', ' ', s).strip()
    s = POSTCODE.sub('', s).strip(' .')
    return s

def parse(path):
    doc = fitz.open(path)
    apps, sheet_date = [], None

    for pageno, page in enumerate(doc):
        text = page.get_text()

        if not sheet_date:
            m = re.search(
                r'(?:Monday|Tuesday|Wednesday|Thursday|Friday)\s+'
                r'(\d{1,2})\s+'
                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
                r'(\d{4})', text
            )
            if m:
                sheet_date = datetime.strptime(' '.join(m.groups()), '%d %B %Y').date().isoformat()

        spans = []
        for b in page.get_text('dict')['blocks']:
            for line in b.get('lines', []):
                for sp in line['spans']:
                    spans.append({
                        'text': sp['text'],
                        'x0': sp['bbox'][0], 'x1': sp['bbox'][2],
                        'y': sp['bbox'][1], 'size': sp['size']
                    })

        # Dropped material is a separate section below the usable appearances.
        dropped_ys = [s['y'] for s in spans if re.search(r'\bDropped\b', s['text'], re.I)]
        dropped_y = min(dropped_ys) if dropped_ys else float('inf')

        # Appearance headings are detected structurally, not from examiner names.
        headers = []
        for sp in spans:
            if sp['x0'] < 60 and 7.4 < sp['size'] < 8.6 and sp['text'].strip():
                y = sp['y']
                same = [z for z in spans if abs(z['y'] - y) < 1.5]
                level = ' '.join(z['text'].strip() for z in same if 100 < z['x0'] < 240).replace("'s", "s")
                grade = ' '.join(z['text'].strip() for z in same if z['x0'] > 530)
                if LEVEL.search(level) and y < dropped_y:
                    headers.append((y, sp['text'].strip().title(), (level + ' ' + grade).strip()))
        headers.sort()

        qs = []
        for sp in spans:
            t = sp['text'].strip()
            if sp['x0'] < 34 and 3.4 < sp['size'] < 4.6 and t.isdigit():
                n = int(t)
                if 0 < n < 200 and sp['y'] < dropped_y:
                    qs.append((sp['y'], n))
        qs = sorted(set(qs))

        for i, (qy, qn) in enumerate(qs):
            hs = [h for h in headers if h[0] < qy]
            if not hs:
                continue
            hy, exam, level = hs[-1]

            later_qs = [y for y, _ in qs if y > qy]
            nextq = min(later_qs, default=730)
            nexth = min([h[0] for h in headers if h[0] > qy], default=730)
            bottom = min(nextq, nexth, dropped_y) - 2.5

            fields = {'start': [], 'destination': [], 'startAnswer': [], 'destinationAnswer': []}
            for sp in spans:
                if not (qy - 3 <= sp['y'] < bottom and 7.4 < sp['size'] < 8.6):
                    continue
                cx = (sp['x0'] + sp['x1']) / 2
                key = 'start' if cx < 150 else 'destination' if cx < 280 else 'startAnswer' if cx < 420 else 'destinationAnswer'
                fields[key].append(sp)

            vals = {}
            for key, arr in fields.items():
                arr.sort(key=lambda z: (round(z['y'], 1), z['x0']))
                vals[key] = clean(' '.join(z['text'] for z in arr))

            if not vals['start'] or not vals['destination']:
                continue
            if any(re.search(r'\bDropped\b', v, re.I) for v in vals.values()):
                continue

            appkey = (pageno, hy, exam, level)
            if not apps or apps[-1]['_key'] != appkey:
                apps.append({'_key': appkey, 'examiner': exam, 'level': level, 'questions': []})
            vals['number'] = qn
            apps[-1]['questions'].append(vals)

    for a in apps:
        a.pop('_key', None)

    errors = []
    for ai, a in enumerate(apps, 1):
        for q in a['questions']:
            missing = [k for k in ('start','destination','startAnswer','destinationAnswer') if not q[k]]
            if missing:
                errors.append({'appearance': ai, 'question': q['number'], 'missing': missing})

    return {'date': sheet_date, 'appearances': apps,
            'validation': {'ok': bool(sheet_date) and bool(apps) and not errors, 'errors': errors}}

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('-o', '--output', required=True)
    args = ap.parse_args()

    result = parse(args.pdf)
    if not result['validation']['ok']:
        raise SystemExit('ERROR: validation failed: ' + json.dumps(result['validation']['errors']))

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    n = sum(len(a['questions']) for a in result['appearances'])
    print(f"SUCCESS: {result['date']} - {len(result['appearances'])} appearances - {n} questions")
