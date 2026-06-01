"""외부 시세 소스(yfinance/FDR) 장애 시 동기 스레드풀 고갈을 막는 경량 서킷 브레이커.

문제: yfinance/FDR이 네트워크 장애로 응답을 못 주면, 각 요청이 예외가 나기 전까지
오래 매달려 FastAPI 동기 스레드풀(def 엔드포인트용)을 점유한다. 동시 요청이 풀 한도를
넘으면 /api/health 같은 단순 엔드포인트까지 큐에 막혀 앱 전체가 멈춘 것처럼 보인다.

해결: 연속 실패가 임계치를 넘으면 cooldown 동안 호출을 '즉시 실패'(fail-fast)시켜
스레드 점유 자체를 차단한다. cooldown이 지나면 한 번 시도해보고, 성공하면 정상 복귀한다.
"""
import time
import threading


class CircuitBreaker:
    def __init__(self, name: str, fail_threshold: int = 5, cooldown: float = 45.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self._fails = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """True면 회로 개방(호출 건너뜀). cooldown이 지나면 자동으로 False가 되어 1회 시도 허용."""
        with self._lock:
            return time.time() < self._open_until

    def record_success(self):
        with self._lock:
            self._fails = 0
            self._open_until = 0.0

    def record_failure(self):
        with self._lock:
            self._fails += 1
            if self._fails >= self.fail_threshold:
                # 임계치 도달 → cooldown 동안 개방. (cooldown 후 단발 실패에도 즉시 재개방)
                self._open_until = time.time() + self.cooldown

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "open": time.time() < self._open_until,
                "fails": self._fails,
                "reopen_in": round(max(0.0, self._open_until - time.time()), 1),
            }


# 공용 인스턴스 — yfinance 계열 외부 호출에 공유
yf_breaker = CircuitBreaker("yfinance")
