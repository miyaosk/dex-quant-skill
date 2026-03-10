"""
资金费率套利策略模板

数据源: Binance Futures API
回测引擎: 本地 BacktestEngine

策略逻辑:
- funding_rate > 阈值 → 做空永续（收取资金费率）
- funding_rate < -阈值 → 做多永续
- 费率回归中性 → 平仓

收益来源: 资金费率而非价格波动
风险特征: 低波动（单腿版本仍有价格风险）
"""

from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

# ═══ 参数区 ═══
SYMBOL = "BTC-USDT-PERP"
START_DATE = "2025-06-01"
END_DATE = "2026-03-01"
OPEN_THRESHOLD = 0.0005      # 0.05% 开仓
CLOSE_THRESHOLD = 0.00015    # 0.015% 平仓
POSITION_SIZE = 0.5          # BTC 数量
LEVERAGE = 1
INITIAL_CAPITAL = 100_000
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

klines = client.get_perp_klines(SYMBOL, "1d", START_DATE, END_DATE)
funding = client.get_funding_rate(SYMBOL, START_DATE, END_DATE)
funding_map = {
    row["datetime"].strftime("%Y-%m-%d %H:%M"): row["funding_rate"]
    for _, row in funding.iterrows()
}

for i, bar in klines.iterrows():
    dt = str(bar["datetime"])
    price = bar["close"]

    prices = {SYMBOL: {
        "close": price, "high": bar["high"],
        "low": bar["low"], "mark_price": price,
    }}
    fr_key = bar["datetime"].strftime("%Y-%m-%d %H:%M")
    current_fr = funding_map.get(fr_key, 0)
    fr = {SYMBOL: current_fr} if fr_key in funding_map else {}
    engine.on_bar(dt, prices, fr)

    pos = engine.get_position(SYMBOL)

    if pos["side"] == "none":
        if current_fr > OPEN_THRESHOLD:
            engine.open_short(SYMBOL, POSITION_SIZE, price, price, dt, leverage=LEVERAGE)
        elif current_fr < -OPEN_THRESHOLD:
            engine.open_long(SYMBOL, POSITION_SIZE, price, price, dt, leverage=LEVERAGE)

    elif abs(current_fr) < CLOSE_THRESHOLD:
        if pos["side"] == "short":
            engine.close_short(SYMBOL, pos["quantity"], price, price, dt)
        elif pos["side"] == "long":
            engine.close_long(SYMBOL, pos["quantity"], price, price, dt)

result = engine.get_result()
print(engine.format_summary(result))
