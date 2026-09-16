import fitz,re,json,sys
from datetime import datetime
POSTCODE=re.compile(r'\s+(?:EC|WC|E|N|NW|SE|SW|W)\d{1,2}[A-Z]?\s*$',re.I)

def clean(s):
    s=re.sub(r'\s+',' ',s).strip()
    s=POSTCODE.sub('',s).strip(' .')
    return s

def parse(path):
    doc=fitz.open(path); apps=[]; sheet_date=None
    for pageno,page in enumerate(doc):
        text=page.get_text()
        if not sheet_date:
            m=re.search(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',text)
            if m: sheet_date=datetime.strptime(' '.join(m.groups()),'%d %B %Y').date().isoformat()
        spans=[]
        for b in page.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                for sp in line['spans']:
                    spans.append({'text':sp['text'],'x0':sp['bbox'][0],'x1':sp['bbox'][2],'y':sp['bbox'][1],'size':sp['size']})
        # Headers
        headers=[]
        for sp in spans:
            # Appearance heading: examiner name sits at far left on the same line as
            # an appearance level (e.g. 56s/28s/21s). Do not whitelist names.
            if sp['x0'] < 60 and 7.4 < sp['size'] < 8.6 and sp['text'].strip():
                y=sp['y']; same=[z for z in spans if abs(z['y']-y)<1.5]
                level=' '.join(z['text'].strip() for z in same if 100<z['x0']<240).replace("'s",'s')
                grade=' '.join(z['text'].strip() for z in same if z['x0']>530)
                if re.search(r'\b(?:56|28|21)s\b', level, re.I):
                    headers.append((y,sp['text'].strip().title(),(level+' '+grade).strip()))
        headers.sort()
        # Question numbers are rendered separately at 4pt around x=26.
        qs=[]
        for sp in spans:
            t=sp['text'].strip()
            if sp['x0']<34 and 3.4<sp['size']<4.6 and t.isdigit():
                n=int(t)
                if 0<n<200: qs.append((sp['y'],n))
        qs=sorted(set(qs))
        for i,(qy,qn) in enumerate(qs):
            hs=[h for h in headers if h[0]<qy]
            if not hs: continue
            hy,exam,level=hs[-1]
            if 'Dropped' in level: continue
            nextq=qs[i+1][0] if i+1<len(qs) else 730
            nexth=min([h[0] for h in headers if h[0]>qy],default=730)
            bottom=min(nextq,nexth)-2.5
            fields={'start':[],'destination':[],'startAnswer':[],'destinationAnswer':[]}
            for sp in spans:
                if not (qy-3 <= sp['y'] < bottom and 7.4<sp['size']<8.6): continue
                # Logical fields are separate PDF spans. Classify by span centre, which
                # remains stable even when a long right-aligned answer extends leftward.
                cx=(sp['x0']+sp['x1'])/2
                if cx<150: key='start'
                elif cx<280: key='destination'
                elif cx<420: key='startAnswer'
                else: key='destinationAnswer'
                fields[key].append(sp)
            vals={}
            for key,arr in fields.items():
                arr.sort(key=lambda z:(round(z['y'],1),z['x0']))
                vals[key]=clean(' '.join(z['text'] for z in arr))
            if not vals['start'] or not vals['destination']: continue
            appkey=(pageno,hy,exam,level)
            if not apps or apps[-1]['_key']!=appkey:
                apps.append({'_key':appkey,'examiner':exam,'level':level,'questions':[]})
            vals['number']=qn
            apps[-1]['questions'].append(vals)
    for a in apps:a.pop('_key',None)
    # strict validation: every included question must have all four fields
    errors=[]
    for ai,a in enumerate(apps):
        for q in a['questions']:
            missing=[k for k in ('start','destination','startAnswer','destinationAnswer') if not q[k]]
            if missing: errors.append({'appearance':ai+1,'question':q['number'],'missing':missing})
    return {'date':sheet_date,'appearances':apps,'validation':{'ok':not errors,'errors':errors}}

if __name__=='__main__':
    print(json.dumps(parse(sys.argv[1]),indent=2,ensure_ascii=False))
