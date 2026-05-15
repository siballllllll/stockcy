import math

class RiskManager:
    def __init__(self, initial_capital=10000000):
        self.total_equity = initial_capital
        self.daily_start_equity = initial_capital
        self.max_risk_per_trade = 0.01  # 자산의 1% 리스크
        self.max_daily_loss_limit = 0.03  # 일일 손실 한도 3%
        self.max_concurrent_positions = 5
        self.active_positions_count = 0
        self.daily_loss_hit = False

    def reset_daily(self, current_equity):
        """매일 장 시작 전 호출하여 일일 한도 초기화"""
        self.daily_start_equity = current_equity
        self.daily_loss_hit = False

    def can_trade(self, current_equity):
        """진입 가능 여부 확인 (일일 손실 한도 및 동시 보유 제한)"""
        current_daily_loss = (self.daily_start_equity - current_equity) / self.daily_start_equity
        if current_daily_loss >= self.max_daily_loss_limit:
            self.daily_loss_hit = True
            return False
        
        if self.active_positions_count >= self.max_concurrent_positions:
            return False
        
        return not self.daily_loss_hit

    def calculate_position_size(self, entry_price, stop_loss_price):
        """1% 리스크 기반 매수 수량 산출"""
        risk_amount = self.total_equity * self.max_risk_per_trade
        loss_per_share = abs(entry_price - stop_loss_price)
        
        if loss_per_share == 0: return 0
        
        shares = math.floor(risk_amount / loss_per_share)
        # 실제 가용 자본금 내에서 구매 가능한지 체크
        if shares * entry_price > self.total_equity:
            shares = math.floor(self.total_equity / entry_price)
            
        return shares

    def get_stop_targets(self, entry_price, atr):
        """동적 손익비(1:2)에 따른 SL, TP 산출"""
        risk_range = atr * 1.5
        stop_loss = entry_price - risk_range
        take_profit = entry_price + (risk_range * 2)
        breakeven_trigger = entry_price + risk_range  # 목표가 50% 지점
        
        return {
            "sl": stop_loss,
            "tp": take_profit,
            "be_trigger": breakeven_trigger
        }
