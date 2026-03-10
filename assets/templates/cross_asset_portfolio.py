"""
跨资产组合策略模板

数据源: Binance Futures + CoinGecko
回测引擎: 本地 BacktestEngine

策略逻辑:
- 同时持有 BTC 永续 + ETH 永续 + PAXG 黄金代币
- 按固定权重分配资金
- 定期再平衡（偏差超过阈值时调仓）

注意: PAXG 数据来自 CoinGecko（免费日线，最多 365 天）
"""

import numpy as np
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

# ═══ 参数区 ═══
ASSETS = {
    "BTC-USDT-PERP": {"weight": 0.40, "source": "binance_futures"},
    "ETH-USDT-PERP": {"weight": 0.30, "source": "binance_futures"},
    "PAXG":          {"weight": 0.30, "source": "coingecko"},
}
START_DATE = "2025-03-10"
END_DATE = "2026-03-10"
REBALANCE_DAYS = 30
DRIFT_THRESHOLD = 0.05       # 5% 偏差才再平衡
PERP_LEVERAGE = 2
INITIAL_CAPITAL = 100_000
# ═══════════════

client = DataClient()
engine = BacktestEngine(BacktestConfig(
    initial_capital=INITIAL_CAPITAL,
    default_leverage=PERP_LEVERAGE,
    margin_mode="isolated",
    slippage_bps=5,
    enable_funding=True,
    enable_liquidation=True,
))

# 拉取数据
data = {}
for symbol, info in ASSETS.items():
    if info["source"] == "binance_futures":
        data[symbol] = client.get_perp_klines(symbol, "1d", START_DATE, END_DATE)
    elif info["source"] == "coingecko":
        data[symbol] = client.get_token_history(symbol, days=365)

# 拉取 BTC/ETH 资金费率
funding_maps = {}
for symbol in ["BTC-USDT-PERP", "ETH-USDT-PERP"]:
    fr = client.get_funding_rate(symbol, START_DATE, END_DATE)
    funding_maps[symbol] = {
        row["datetime"].strftime("%Y-%m-%d %H:%M"): row["funding_rate"]
        for _, row in fr.iterrows()
    }

# 对齐日期（取所有资产的交集）
btc_dates = set(data["BTC-USDT-PERP"]["datetime"].dt.date)
common_dates = btc_dates
for symbol, df in data.items():
    common_dates &= set(df["datetime"].dt.date)
common_dates = sorted(common_dates)

bar_count = 0

for date in common_dates:
    bar_count += 1
    dt = str(date)

    prices = {}
    for symbol, df in data.items():
        day_data = df[df["datetime"].dt.date == date]
        if day_data.empty:
            continue
        row = day_data.iloc[0]
        close = row.get("close", row.get("close", 0))
        high = row.get("high", close)
        low = row.get("low", close)
        prices[symbol] = {
            "close": close, "high": high, "low": low, "mark_price": close,
        }

    # 资金费率
    funding_rates = {}
    for sym in ["BTC-USDT-PERP", "ETH-USDT-PERP"]:
        fr_key = f"{date} 00:00"
        if fr_key in funding_maps.get(sym, {}):
            funding_rates[sym] = funding_maps[sym][fr_key]

    engine.on_bar(dt, prices, funding_rates)

    # 再平衡
    if bar_count % REBALANCE_DAYS != 0:
        continue

    total_equity = engine.account.equity

    for symbol, info in ASSETS.items():
        if symbol not in prices:
            continue

        target_value = total_equity * info["weight"]
        current_price = prices[symbol]["close"]
        target_qty = target_value / current_price

        pos = engine.get_position(symbol)
        current_qty = pos["quantity"] if pos["side"] != "none" else 0.0

        if target_qty == 0:
            continue

        drift = abs(current_qty - target_qty) / target_qty
        if drift <= DRIFT_THRESHOLD:
            continue

        diff = target_qty - current_qty
        lev = PERP_LEVERAGE if symbol.endswith("-PERP") else 1

        if diff > 0:
            engine.open_long(symbol, abs(diff), current_price, current_price, dt, leverage=lev)
        elif diff < 0 and pos["side"] == "long":
            close_qty = min(abs(diff), pos["quantity"])
            engine.close_long(symbol, close_qty, current_price, current_price, dt)

result = engine.get_result()
print(engine.format_summary(result))
