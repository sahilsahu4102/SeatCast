import json
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from seatcast import OUT, ROOT, cfg

IMG = ROOT / 'docs' / 'img'
INK, GRID = '#222222', '#dddddd'
BLUE = '#2a78d6'
LEVELS = ['STANDING_ROOM_ONLY', 'CRUSHED_STANDING_ROOM_ONLY']
OP_COLS = ['route', 'hour', 'plus1_benefit', 'max_from', 'max_to', 'F_obs', 'F_req', 'gap_obs']
CELL_COLS = ['base', 'dir', 'k', 'from_name', 'to_name', 'slot', 'daytype', 'f', 'flag', 'level']
TMS = ('TMS(+)', 'UP')
TMS_MARKS = ['Maharani Bagh', 'Lajpat Nagar', 'AIIMS', 'Satya Niketan', 'Dhaula Kuan', 'COD Ring']  # stops named or implied by the Down To Earth article


def axes(title, xl, yl):
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=100)
    ax.set_title(title, loc='left', fontsize=11, color=INK)
    ax.set_xlabel(xl, color=INK)
    ax.set_ylabel(yl, color=INK)
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#999999')
    ax.tick_params(colors=INK, labelsize=9)
    return fig, ax


def save(fig, name):
    IMG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(IMG / name)
    plt.close(fig)


def peak_mask(df, hour, periods):
    m = pd.Series(False, index=df.index)
    for start, end in periods.values():
        m |= hour.ge(start) & hour.lt(end)
    return m


def tables(op, cells, e, k):
    top_n = k['findings']['top_n']
    wd = op[op['daytype'] == 'weekday'].copy()
    f1 = wd.nlargest(top_n, 'plus1_benefit').reset_index(drop=True)

    am, pm = k['periods']['am'], k['periods']['pm']
    f2 = []
    for name, (start, end) in [('Morning', am), ('Evening', pm)]:
        x = wd[wd['hour'].ge(start) & wd['hour'].lt(end)]
        f2.append({
            'period': name,
            'gap': x['gap_obs'].fillna(0).sum(),
            'short': int(x['gap_obs'].gt(0).sum()),
        })

    x = cells[cells['daytype'] == 'weekday'].copy()
    f3 = (x.groupby(['base', 'dir', 'from_name', 'to_name'], as_index=False)['f']
          .sum().assign(riders=lambda d: d['f'] * e / (2 * k['slot_window'] + 1))  # f pools 2w+1 slots; undo it
          .nlargest(top_n, 'riders').reset_index(drop=True))

    pub = cells[(cells['daytype'] == 'weekday') & cells['flag'].isna()].copy()
    pub['hour'] = pub['slot'] // (60 // k['slot_min'])
    pub['crowded'] = pub['level'].isin(LEVELS)
    f4 = (pub.groupby('hour', as_index=False)
          .agg(total=('level', 'size'), crowded=('crowded', 'sum')))
    f4['share'] = f4['crowded'] / f4['total']
    f4 = f4.set_index('hour').reindex(range(24))

    pub['peak'] = peak_mask(pub, pub['hour'], k['periods'])
    p = pub[pub['peak']]
    f5 = (p.groupby(['base', 'dir'], as_index=False)
          .agg(cells=('level', 'size'),
               crushed=('level', lambda s: s.eq('CRUSHED_STANDING_ROOM_ONLY').sum())))
    f5 = f5[f5['cells'] >= k['findings']['min_peak_cells']].copy()
    f5['share'] = f5['crushed'] / f5['cells']
    f5 = f5.nlargest(top_n, 'share').reset_index(drop=True)
    return f1, f2, f3, f4, f5


def tms_profile(cells, e, k):
    # weekday riders/day on each stretch of the TMS ring route, in route order (f pools 2w+1 slots; undo it)
    x = cells[(cells['base'] == TMS[0]) & (cells['dir'] == TMS[1]) & (cells['daytype'] == 'weekday')]
    return (x.groupby(['k', 'from_name', 'to_name'], as_index=False)['f'].sum()
            .assign(riders=lambda d: d['f'] * e / (2 * k['slot_window'] + 1)).sort_values('k').reset_index(drop=True))


def tms_story(p):
    # k of the first stretch whose name contains each marker; shape facts computed from the profile
    at = {m: int(p.loc[p['from_name'].str.contains(m, regex=False), 'k'].min()) for m in TMS_MARKS
          if p['from_name'].str.contains(m, regex=False).any()}
    if len(at) < len(TMS_MARKS):
        return None
    r = p.set_index('k')['riders']
    ks = p.set_index('k')['from_name']
    pk = r.loc[at['Maharani Bagh']:at['Dhaula Kuan']].idxmax()
    lo = r.loc[pk:at['Dhaula Kuan']].idxmin()
    hi = r.loc[at['Dhaula Kuan']:at['Dhaula Kuan'] + 6].max()
    return {'at': at, 'before': r.loc[at['Maharani Bagh'] - 1], 'mb': r.loc[at['Maharani Bagh']],
            'pk': pk, 'pk_name': ks.loc[pk], 'pk_r': r.loc[pk], 'lo_name': ks.loc[lo], 'lo_r': r.loc[lo], 'hi': hi}


def chart_hourly(f4):
    h = f4.index.to_numpy()
    share = f4['share'].to_numpy() * 100
    fig, ax = axes('Weekday peak crowding by hour', 'hour of day', 'published cells standing or crushed (%)')
    ax.plot(h, share, color=BLUE, lw=2, marker='o', markersize=3)
    ax.set_xticks(range(0, 24, 2))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.0f}%'))
    ax.set_ylim(bottom=0)
    save(fig, 'findings_hourly.png')


def chart_plus1(f1):
    labels = [f'{r.route} · {int(r.hour):02d}:00' for r in f1.itertuples()]
    values = f1['plus1_benefit'].to_numpy()
    fig, ax = axes('Route-hours ranked by benefit from one more bus', 'standee-minutes saved', '')
    y = range(len(f1))
    ax.barh(list(y), values[::-1], color=BLUE)
    ax.set_yticks(list(y), labels[::-1])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:,.0f}'))
    save(fig, 'findings_plus1.png')


def fmt(value, digits=0):
    if pd.isna(value):
        return '—'
    return f'{value:,.{digits}f}'


def report(f1, f2, f3, f4, f5, prof, e, k):
    am, pm = f2
    best = f1.iloc[0]
    busiest = f3.iloc[0]
    peak_h = f4['share'].idxmax()
    peak_share = f4.loc[peak_h, 'share']
    peak_n = f4.loc[peak_h, 'total']
    if len(f5):
        crushed = f5.iloc[0]
        f5_sentence = (f"Among routes with at least {k['findings']['min_peak_cells']} published peak cells, "
                       f"{crushed['base']} {crushed['dir']} had the highest crushed share: "
                       f"{crushed['share']:.1%} ({fmt(crushed['crushed'])} of {fmt(crushed['cells'])} cells).")
    else:
        f5_sentence = (f"No route had at least {k['findings']['min_peak_cells']} published weekday peak cells.")

    s = ['# Operator Findings', '',
         '## Finding F1 — Where one more bus helps most', '',
         (f"The highest +1-bus benefit is on {best['route']} at {int(best['hour']):02d}:00, "
          f"where {best['max_from']} to {best['max_to']} ran {fmt(best['F_obs'], 1)} buses/hour "
          f"against {fmt(best['F_req'])} needed."), '',
         '| Route | Hour | Busiest stretch | Ran → needed (buses/hour) | +1-bus benefit (standee-minutes) |',
         '|---|---:|---|---:|---:|']
    for r in f1.itertuples():
        s.append(f'| {r.route} | {int(r.hour):02d}:00 | {r.max_from} → {r.max_to} | '
                 f'{fmt(r.F_obs, 1)} → {fmt(r.F_req)} | {fmt(r.plus1_benefit, 1)} |')
    s += ['', '![Top route-hours by +1-bus benefit](img/findings_plus1.png)', '',
          '## Finding F2 — Weekday peak service shortfall', '',
          (f"Observed service falls short in {fmt(am['short'])} morning and {fmt(pm['short'])} evening "
           f"route-hours, with summed shortfalls of {fmt(am['gap'], 1)} and {fmt(pm['gap'], 1)} bus-hours, respectively."), '',
          '| Peak | Summed shortfall (bus-hours) | Short route-hours |',
          '|---|---:|---:|']
    for x in f2:
        s.append(f"| {x['period']} | {fmt(x['gap'], 1)} | {fmt(x['short'])} |")
    s += ['', '## Finding F3 — Busiest passenger stretches', '',
          (f"The busiest estimated weekday stretch is {busiest['base']} {busiest['dir']}, "
           f"{busiest['from_name']} → {busiest['to_name']}, at {fmt(busiest['riders'])} riders/day "
           f"(using expansion factor E = {fmt(e, 2)})."), '',
          '| Base | Direction | From → to | Estimated riders/day |',
          '|---|---|---|---:|']
    for r in f3.itertuples():
        s.append(f'| {r.base} | {r.dir} | {r.from_name} → {r.to_name} | {fmt(r.riders)} |')
    s += ['', '## Finding F4 — Crowded share by hour', '',
          (f"The highest weekday hourly crowded share is {peak_share:.1%} at {int(peak_h):02d}:00 "
           f"({fmt(f4.loc[peak_h, 'crowded'])} of {fmt(peak_n)} published cells)."), '',
          '![Published weekday cells at standing or crushed level by hour](img/findings_hourly.png)', '',
          '| Hour | Published cells | Standing or crushed | Share |',
          '|---:|---:|---:|---:|']
    for h, r in f4.iterrows():
        s.append(f'| {h:02d}:00 | {fmt(r["total"])} | {fmt(r["crowded"])} | '
                 f'{r["share"]:.1%} |' if pd.notna(r['total']) else f'| {h:02d}:00 | — | — | — |')
    s += ['', '## Finding F5 — Routes most often crushed in peak cells', '',
          f5_sentence, '',
          '| Base | Direction | Published peak cells | Crushed cells | Crushed share |',
          '|---|---|---:|---:|---:|']
    for r in f5.itertuples():
        s.append(f'| {r.base} | {r.dir} | {fmt(r.cells)} | {fmt(r.crushed)} | {r.share:.1%} |')
    s += ['', 'Caveat: sizes at the peak carry the uncertainty described in TECH_NOTE §8; the ranking is the robust part.', '']
    st = tms_story(prof)
    s += ['## Outside check', '',
          ('The one public source we found with a route-level passenger pattern is a Down To Earth report on a DTC '
           'experiment on the TMS ring route, which it calls "one of the most popular bus routes in Delhi". '
           'An on-bus passenger count showed that on the up direction Maharani Bagh and Lajpat Nagar are high boarding stops, '
           'that "the passenger count dropped by half at the AIIMS stop", and that it "started to increase again after Dhaula Kuan".'), '']
    if st:
        s += [(f"SeatCast's weekday flow on TMS(+) UP has the same shape. It rises from {fmt(st['before'])} to {fmt(st['mb'])} riders/day "
               f"at Maharani Bagh, peaks at {st['pk_name']} ({fmt(st['pk_r'])}), falls to a low of {fmt(st['lo_r'])} at {st['lo_name']} "
               f"({(st['lo_r'] / st['pk_r'] - 1):.0%}), then rises again to {fmt(st['hi'])} within six stretches of Dhaula Kuan "
               f"({(st['hi'] / st['lo_r'] - 1):+.0%} from the low). The direction and stops broadly agree; the published drop is larger, "
               f"and the two measure different things: the survey counted riders on board, we count app tickets scaled to all riders (E = {fmt(e, 2)})."), '',
              '| Stretch starts at | Order on route | Estimated weekday riders/day |', '|---|---:|---:|']
        for m, kk in st['at'].items():
            row = prof[prof['k'] == kk].iloc[0]
            s.append(f"| {row['from_name']} | {kk} | {fmt(row['riders'])} |")
        s.append('')
    else:
        s += ['The TMS stretches could not be matched by name in this build, so no profile comparison is shown.', '']
    s += [('**Top-ten overlap:** not computable. Neither that report nor the GNCTD route-rationalization notice publishes a '
           'ranking of routes by ridership, and we do not substitute our own.'), '',
          'Sources: [Down To Earth, DTC route-curtailment pilot](https://www.downtoearth.org.in/energy/'
          'dtc-pilots-one-bus-route-design-to-demonstrate-improved-services-and-passengers); '
          '[GNCTD Transport Department, route-rationalization public notice]'
          '(https://transport.delhi.gov.in/sites/default/files/Transport/circulars-orders/'
          'public_notice_route_rationalization.pdf).', '']
    return '\n'.join(s)


def run():
    t0 = time.time()
    k = cfg()
    op = pd.read_parquet(OUT / 'operator.parquet', columns=OP_COLS + ['daytype'])
    cells = pd.read_parquet(OUT / 'cells.parquet', columns=CELL_COLS)
    cov = json.loads((OUT / 'coverage.json').read_text(encoding='utf-8'))
    e = cov['load']['E']['central']
    f1, f2, f3, f4, f5 = tables(op, cells, e, k)
    prof = tms_profile(cells, e, k)
    chart_hourly(f4)
    chart_plus1(f1)
    md = report(f1, f2, f3, f4, f5, prof, e, k)
    p = ROOT / 'docs' / 'FINDINGS.md'
    p.write_text(md, encoding='utf-8')
    print(f'findings: {p.relative_to(ROOT)} written ({time.time() - t0:.1f}s)')
