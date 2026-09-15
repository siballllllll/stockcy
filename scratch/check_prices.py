r"""백엔드 엔드포인트로만 현재가를 확인한다.

⚠️ toss_api를 직접 import하지 않는다 — 토큰을 새로 받으면 앱키당 하나뿐인 토큰 규칙
   때문에 **백엔드의 토큰이 무효화**된다(2026-09-15에 그렇게 고장 냈다).
"""
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = r'C:\Users\user\.gemini\스톡시'
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

from api.auth import create_token
import requests

tok = create_token('admin')
con = sqlite3.connect(os.path.join(ROOT, 'db.sqlite3'))
syms = [r[0] for r in con.execute(
    "SELECT DISTINCT ticker FROM confluence_log WHERE event_date >= date('now','-9 day') LIMIT 15")]
if not syms:
    syms = ['005930', '035420', 'GOOGL']

r = requests.get('http://127.0.0.1:8000/api/prices/toss-bulk?symbols=' + ','.join(syms),
                 headers={'Authorization': 'Bearer ' + tok}, timeout=60)
d = r.json() if r.status_code == 200 else {}
print(f'HTTP {r.status_code} — 요청 {len(syms)}종목 / 응답 {len(d)}건')
for k in syms:
    print(f'   {k:<8} {d.get(k, "— 없음")}')
