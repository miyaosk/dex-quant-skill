"""
技术指标策略模板
基于 K 线价格和成交量的纯技术指标策略。

使用方式:
  回测: python technical_strategy.py backtest 2024-01-01 2024-12-31
  实时: python technical_strategy.py live
  单次: python technical_strategy.py live --once

依赖: pip install httpx numpy pandas loguru
"""

import json
import sys
import os
from datetime import datetime, timezone

# ── 将 backtester/scripts 加入路径以复用数据客户端和指标库 ──
SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(SKILL_ROOT, "backtester", "scripts"))

from data_client import DataClient
from indicators import Indicators
import numpy as np

# ═══════════════════════════════════════════════════
# 策略配置 — 根据用户需求修改此部分
# ═══════════════════════════════════════════════════

STRATEGY_NAME = "BTC MACD 趋势跟踪"
STRATEGY_VERSION = "v1.0"
SYMBOLS = ["BTCUSDT"]
TIMEFRAME = "4h"
VENUE = "binance_futures"       # binance_futures / binance_spot

# ── 指标参数 ──
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOL_MA_PERIOD = 20
VOL_MULTIPLIER = 1.5

# ── 风控参数 ──
STOP_LOSS_PCT = 0.02            # 止损 2%
TAKE_PROFIT_PCT = 0.06          # 止盈 6%


# ═══════════════════════════════════════════════════
# 信号生成逻辑 — 核心函数
# ═══════════════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    """
    策略主函数。
    mode: "live" 实时模式 / "backtest" 回测模式
    返回标准信号 JSON。
    """
    client = DataClient()
    signals = []

    for symbol in SYMBOLS:
        ticker = symbol.replace("USDT", "-USDT")
        if VENUE == "binance_futures":
            ticker += "-PERP"

        if mode == "backtest" and start_date and end_date:
            df = client.get_perp_klines(ticker, TIMEFRAME, start_date, end_date)
        else:
            df = client.get_perp_klines(ticker, TIMEFRAME, limit=100)

        if df.empty:
            continue

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        # ── 计算指标 ──
        macd_dif, macd_dea, macd_hist = Indicators.macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        rsi = Indicators.rsi(close, RSI_PERIOD)
        vol_ma = Indicators.volume_ma(volume, VOL_MA_PERIOD)
        cross_up = Indicators.crossover(macd_dif, macd_dea)
        cross_down = Indicators.crossunder(macd_dif, macd_dea)

        if mode == "backtest":
            for i in range(max(MACD_SLOW, VOL_MA_PERIOD, RSI_PERIOD) + 1, len(df)):
                sig = _evaluate_bar(
                    symbol, df.iloc[i], i,
                    macd_dif, macd_dea, rsi, volume, vol_ma,
                    cross_up, cross_down, close
                )
                if sig:
                    signals.append(sig)
        else:
            i = len(df) - 1
            sig = _evaluate_bar(
                symbol, df.iloc[i], i,
                macd_dif, macd_dea, rsi, volume, vol_ma,
                cross_up, cross_down, close
            )
            if sig:
                signals.append(sig)

    client.close()

    return {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "signals": signals,
    }


def _evaluate_bar(symbol, row, i, macd_dif, macd_dea, rsi, volume, vol_ma,
                  cross_up, cross_down, close):
    """评估单根 bar 是否触发信号。"""
    price = row["close"]
    ts = str(row["datetime"])

    # ── 买入条件: MACD 金叉 + 成交量放大 + RSI 未超买 ──
    if (cross_up[i]
        and not np.isnan(vol_ma[i]) and volume[i] > vol_ma[i] * VOL_MULTIPLIER
        and not np.isnan(rsi[i]) and rsi[i] < RSI_OVERBOUGHT):
        return {
            "symbol": symbol,
            "action": "buy",
            "confidence": min(0.5 + (volume[i] / vol_ma[i] - 1) * 0.3, 1.0) if vol_ma[i] > 0 else 0.6,
            "reason": f"MACD 金叉 (DIF={macd_dif[i]:.1f} 上穿 DEA={macd_dea[i]:.1f}) + 成交量放大 {volume[i]/vol_ma[i]:.1f}x",
            "price_at_signal": float(price),
            "suggested_stop_loss": float(price * (1 - STOP_LOSS_PCT)),
            "suggested_take_profit": float(price * (1 + TAKE_PROFIT_PCT)),
            "source_type": "technical",
            "timestamp": ts,
            "metadata": {
                "macd_dif": float(macd_dif[i]),
                "macd_dea": float(macd_dea[i]),
                "rsi": float(rsi[i]),
                "volume_ratio": float(volume[i] / vol_ma[i]) if vol_ma[i] > 0 else 0,
            }
        }

    # ── 卖出条件: MACD 死叉 OR RSI 超买 ──
    if cross_down[i] or (not np.isnan(rsi[i]) and rsi[i] > RSI_OVERBOUGHT):
        reason_parts = []
        if cross_down[i]:
            reason_parts.append(f"MACD 死叉 (DIF={macd_dif[i]:.1f} 下穿 DEA={macd_dea[i]:.1f})")
        if not np.isnan(rsi[i]) and rsi[i] > RSI_OVERBOUGHT:
            reason_parts.append(f"RSI 超买 ({rsi[i]:.1f} > {RSI_OVERBOUGHT})")
        return {
            "symbol": symbol,
            "action": "sell",
            "confidence": 0.7,
            "reason": " + ".join(reason_parts),
            "price_at_signal": float(price),
            "source_type": "technical",
            "timestamp": ts,
            "metadata": {
                "macd_dif": float(macd_dif[i]),
                "macd_dea": float(macd_dea[i]),
                "rsi": float(rsi[i]),
            }
        }

    return None


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None

    result = generate_signals(mode=mode, start_date=start, end_date=end)
    print(json.dumps(result, ensure_ascii=False, indent=2))
