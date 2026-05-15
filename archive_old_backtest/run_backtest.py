import pandas as pd
import os
import glob
import time
from signal_logic import prepare_df, detect_signal_detail
from risk_manager import RiskManager

# 설정
DATA_DIR = "./data_csv/*.csv"
INITIAL_CAPITAL = 10000000  # 초기 자본금 1,000만 원
COST_RATE = 0.007

def run_advanced_backtest():
    csv_files = glob.glob(DATA_DIR)
    if not csv_files: return print("❌ 데이터 없음")

    # 1. 전 종목 데이터 로드 및 통합 (시간순 정렬을 위함)
    print("📂 데이터를 로드하고 통합하는 중...")
    all_data_list = []
    for f in csv_files:
        ticker = os.path.basename(f).replace(".csv", "")
        df = pd.read_csv(f)
        df['ticker'] = ticker
        df['datetime'] = pd.to_datetime(df['datetime'])
        all_data_list.append(prepare_df(df))
    
    # 시간순 통합 시뮬레이션을 위해 하나의 DF로 결합 후 정렬
    full_df = pd.concat(all_data_list).sort_values('datetime')
    time_steps = full_df['datetime'].unique()
    
    # 2. 리스크 매니저 및 자산 추적 초기화
    rm = RiskManager(initial_capital=INITIAL_CAPITAL)
    equity_curve = []
    active_trades = {}  # {ticker: position_info}
    daily_stats = {"last_date": None}

    print(f"🚀 실전 통합 백테스트 시작 (초기자본: {INITIAL_CAPITAL:,}원)")
    
    # 3. 시간 순서대로 시뮬레이션 (Chronological Simulation)
    for current_time in time_steps:
        # 일자 변경 시 리스크 매니저 초기화
        current_date = current_time.date()
        if daily_stats["last_date"] != current_date:
            rm.reset_daily(rm.total_equity)
            daily_stats["last_date"] = current_date

        # 현재 시간에 해당하는 봉들만 추출
        step_df = full_df[full_df['datetime'] == current_time]
        
        for _, row in step_df.iterrows():
            ticker = row['ticker']
            
            # A. 보유 포지션 관리 (청산 로직)
            if ticker in active_trades:
                pos = active_trades[ticker]
                profit_rate = (row['close'] / pos['entry_price']) - 1
                
                # 본절 트레일링 체크
                if not pos['be_active'] and row['high'] >= pos['be_trigger']:
                    pos['sl'] = pos['entry_price'] * (1 + COST_RATE) # 본전(수수료 포함)으로 SL 상향
                    pos['be_active'] = True

                # 청산 조건: TP 도달, SL 도달, 또는 장마감(15:20)
                is_close = (row['datetime'].time() >= pd.to_datetime("15:20").time())
                if row['low'] <= pos['sl'] or row['high'] >= pos['tp'] or is_close:
                    exit_price = pos['sl'] if row['low'] <= pos['sl'] else (pos['tp'] if row['high'] >= pos['tp'] else row['close'])
                    trade_profit = (exit_price - pos['entry_price']) * pos['shares'] - (exit_price * pos['shares'] * (COST_RATE/2))
                    rm.total_equity += trade_profit
                    rm.active_positions_count -= 1
                    del active_trades[ticker]
                continue

            # B. 신규 진입 관리
            if rm.can_trade(rm.total_equity):
                # 시그널 확인
                # (주의: full_df에서 해당 ticker의 전체 df를 다시 슬라이싱하여 시그널 판단)
                # 성능을 위해 detect_signal_detail에 필요한 값들은 row에 이미 포함됨
                score_data = detect_signal_detail(step_df[step_df['ticker']==ticker], 0) # 여기선 간략화
                
                # 실제로는 prepare_df에서 계산된 컬럼을 row에서 직접 확인
                if row['vol_accel'] >= 1.5 and row['vol_ratio'] >= 3.0 and row['box_high'] > 0 and row['close'] > row['box_high']:
                    # 리스크 매니저를 통한 타겟 및 수량 산출
                    targets = rm.get_stop_targets(row['close'], row['atr'])
                    shares = rm.calculate_position_size(row['close'], targets['sl'])
                    
                    if shares > 0:
                        active_trades[ticker] = {
                            "entry_price": row['close'],
                            "entry_time": row['datetime'],
                            "shares": shares,
                            "sl": targets['sl'],
                            "tp": targets['tp'],
                            "be_trigger": targets['be_trigger'],
                            "be_active": False
                        }
                        rm.total_equity -= (row['close'] * shares * (COST_RATE/2)) # 진입 수수료
                        rm.active_positions_count += 1

        equity_curve.append({"datetime": current_time, "equity": rm.total_equity})

    # 4. 결과 분석 (MDD 등)
    report_results(equity_curve, INITIAL_CAPITAL)

def report_results(curve, initial):
    df = pd.DataFrame(curve)
    df['peak'] = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
    mdd = df['drawdown'].min()
    final_equity = df['equity'].iloc[-1]
    
    print("\n" + "="*50)
    print("🛡️ Phase 3 리스크 관리 백테스트 결과")
    print("="*50)
    print(f"최종 자산: {final_equity:,.0f}원 (수익률: {(final_equity/initial-1):.2%})")
    print(f"최대 낙폭 (MDD): {mdd:.2%}")
    print("="*50)

if __name__ == "__main__":
    run_advanced_backtest()
