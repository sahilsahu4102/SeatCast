import html
import re

from seatcast import cfg

PAT = re.compile(r'^(?P<base>.+?)(?P<dir>UP|DOWN)(?P<var>\d*)$')
RING = re.compile(r'^(?P<base>[A-Z0-9-]+?(?:EV)?)\s*\((?P<sign>[+-])\)(?P<rest>.*)$')
RING2 = re.compile(r'^(?P<base>[A-Z]+?)(?P<word>PLUS|MINUS)$')

ABBR = [(r'\bx[- ]?ing\b', 'crossing'), (r'\bxing\b', 'crossing'), (r'\(t\)', ' terminal'),
        (r'\bterm\b', 'terminal'), (r'\bsec\b', 'sector'), (r'\brly\b', 'railway'),
        (r'\bstn\b', 'station'), (r'\bmkt\b', 'market'), (r'\bngr\b', 'nagar'),
        (r'\bextn?\b', 'extension'), (r'\bopp\b', 'opposite'), (r'\bmore\b', 'mor'),
        (r'\bbdr\b', 'border'), (r'\bpkt\b', 'pocket'), (r'\b(?:apt|aptt|apts)\b', 'apartment'),
        (r'\brd\b', 'road'), (r'\bnr\b', 'near'), (r'\bhosp\b', 'hospital'),
        (r'\bjn\b', 'junction'), (r'\bph\b', 'phase')]

STD = {True: {9, 13.5, 18, 22.5}, False: {4.5, 9, 13.5}}
FULL = {True: {10, 15, 20, 25}, False: {5, 10, 15}}


def parse_route(code):
    c = code.strip().upper()
    m = PAT.match(c)
    if m:
        return m['base'], m['dir'], m['var']
    m = RING.match(c)
    if m:
        return m['base'] + m['rest'], 'CW' if m['sign'] == '+' else 'CCW', ''
    m = RING2.match(c)
    if m:
        return m['base'], 'CW' if m['word'] == 'PLUS' else 'CCW', ''
    return None


def norm(s):
    s = html.unescape(s).lower()
    s = re.sub(r'([a-z])(\d)', r'\1 \2', s)
    s = re.sub(r'(\d)([a-z])', r'\1 \2', s)
    for a, b in ABBR:
        s = re.sub(a, b, s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def fare_class(f, ac):
    f = round(f, 2)
    if f in STD[bool(ac)]:
        return 'std'
    k = (f - 22) / 4.5
    if f >= 22 and abs(k - round(k)) < 1e-6:
        return 'ncr'
    if f in FULL[bool(ac)]:
        return 'full'
    return 'other'


def daytype(d):
    d = d.date() if hasattr(d, 'date') else d
    if d.isoformat() in cfg()['holidays']:
        return 'sunday'
    for name, days in cfg()['daytypes'].items():
        if d.weekday() in days:
            return name


def anomalies(daily, thr=0.3):
    # daily: DataFrame with date, pax. Median over same daytype + weekday, after holiday reassignment.
    df = daily.copy()
    df['daytype'] = [daytype(d) for d in df['date']]
    df['dow'] = [d.weekday() for d in df['date']]
    med = df.groupby(['daytype', 'dow'])['pax'].transform('median')
    df['dev'] = df['pax'] / med - 1
    df['flag'] = df['dev'].abs() > thr
    return df
