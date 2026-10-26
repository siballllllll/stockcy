"""모델 그림자 비교 (v3.209.0) — 신형 모델에 같은 질문을 몰래 한 번 더 던져 나란히 기록.

목적: 실사용 모델(gemini-2.5-flash · gpt-4o-mini)은 2024~25년 세대다. 신형으로 바꾸면
판단 성향이 바뀌어(10-26 실측: 같은 질문에 2.5-flash만 BUY, 신형 전부 HOLD) 적중률·ML
학습셋의 연속성이 끊기므로, 바꾸기 전에 "얼마나 다르게 답하나 / 얼마나 비싸고 느린가"를
실제 호출 그대로 측정한다.

원칙:
- 실행에는 절대 안 쓴다. 메인 응답은 이미 반환된 뒤 데몬 스레드에서 따로 호출하고,
  결과는 data_csv/model_shadow.jsonl 에만 쌓인다.
- 메인 경로(_call_gemini/_call_openai)를 거치지 않고 SDK를 직접 부른다 — 그림자 쪽 429가
  메인의 할당량 백오프(_QUOTA_BLOCK_UNTIL)를 켜거나, 메인의 모델 폴백을 타면 안 되기 때문.
- 비용은 진짜로 나가므로 ai_usage.jsonl 에도 source="shadow:<기능>"으로 남긴다(합계가 맞도록).
- 하루 프로바이더별 상한(MODEL_SHADOW_DAILY_CAP) + 동시 실행 상한으로 폭주를 막는다.

설정(.env, 없으면 기본값):
    MODEL_SHADOW=1                    0이면 끔
    MODEL_SHADOW_GEMINI=gemini-3.8-flash
    MODEL_SHADOW_OPENAI=gpt-6-luna
    MODEL_SHADOW_OPENAI_EFFORT=low    추론형 모델 reasoning_effort (빈 값이면 안 보냄)
    MODEL_SHADOW_DAILY_CAP=200

보고서:  venv/Scripts/python model_shadow.py [일수]
"""
import json
import os
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

_BASE = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.path.join(_BASE, "data_csv", "model_shadow.jsonl")
_TEXT_LIMIT = 6000          # 응답 원문 보관 길이 (리서치 감시 응답이 길어 파일이 커지는 것 방지)
_TIMEOUT_SEC = 120
_MAX_CONCURRENT = 3

_slots = threading.BoundedSemaphore(_MAX_CONCURRENT)
_count_lock = threading.Lock()
_daily = {"date": None, "counts": Counter(), "dropped": Counter()}
_write_lock = threading.Lock()


def _enabled() -> bool:
    return os.getenv("MODEL_SHADOW", "1").strip() not in ("0", "false", "off", "")


def _candidate(provider: str) -> str:
    if provider == "gemini":
        return os.getenv("MODEL_SHADOW_GEMINI", "gemini-3.8-flash").strip()
    return os.getenv("MODEL_SHADOW_OPENAI", "gpt-6-luna").strip()


def _take_quota(provider: str) -> bool:
    cap = int(os.getenv("MODEL_SHADOW_DAILY_CAP", "200") or 200)
    today = datetime.now().strftime("%Y-%m-%d")
    with _count_lock:
        if _daily["date"] != today:
            _daily.update(date=today, counts=Counter(), dropped=Counter())
        if _daily["counts"][provider] >= cap:
            _daily["dropped"][provider] += 1
            return False
        _daily["counts"][provider] += 1
        return True


def maybe_shadow(provider: str, primary_model: str, primary_text: str, primary_latency: float,
                 primary_cost: float, prompt: str, source: str, use_search: bool = False,
                 temperature: float = 0.7, response_mime_type=None, max_output_tokens=8000,
                 thinking: bool = False):
    """메인 호출 성공 직후 불린다. 조건이 맞으면 그림자 호출을 백그라운드로 띄우고 즉시 반환.
    어떤 예외도 메인으로 올리지 않는다."""
    held = False
    try:
        if not _enabled() or not prompt:
            return
        if str(source or "").startswith("shadow:"):
            return
        shadow_model = _candidate(provider)
        if not shadow_model or shadow_model in str(primary_model):
            return  # 이미 신형으로 돌고 있으면 비교할 게 없다
        if not _slots.acquire(blocking=False):
            with _count_lock:
                _daily["dropped"][provider] += 1
            return
        held = True
        if not _take_quota(provider):
            _slots.release()
            return
        primary = {"model": primary_model, "text": primary_text or "",
                   "latency": round(float(primary_latency or 0), 3), "cost": float(primary_cost or 0)}
        opts = {"use_search": bool(use_search), "temperature": temperature,
                "response_mime_type": response_mime_type, "max_output_tokens": max_output_tokens,
                "thinking": bool(thinking)}
        threading.Thread(target=_run, args=(provider, shadow_model, prompt, source, primary, opts),
                         daemon=True, name="model-shadow").start()
        held = False  # 이제 스레드가 반납한다
    except Exception:
        if held:
            _slots.release()


def _run(provider, shadow_model, prompt, source, primary, opts):
    try:
        t0 = time.perf_counter()
        err = None
        res = None
        try:
            if provider == "gemini":
                res = _call_gemini_shadow(shadow_model, prompt, opts, source)
            else:
                res = _call_openai_shadow(shadow_model, prompt, opts, source)
        except Exception as e:
            err = str(e)[:300]
        lat = round(time.perf_counter() - t0, 3)
        _record(provider, source, prompt, primary, shadow_model, res, lat, err, opts)
    except Exception:
        pass
    finally:
        _slots.release()


def _call_gemini_shadow(model, prompt, opts, source):
    from google import genai
    from google.genai import types
    import ai_engine

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""),
                          http_options={"api_version": "v1alpha", "timeout": _TIMEOUT_SEC * 1000})
    kw = {"temperature": opts["temperature"]}
    if opts["max_output_tokens"]:
        kw["max_output_tokens"] = opts["max_output_tokens"]
    if opts["use_search"]:
        kw["tools"] = [{"google_search": {}}]
    elif opts["response_mime_type"]:
        kw["response_mime_type"] = opts["response_mime_type"]
    # 메인과 같은 비용 방어(thinking 기본 차단). 3.8-flash는 budget=0을 받는다(10-26 실측).
    kw["thinking_config"] = types.ThinkingConfig(
        thinking_budget=(ai_engine._THINKING_BUDGET_ON if opts["thinking"] else 0))
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=model, contents=prompt,
                                          config=types.GenerateContentConfig(**kw))
    ai_engine._log_llm_usage(resp, f"shadow:{source}", use_search=opts["use_search"],
                             provider="gemini", latency_sec=time.perf_counter() - t0)
    um = getattr(resp, "usage_metadata", None)
    in_t = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
    out_t = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
    think_t = int(getattr(um, "thoughts_token_count", 0) or 0) if um else 0
    mdl = str(getattr(resp, "model_version", "") or model)
    return {"text": getattr(resp, "text", "") or "", "model": mdl, "in": in_t, "out": out_t + think_t,
            "cost": ai_engine._calc_estimated_cost("gemini", mdl, in_t, out_t + think_t)}


def _call_openai_shadow(model, prompt, opts, source):
    """신형(추론형) 모델은 4o-mini와 파라미터가 다르다(10-26 실측, gpt-6-luna):
    temperature 거부 · max_tokens 대신 max_completion_tokens(추론 토큰 포함) ·
    웹검색과 JSON 모드 동시 사용 불가. 그래서 거부되면 그 파라미터만 떼고 다시 보낸다."""
    import ai_engine

    client = ai_engine._get_openai_client()
    want_json = opts["response_mime_type"] == "application/json" or "json" in prompt.lower()
    effort = os.getenv("MODEL_SHADOW_OPENAI_EFFORT", "low").strip()
    t0 = time.perf_counter()
    if opts["use_search"]:
        kw = {"model": model, "tools": [{"type": "web_search"}], "timeout": _TIMEOUT_SEC,
              "input": prompt + ("\n\n[출력 형식] 인사말·설명·마크다운 코드펜스 없이 "
                                 "**JSON 객체 하나만** 출력하라." if want_json else "")}
        if opts["max_output_tokens"]:
            kw["max_output_tokens"] = opts["max_output_tokens"]
        if effort:
            kw["reasoning"] = {"effort": effort}
        resp = _retry_without_rejected(client.responses.create, kw)
        text = getattr(resp, "output_text", "") or ""
        usage = getattr(resp, "usage", None)
        in_t = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        out_t = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
    else:
        kw = {"model": model, "messages": [{"role": "user", "content": prompt}],
              "temperature": opts["temperature"], "timeout": _TIMEOUT_SEC}
        if opts["max_output_tokens"]:
            kw["max_completion_tokens"] = opts["max_output_tokens"]
        if want_json:
            kw["response_format"] = {"type": "json_object"}
        if effort:
            kw["reasoning_effort"] = effort
        resp = _retry_without_rejected(client.chat.completions.create, kw)
        text = resp.choices[0].message.content or ""
        in_t = int(getattr(resp.usage, "prompt_tokens", 0) or 0)
        out_t = int(getattr(resp.usage, "completion_tokens", 0) or 0)
    lat = time.perf_counter() - t0
    mdl = getattr(resp, "model", model)
    ai_engine._log_llm_usage(
        ai_engine.LLMResponse(text=text, model=mdl, in_tokens=in_t, out_tokens=out_t, latency_sec=lat,
                              provider="openai", search_used=opts["use_search"], raw_response=resp),
        f"shadow:{source}", use_search=opts["use_search"], provider="openai", latency_sec=lat)
    return {"text": text, "model": mdl, "in": in_t, "out": out_t,
            "cost": ai_engine._calc_estimated_cost("openai", mdl, in_t, out_t)}


def _retry_without_rejected(fn, kw, tries=3):
    """400 'Unsupported parameter: X'면 X만 빼고 재시도."""
    for _ in range(tries):
        try:
            return fn(**kw)
        except Exception as e:
            msg = str(e)
            dropped = False
            for p in ("temperature", "reasoning_effort", "reasoning", "response_format", "max_completion_tokens"):
                if p in kw and f"'{p}'" in msg:
                    kw.pop(p)
                    dropped = True
                    break
            if not dropped:
                raise
    return fn(**kw)


def _parse(text):
    try:
        import ai_engine

        class _R:
            pass
        r = _R()
        r.text = text
        return ai_engine._parse_json_response(r)
    except Exception:
        return None


def _record(provider, source, prompt, primary, shadow_model, res, shadow_latency, err, opts):
    p_json = _parse(primary["text"])
    s_json = _parse(res["text"]) if res else None
    p_act = p_json.get("action") if isinstance(p_json, dict) else None
    s_act = s_json.get("action") if isinstance(s_json, dict) else None
    rec = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "provider": provider,
        "search": opts["use_search"],
        "prompt_chars": len(prompt),
        "primary_model": primary["model"],
        "primary_latency": primary["latency"],
        "primary_cost": round(primary["cost"], 6),
        "primary_chars": len(primary["text"]),
        "primary_json_ok": p_json is not None,
        "primary_action": p_act,
        "shadow_model": (res or {}).get("model") or shadow_model,
        "shadow_ok": res is not None,
        "shadow_error": err,
        "shadow_latency": shadow_latency,
        "shadow_cost": round((res or {}).get("cost", 0.0), 6),
        "shadow_chars": len((res or {}).get("text", "")),
        "shadow_json_ok": s_json is not None,
        "shadow_action": s_act,
        "action_agree": (p_act == s_act) if (p_act and s_act) else None,
        "primary_text": primary["text"][:_TEXT_LIMIT],
        "shadow_text": (res or {}).get("text", "")[:_TEXT_LIMIT],
    }
    with _write_lock:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def get_model_shadow_report(days: int = 7) -> dict:
    """프로바이더·기능별로 성공률, JSON 성공률, 매매판단 일치율, 지연, 비용 배율을 집계."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    try:
        with open(_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("ts", "") >= cutoff:
                    r.pop("primary_text", None)
                    r.pop("shadow_text", None)
                    rows.append(r)
    except FileNotFoundError:
        pass

    def _agg(rs):
        ok = [r for r in rs if r["shadow_ok"]]
        agree = [r["action_agree"] for r in ok if r.get("action_agree") is not None]
        p_cost = sum(r["primary_cost"] for r in ok)
        s_cost = sum(r["shadow_cost"] for r in ok)
        flips = Counter(f"{r['primary_action']}→{r['shadow_action']}" for r in ok
                        if r.get("action_agree") is False)
        return {
            "n": len(rs),
            "shadow_fail": len(rs) - len(ok),
            "primary_json_ok_pct": round(100 * sum(r["primary_json_ok"] for r in ok) / len(ok), 1) if ok else None,
            "shadow_json_ok_pct": round(100 * sum(r["shadow_json_ok"] for r in ok) / len(ok), 1) if ok else None,
            "action_n": len(agree),
            "action_agree_pct": round(100 * sum(agree) / len(agree), 1) if agree else None,
            "action_flips": dict(flips.most_common(5)),
            "latency_primary": round(sum(r["primary_latency"] for r in ok) / len(ok), 1) if ok else None,
            "latency_shadow": round(sum(r["shadow_latency"] for r in ok) / len(ok), 1) if ok else None,
            "chars_ratio": round(sum(r["shadow_chars"] for r in ok) / max(1, sum(r["primary_chars"] for r in ok)), 2) if ok else None,
            "cost_primary_usd": round(p_cost, 4),
            "cost_shadow_usd": round(s_cost, 4),
            "cost_ratio": round(s_cost / p_cost, 2) if p_cost else None,
        }

    by_prov = defaultdict(list)
    by_src = defaultdict(list)
    for r in rows:
        by_prov[(r["provider"], r["primary_model"], r["shadow_model"])].append(r)
        by_src[(r["provider"], r["source"])].append(r)
    return {
        "period_days": days,
        "sample": len(rows),
        "today_counts": dict(_daily["counts"]),
        "today_dropped": dict(_daily["dropped"]),
        "by_provider": [{"provider": k[0], "primary_model": k[1], "shadow_model": k[2], **_agg(v)}
                        for k, v in by_prov.items()],
        "by_source": sorted(({"provider": k[0], "source": k[1], **_agg(v)} for k, v in by_src.items()),
                            key=lambda x: -x["n"]),
        "errors": dict(Counter((r.get("shadow_error") or "")[:80] for r in rows if not r["shadow_ok"]).most_common(5)),
    }


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    rep = get_model_shadow_report(d)
    print(f"모델 그림자 비교 — 최근 {d}일 · 표본 {rep['sample']}건")
    for p in rep["by_provider"]:
        print(f"\n[{p['provider']}] {p['primary_model']} → {p['shadow_model']}  ({p['n']}건, 실패 {p['shadow_fail']})")
        print(f"   JSON 성공  현재 {p['primary_json_ok_pct']}% / 신형 {p['shadow_json_ok_pct']}%")
        print(f"   매매판단 일치 {p['action_agree_pct']}% ({p['action_n']}건)  뒤집힘 {p['action_flips']}")
        print(f"   지연 {p['latency_primary']}s → {p['latency_shadow']}s · 응답 길이 x{p['chars_ratio']}")
        print(f"   비용 ${p['cost_primary_usd']} → ${p['cost_shadow_usd']} (x{p['cost_ratio']})")
    if rep["by_source"]:
        print("\n기능별:")
        for s in rep["by_source"]:
            print(f"   {s['provider']:6} {s['source'][:32]:32} {s['n']:4}건 · 일치 {s['action_agree_pct']} · "
                  f"JSON {s['primary_json_ok_pct']}/{s['shadow_json_ok_pct']} · 비용 x{s['cost_ratio']} · 길이 x{s['chars_ratio']}")
    if rep["errors"]:
        print("\n그림자 실패:", rep["errors"])
