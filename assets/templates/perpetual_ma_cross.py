"""
永续合约均线交叉策略模板

数据源: Binance Futures API (公开, 无需 Key)
回测引擎: 本地 BacktestEngine

策略逻辑:
- 快速均线上穿慢速均线 → 开多
- 快速均线下穿慢速均线 → 开空
- 支持杠杆、止损止盈、资金费率结算

用法: 修改下方参数区即可运行
"""

import numpy as np
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

# ═══ 参数区 ═══
SYMBOL = "BTC-USDT-PERP"
START_DATE = "2024-01-01"
END_DATE = "2025-12-31"
INTERVAL = "1d"
FAST_PERIOD = 10
SLOW_PERIOD = 30
LEVERAGE = 5
POSITION_SIZE = 0.1          # BTC 数量
STOP_LOSS_PCT = 0.05         # 5%
TAKE_PROFIT_PCT = 0.15       # 15%
INITIAL_CAPITAL = 100_000    # USDT
# ═══════════════

client = DataClient()
engine = BacktestEngine(BacktestConfig(
    initial_capital=INITIAL_CAPITAL,
    default_leverage=LEVERAGE,
    margin_mode="isolated",
    slippage_bps=2,
    enable_funding=True,
    enable_liquidation=True,
))

klines = client.get_perp_klines(SYMBOL, INTERVAL, START_DATE, END_DATE)
funding = client.get_funding_rate(SYMBOL, START_DATE, END_DATE)
funding_map = {
    row["datetime"].strftime("%Y-%m-%d %H:%M"): row["funding_rate"]
    for _, row in funding.iterrows()
}

closes = []

for i, bar in klines.iterrows():
    dt = str(bar["datetime"])
    price = bar["close"]
    closes.append(price)

    prices = {SYMBOL: {
        "close": price, "high": bar["high"],
        "low": bar["low"], "mark_price": price,
    }}
    fr_key = bar["datetime"].strftime("%Y-%m-%d %H:%M")
    fr = {SYMBOL: funding_map[fr_key]} if fr_key in funding_map else {}
    engine.on_bar(dt, prices, fr)

    if len(closes) < SLOW_PERIOD:
        continue

    fast_ma = np.mean(closes[-FAST_PERIOD:])
    slow_ma = np.mean(closes[-SLOW_PERIOD:])
    pos = engine.get_position(SYMBOL)

    if fast_ma > slow_ma and pos["side"] != "long":
        if pos["side"] == "short":
            engine.close_short(SYMBOL, pos["quantity"], price, price, dt)
        engine.open_long(SYMBOL, POSITION_SIZE, price, price, dt, leverage=LEVERAGE)
        engine.set_stop_loss(SYMBOL, price * (1 - STOP_LOSS_PCT))
        engine.set_take_profit(SYMBOL, price * (1 + TAKE_PROFIT_PCT))

    elif fast_ma < slow_ma and pos["side"] != "short":
        if pos["side"] == "long":
            engine.close_long(SYMBOL, pos["quantity"], price, price, dt)
        engine.open_short(SYMBOL, POSITION_SIZE, price, price, dt, leverage=LEVERAGE)
        engine.set_stop_loss(SYMBOL, price * (1 + STOP_LOSS_PCT))
        engine.set_take_profit(SYMBOL, price * (1 - TAKE_PROFIT_PCT))

result = engine.get_result()
print(engine.format_summary(result))
