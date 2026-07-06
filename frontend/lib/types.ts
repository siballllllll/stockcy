/* Stockcy 공통 TypeScript 타입 정의 */

// ── 시장 지수 ─────────────────────────────────────────────────────────────────
export interface MarketIndex {
  price:      number;
  change:     number;
  change_pct: number;
}

export interface UsIndices {
  "S&P 500": MarketIndex;
  NASDAQ:    MarketIndex;
  DOW:       MarketIndex;
  VIX:       MarketIndex;
}

export interface KrIndex {
  index:      number;
  change:     number;
  change_pct: number;
}

export interface KrIndices {
  KOSPI:  KrIndex;
  KOSDAQ: KrIndex;
}

// ── 주식 시세 ────────────────────────────────────────────────────────────────
export interface UsStock {
  "심볼":      string;
  "현재가($)": number;
  "등락률(%)": number;
  "상태":      string;
}

export interface KrStock {
  price:      number;
  change:     number;
  change_pct: number;
  volume:     number;
  amount:     number;
  open:       number;
  high:       number;
  low:        number;
  per:        string;
  pbr:        string;
  w52_high:   number;
  w52_low:    number;
  market_cap: string;
}

export interface RankingStock {
  "종목코드":  string;
  "종목명":    string;
  "현재가":    number;
  "등락률(%)": number;
  "거래량":    number;
  "시장"?:     string;
}

// ── 즐겨찾기 ────────────────────────────────────────────────────────────────
export interface Favorite {
  "추가시간": string;
  "시장":     string;
  "티커":     string;
  "종목명":   string;
  "메모"?:    string;
  "섹터"?:    string;
}

// ── AI 분석 결과 ──────────────────────────────────────────────────────────────

export interface AiSector {
  keyword:              string;
  is_main:              boolean;
  reason:               string;
  reference_news_title: string;
  reference_news_url:   string;
  related_stocks:       { name_kr: string; ticker: string }[];
}

export interface DailyBriefing {
  sectors: AiSector[];
  error?:  string;
}

export interface ScenarioStock {
  name:           string;
  ticker:         string;
  reason:         string;
  valuation_note: string;
  signal:         string;
  signal_reason:  string;
  buy_target?:    string;
  sell_target?:   string;
  stop_loss?:     string;
}

export interface Scenario {
  label:             string;
  title:             string;
  probability:       string;
  probability_pct:   number;
  market_direction:  string;
  trigger:           string;
  economic_analysis: string;
  rising_stocks:     ScenarioStock[];
  falling_stocks:    ScenarioStock[];
  theme_stocks:      ScenarioStock[];
  short_strategy:    string;
  long_strategy:     string;
}

export interface MacroIssue {
  issue_no:  number;
  title:     string;
  summary:   string;
  urgency:   string;
  category:  string;
  scenarios: Scenario[];
}

export interface MarketScenarios {
  issues: MacroIssue[];
  error?: string;
}

export interface StockReport {
  verified_name:           string;
  ticker_mismatch:         boolean;
  rating:                  string;
  key_issues:              string;
  short_term_view_pct:     string;
  short_term_view_price:   string;
  short_term_view_reason:  string;
  buy_target:              string;
  sell_target:             string;
  stop_loss:               string;
  mid_term_view_pct:       string;
  mid_term_view_price:     string;
  mid_term_view_condition: string;
  analysis:                string;
  long_term_rating:        string;
  long_term_period:        string;
  long_term_target:        string;
  long_term_analysis:      string;
  /** 자체 ML 상승확률 % (우리 매매결과 학습·확률보정) — 모델 미학습 시 없음 */
  ml_win_proba?:           { d3?: number; d7?: number; d20?: number };
  error?:                  string;
}

export interface RealtimePick {
  rank:          number;
  code:          string;
  name:          string;
  theme:         string;
  pattern:       string;
  reason:        string;
  current_price: number;
  change_pct:    number;
  entry:         number;
  entry_limit:   number;
  target:        number;
  stop:          number;
  urgency:       string;
  horizon:       string;
  position:      string;
  theme_stage:   string;
  leader_name:   string;
  supply_signal: string;
}

// ── 국내 종목 AI 리포트 ───────────────────────────────────────────────────────
export interface KrStockReport {
  verified_name:              string;
  ticker_mismatch:            boolean;
  rating:                     string;
  key_issues:                 string;
  short_term_view_pct:        string;
  short_term_view_price:      string;
  short_term_view_reason:     string;
  buy_target:                 string;
  sell_target:                string;
  stop_loss:                  string;
  mid_term_view_pct:          string;
  mid_term_view_price:        string;
  mid_term_view_condition:    string;
  "세력분석"?:                string;
  analysis:                   string;
  historical_pattern_analysis?: string;
  long_term_rating:           string;
  long_term_period:           string;
  long_term_target:           string;
  long_term_target_pct?:      string;
  long_term_analysis:         string;
  /** 자체 ML 상승확률 % (우리 매매결과 학습·확률보정) — 모델 미학습 시 없음 */
  ml_win_proba?:              { d3?: number; d7?: number; d20?: number };
  error?:                     string;
}

// ── 미국 단타 핫 종목 ─────────────────────────────────────────────────────────
export interface HotStockUs {
  ticker:          string;
  verified_name:   string;
  ticker_verified: boolean;
  name_kr:         string;
  buy_target:      string;
  sell_target:     string;
  stop_loss:       string;
  reasoning:       string;
  error?:          string;
}

// ── 차트 데이터 ───────────────────────────────────────────────────────────────
export interface ChartCandle {
  일자:   string;
  시가:   number;
  고가:   number;
  저가:   number;
  종가:   number;
  거래량: number;
}

// ── SSE 이벤트 ────────────────────────────────────────────────────────────────
export type SseStatus = "idle" | "running" | "done" | "error";

export interface SseEvent<T = unknown> {
  status:     SseStatus;
  message?:   string;
  result?:    T;
  from_cache?: boolean;
}

// ── API 응답 공통 ─────────────────────────────────────────────────────────────
export interface ApiResponse<T = unknown> {
  success?: boolean;
  message?: string;
  data?:    T;
}
