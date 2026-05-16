"""pykrx 5분봉 지원 여부 탐색"""
import inspect
from pykrx import stock as krx

# pykrx stock 모듈에서 분봉/intraday 관련 함수 탐색
funcs = [name for name in dir(krx) if "min" in name.lower() or "minute" in name.lower()
         or "intra" in name.lower() or "tick" in name.lower() or "time" in name.lower()
         or "chart" in name.lower() or "ohlcv" in name.lower()]
print("=== pykrx functions with ohlcv/minute/tick/intra/time/chart ===")
for f in funcs:
    print(" ", f)

# get_market_ohlcv 시그니처 확인
print("\n=== get_market_ohlcv signature ===")
try:
    print(inspect.signature(krx.get_market_ohlcv))
except Exception as e:
    print(e)

# 실제 호출 테스트: 삼성전자 5분봉 (가능하다면)
print("\n=== 실제 5분봉 조회 시도: 005930, 20240101~20240102 ===")
try:
    df = krx.get_market_ohlcv("20240101", "20240102", "005930", freq="T")
    print("freq='T' 결과 shape:", df.shape)
    print(df.head(3))
except Exception as e:
    print("freq='T' 실패:", type(e).__name__, str(e)[:120])

try:
    df = krx.get_market_ohlcv("20240101", "20240102", "005930", freq="5T")
    print("freq='5T' 결과 shape:", df.shape)
except Exception as e:
    print("freq='5T' 실패:", type(e).__name__, str(e)[:120])

# pykrx 버전
import pykrx
print("\npykrx version:", pykrx.__version__)
