"""V32 — Gemini 현행 vs 신형 그림자 기록을 시장 대비로 채점(과금 0). VERIFY.md V32 참조.
실행: venv/Scripts/python scratch/grade_gemini_shadow.py"""
import json, re, sys, collections, statistics as st, random
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
import FinanceDataReader as fdr, yfinance as yf

FEE = {'kr': .21, 'us': .15}
HS = (1, 3, 5, 7)
LAST = date.today() - timedelta(days=1)   # 오늘 봉은 장중일 수 있어 뺀다

rows = [json.loads(l) for l in open('data_csv/model_shadow.jsonl', encoding='utf-8')]
R = [x for x in rows if x['provider'] == 'gemini' and x['source'] == 'run_research_watch' and x.get('shadow_ok')]


def P(t):
    t = re.sub(r'^```(json)?', '', t.strip()).strip()
    t = re.sub(r'```$', '', t).strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, list) else None
    except Exception:
        return None


_ls = fdr.StockListing('KRX')
_code = dict(zip(_ls['Code'], _ls['Name']))
_byname = dict(zip(_ls['Name'], _ls['Code']))
codechk = collections.Counter()
picks, skipped, calls = [], collections.Counter(), 0
for x in R:
    a, b = P(x['primary_text']), P(x['shadow_text'])
    if a is None or b is None:
        skipped['unparsable_call'] += 1
        continue
    calls += 1
    for model, d in (('old', a), ('new', b)):
        for i in d:
            dr = i.get('direction')
            for s in i.get('stocks') or []:
                t = str(s.get('ticker') or '').strip().upper()
                nm = str(s.get('name') or '').strip()
                # 이름이 상장 목록에 있으면 이름이 기준 — 코드가 틀려도 양쪽 똑같이 교정한다
                if nm in _byname:
                    codechk[(model, '코드 맞음' if t == _byname[nm] else '코드 틀림')] += 1
                    t = _byname[nm]
                elif re.fullmatch(r'\d{6}', t):
                    codechk[(model, '이름 미확인(코드만 상장)' if t in _code else '이름·코드 모두 없음')] += 1
                if re.fullmatch(r'\d{6}|\d[0-9A-Z]{4}\d|\d{4}[0-9A-Z]\d', t) or re.fullmatch(r'\d{4}[A-Z]\d', t):
                    mk = 'kr'
                elif re.fullmatch(r'[A-Z]{1,5}([.\-][A-Z])?', t):
                    mk = 'us'
                    t = t.replace('.', '-')
                else:
                    skipped[model + '_bad_ticker'] += 1
                    continue
                picks.append(dict(ts=x['ts'], model=model, t=t, mk=mk, dir=dr))
tks = {(p['t'], p['mk']) for p in picks}
print('calls', calls, 'picks', len(picks), 'tickers', len(tks), dict(skipped))
print('코드 점검', sorted(codechk.items()))

px = {}


def get(t, mk):
    if mk == 'kr':
        df = fdr.DataReader(t, '2026-10-01')
    else:
        df = yf.download(t, start='2026-10-01', progress=False, timeout=15, auto_adjust=False)
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
    return df[['Open', 'Close']].dropna()


def job(k):
    t, mk = k
    if mk == 'idx':
        return k, fdr.DataReader('KS11', '2026-10-01')[['Open', 'Close']].dropna()
    if mk == 'idxus':
        return k, get('^GSPC', 'us')
    return k, get(t, mk)


todo = [k for k in tks | {('KS11', 'idx'), ('^GSPC', 'idxus')} if k not in px]
fail = []
with ThreadPoolExecutor(8) as ex:
    fs = [ex.submit(job, k) for k in todo]
    for f in as_completed(fs, timeout=1200):
        try:
            k, df = f.result()
            px[k] = df
        except Exception as e:
            fail.append(str(e)[:50])
print('fetched', len(todo), 'fail', len(fail), collections.Counter(fail).most_common(3))
print('KS11 last', [str(x.date()) for x in px[('KS11', 'idx')].index[-3:]],
      'SPX last', [str(x.date()) for x in px[('^GSPC', 'idxus')].index[-3:]])


def entry(df, ts, mk):
    # 등장 순간 시세 기록이 없다 — 장 전=당일 시가, 장중=당일 종가(원장의 시세 없음 대체), 마감 뒤=다음날 시가
    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
    if mk == 'kr':
        d, hm = dt.date(), dt.hour * 60 + dt.minute
        lo, hi = 540, 930
    else:
        ld = dt - timedelta(hours=14)
        d, hm = ld.date(), ld.hour * 60 + ld.minute
        lo, hi = 510, 900   # 미국 정규장 근사
    if hm < lo:
        mode = 'open'
    elif hm < hi:
        mode = 'close'
    else:
        d += timedelta(days=1)
        mode = 'open'
    idx = [i for i, x in enumerate(df.index) if x.date() >= d]
    if not idx:
        return None
    i = idx[0]
    if df.index[i].date() != d:
        mode = 'open'
    return i, mode, float(df['Open'].iloc[i] if mode == 'open' else df['Close'].iloc[i])


seen = {}
for p in sorted(picks, key=lambda x: x['ts']):
    seen.setdefault((p['model'], p['ts'][:10], p['t'], p['dir']), p)
U = list(seen.values())
sets = collections.defaultdict(set)
for p in U:
    sets[(p['model'], p['ts'][:10], p['dir'])].add(p['t'])

out, noprice = [], collections.Counter()
for p in U:
    df = px.get((p['t'], p['mk']))
    other = 'new' if p['model'] == 'old' else 'old'
    p['both'] = p['t'] in sets[(other, p['ts'][:10], p['dir'])]
    if df is None or df.empty:
        noprice[p['model']] += 1
        continue
    e = entry(df, p['ts'], p['mk'])
    if not e:
        noprice[p['model'] + '_noentry'] += 1
        continue
    i, mode, base = e
    b = px[('KS11', 'idx')] if p['mk'] == 'kr' else px[('^GSPC', 'idxus')]
    d0 = df.index[i]
    if base <= 0 or d0 not in b.index:
        noprice[p['model'] + '_nobench'] += 1
        continue
    bi = b.index.get_loc(d0)
    bbase = float(b['Open'].iloc[bi] if mode == 'open' else b['Close'].iloc[bi])
    p['mom5'] = (float(df['Close'].iloc[i - 1]) / float(df['Close'].iloc[i - 6]) - 1) * 100 if i >= 6 else None
    for h in HS:
        p[f'x{h}'] = p[f'w{h}'] = None
        if i + h < len(df) and bi + h < len(b) and df.index[i + h].date() <= LAST and b.index[bi + h] == df.index[i + h]:
            r = (float(df['Close'].iloc[i + h]) / base - 1) * 100
            br = (float(b['Close'].iloc[bi + h]) / bbase - 1) * 100
            p[f'x{h}'] = r - br
            fee = FEE[p['mk']]
            p[f'w{h}'] = (r - br > fee) if p['dir'] != '부정' else (r - br < -fee)
    out.append(p)
print('unique', len(U), 'scored', len(out), 'noprice', dict(noprice))


def S(v, h):
    w, x = f'w{h}', f'x{h}'
    v = [p for p in v if p.get(w) is not None]
    if not v:
        return f'd{h} n=0'
    return (f"d{h} n={len(v):4} 승률 {100 * sum(p[w] for p in v) / len(v):5.1f}% "
            f"평균 {st.mean(p[x] for p in v):+6.2f} 중앙 {st.median(p[x] for p in v):+6.2f}")


GROUPS = (('현행 전체', lambda p: p['model'] == 'old'), ('신형 전체', lambda p: p['model'] == 'new'),
          ('둘다 고른', lambda p: p['both'] and p['model'] == 'old'),
          ('현행만', lambda p: p['model'] == 'old' and not p['both']),
          ('신형만', lambda p: p['model'] == 'new' and not p['both']))


def block(title, flt):
    print('\n==' + title)
    for name, f2 in GROUPS:
        v = [p for p in out if flt(p) and f2(p)]
        print(f'{name:6}', ' | '.join(S(v, h) for h in HS))


pos = lambda p: p['dir'] == '긍정'
nochase = lambda p: p['dir'] == '긍정' and not (p.get('mom5') is not None and p['mom5'] >= 10)
block('긍정 전체', pos)
block('긍정 급등 제외 (원장 큰 숫자 기준)', nochase)
block('부정 (더 빠져야 적중)', lambda p: p['dir'] == '부정')
block('긍정 급등제외 국내', lambda p: nochase(p) and p['mk'] == 'kr')
block('긍정 급등제외 미국', lambda p: nochase(p) and p['mk'] == 'us')

print('\n==날짜별 (긍정 급등제외, d3 승률)')
for d in sorted({p['ts'][:10] for p in out}):
    a = [p for p in out if nochase(p) and p['ts'][:10] == d and p['model'] == 'old' and p.get('w3') is not None]
    b = [p for p in out if nochase(p) and p['ts'][:10] == d and p['model'] == 'new' and p.get('w3') is not None]
    if a and b:
        print(d, f"현행 {len(a)}건 {100 * sum(p['w3'] for p in a) / len(a):.1f}% / 신형 {len(b)}건 {100 * sum(p['w3'] for p in b) / len(b):.1f}%")

for h in (1, 3, 5):
    w = f'w{h}'
    a = [p for p in out if nochase(p) and p['model'] == 'old' and not p['both'] and p.get(w) is not None]
    b = [p for p in out if nochase(p) and p['model'] == 'new' and not p['both'] and p.get(w) is not None]
    ta, tb = collections.defaultdict(list), collections.defaultdict(list)
    for p in a:
        ta[p['t']].append(p)
    for p in b:
        tb[p['t']].append(p)
    ka, kb = list(ta), list(tb)
    if not ka or not kb:
        continue
    random.seed(1)
    ds = []
    for _ in range(2000):
        xa = [p for t in random.choices(ka, k=len(ka)) for p in ta[t]]
        xb = [p for t in random.choices(kb, k=len(kb)) for p in tb[t]]
        ds.append(sum(p[w] for p in xb) / len(xb) - sum(p[w] for p in xa) / len(xa))
    ds.sort()
    diff = sum(p[w] for p in b) / len(b) - sum(p[w] for p in a) / len(a)
    print(f'd{h} 신형만-현행만 승률차 {100 * diff:+.1f}%p 95%CI [{100 * ds[50]:+.1f}, {100 * ds[1949]:+.1f}] 고유종목 {len(ka)}/{len(kb)}')
