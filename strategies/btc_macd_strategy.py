"""
BTC MACD 金叉死叉策略

规则:
  买入: MACD 金叉（DIF 上穿 DEA）
  卖出: MACD 死叉（DIF 下穿 DEA）

使用方式:
  回测: python btc_macd_strategy.py backtest 2024-01-01 2024-12-31
  实时: python btc_macd_strategy.py live

依赖: pip install httpx numpy pandas loguru
"""

import json
import sys
import os
from datetime import datetime, timezone

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(SKILL_ROOT, "backtester", "scripts"))

from data_client import DataClient
from indicators import Indicators
import numpy as np

# ═══════════════════════════════════════════════════
# 策略配置
# ═══════════════════════════════════════════════════

STRATEGY_NAME = "BTC MACD 金叉死叉"
STRATEGY_VERSION = "v1.0"
SYMBOL = "BTCUSDT"
TIMEFRAME = "4h"

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9


# ═══════════════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    client = DataClient()

    ticker = "BTC-USDT-PERP"
    if mode == "backtest" and start_date and end_date:
        df = client.get_perp_klines(ticker, TIMEFRAME, start_date, end_date)
    else:
        df = client.get_perp_klines(ticker, TIMEFRAME, limit=100)

    client.close()

    if df.empty:
        return _output(mode, [])

    close = df["close"].values
    dif, dea, hist = Indicators.macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    cross_up = Indicators.crossover(dif, dea)
    cross_down = Indicators.crossunder(dif, dea)

    signals = []
    warmup = MACD_SLOW + MACD_SIGNAL

    if mode == "backtest":
        for i in range(warmup, len(df)):
            sig = _evaluate(df.iloc[i], i, dif, dea, cross_up, cross_down)
            if sig:
                signals.append(sig)
    else:
        i = len(df) - 1
        sig = _evaluate(df.iloc[i], i, dif, dea, cross_up, cross_down)
        if sig:
            signals.append(sig)

    return _output(mode, signals)


def _evaluate(row, i, dif, dea, cross_up, cross_down):
    price = float(row["close"])
    ts = str(row["datetime"])

    if cross_up[i]:
        return {
            "symbol": SYMBOL,
            "action": "buy",
            "confidence": round(min(0.6 + abs(dif[i] - dea[i]) / price * 100, 1.0), 2),
            "reason": f"MACD 金叉 (DIF={dif[i]:.1f} 上穿 DEA={dea[i]:.1f})",
            "price_at_signal": price,
            "source_type": "technical",
            "timestamp": ts,
            "metadata": {
                "macd_dif": round(float(dif[i]), 2),
                "macd_dea": round(float(dea[i]), 2),
                "macd_hist": round(float(dif[i] - dea[i]), 2),
            },
        }

    if cross_down[i]:
        return {
            "symbol": SYMBOL,
            "action": "sell",
            "confidence": round(min(0.6 + abs(dif[i] - dea[i]) / price * 100, 1.0), 2),
            "reason": f"MACD 死叉 (DIF={dif[i]:.1f} 下穿 DEA={dea[i]:.1f})",
            "price_at_signal": price,
            "source_type": "technical",
            "timestamp": ts,
            "metadata": {
                "macd_dif": round(float(dif[i]), 2),
                "macd_dea": round(float(dea[i]), 2),
                "macd_hist": round(float(dif[i] - dea[i]), 2),
            },
        }

    return None


def _output(mode, signals):
    return {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "signals": signals,
    }


if __name__ == "__main__":
    from strategy_runner import run
    run(generate_signals, STRATEGY_NAME, SYMBOL, TIMEFRAME, script_path=__file__)
