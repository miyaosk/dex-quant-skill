"""
混合策略模板
技术指标 + 社交媒体 + 链上数据的综合策略。

使用方式:
  回测: python mixed_strategy.py backtest 2024-01-01 2024-12-31
        (仅技术指标部分可回测，社媒部分标注为"未验证")
  实时: python mixed_strategy.py live

依赖: pip install httpx numpy pandas loguru
"""

import json
import sys
import os
from datetime import datetime, timezone

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(SKILL_ROOT, "backtester", "scripts"))

from data_client import DataClient
from indicators import Indicators
import numpy as np

# ═══════════════════════════════════════════════════
# 策略配置
# ═══════════════════════════════════════════════════

STRATEGY_NAME = "ETH 综合信号策略（技术+社媒+链上）"
STRATEGY_VERSION = "v1.0"
SYMBOLS = ["ETHUSDT"]
TIMEFRAME = "4h"

# ── 技术指标参数 ──
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 45
RSI_SELL_THRESHOLD = 65
SMA_FAST = 10
SMA_SLOW = 30

# ── 链上数据阈值 ──
FUNDING_RATE_HIGH = 0.001      # 资金费率 > 0.1% 视为过热
FUNDING_RATE_LOW = -0.0005     # 资金费率 < -0.05% 视为过冷

# ── 社媒配置 ──
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# ── 风控 ──
STOP_LOSS_PCT = 0.025
TAKE_PROFIT_PCT = 0.08


# ═══════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════

def get_technical_data(client, symbol, mode, start_date, end_date):
    """获取 K 线 + 计算技术指标。"""
    ticker = symbol.replace("USDT", "-USDT") + "-PERP"

    if mode == "backtest" and start_date and end_date:
        df = client.get_perp_klines(ticker, TIMEFRAME, start_date, end_date)
    else:
        df = client.get_perp_klines(ticker, TIMEFRAME, limit=100)

    if df.empty:
        return None, {}

    close = df["close"].values
    rsi = Indicators.rsi(close, RSI_PERIOD)
    sma_fast = Indicators.sma(close, SMA_FAST)
    sma_slow = Indicators.sma(close, SMA_SLOW)
    cross_up = Indicators.crossover(sma_fast, sma_slow)
    cross_down = Indicators.crossunder(sma_fast, sma_slow)
    atr = Indicators.atr(df["high"].values, df["low"].values, close, 14)

    indicators = {
        "rsi": rsi, "sma_fast": sma_fast, "sma_slow": sma_slow,
        "cross_up": cross_up, "cross_down": cross_down, "atr": atr,
    }
    return df, indicators


def get_funding_rate(client, symbol):
    """获取当前资金费率。"""
    try:
        ticker = symbol.replace("USDT", "-USDT") + "-PERP"
        df = client.get_funding_rate(ticker, limit=1)
        if not df.empty:
            return float(df.iloc[-1]["funding_rate"])
    except Exception:
        pass
    return 0.0


def get_social_sentiment(symbol):
    """获取社媒情绪得分 (0~1, >0.5 看多, <0.5 看空)。"""
    if not TWITTER_BEARER_TOKEN:
        return None

    # 简化实现：实际项目中替换为真正的社媒 API 调用
    # 这里返回 None 表示社媒数据不可用
    return None


# ═══════════════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    client = DataClient()
    signals = []

    for symbol in SYMBOLS:
        df, ind = get_technical_data(client, symbol, mode, start_date, end_date)
        if df is None:
            continue

        funding_rate = get_funding_rate(client, symbol) if mode == "live" else 0.0
        social_score = get_social_sentiment(symbol) if mode == "live" else None

        if mode == "backtest":
            warmup = max(SMA_SLOW, RSI_PERIOD) + 1
            for i in range(warmup, len(df)):
                sig = _evaluate(symbol, df.iloc[i], i, ind, funding_rate, social_score)
                if sig:
                    signals.append(sig)
        else:
            i = len(df) - 1
            sig = _evaluate(symbol, df.iloc[i], i, ind, funding_rate, social_score)
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


def _evaluate(symbol, row, i, ind, funding_rate, social_score):
    """综合评估单根 bar。"""
    price = row["close"]
    ts = str(row["datetime"])
    reasons = []
    score = 0.0                     # 综合打分: >0 偏多, <0 偏空

    # ── 技术面 ──
    rsi_val = ind["rsi"][i]
    if not np.isnan(rsi_val):
        if rsi_val < RSI_BUY_THRESHOLD:
            score += 0.3
            reasons.append(f"RSI 超卖 ({rsi_val:.0f})")
        elif rsi_val > RSI_SELL_THRESHOLD:
            score -= 0.3
            reasons.append(f"RSI 超买 ({rsi_val:.0f})")

    if ind["cross_up"][i]:
        score += 0.4
        reasons.append("均线金叉")
    elif ind["cross_down"][i]:
        score -= 0.4
        reasons.append("均线死叉")

    # ── 链上面 ──
    if funding_rate > FUNDING_RATE_HIGH:
        score -= 0.2
        reasons.append(f"资金费率偏高 ({funding_rate:.4%})")
    elif funding_rate < FUNDING_RATE_LOW:
        score += 0.2
        reasons.append(f"资金费率偏低 ({funding_rate:.4%})")

    # ── 社媒面 ──
    social_note = ""
    if social_score is not None:
        if social_score > 0.7:
            score += 0.2
            reasons.append(f"社媒情绪看多 ({social_score:.2f})")
        elif social_score < 0.3:
            score -= 0.2
            reasons.append(f"社媒情绪看空 ({social_score:.2f})")
    else:
        social_note = "(社媒数据不可用，仅基于技术+链上)"

    # ── 综合判断 ──
    if score >= 0.5:
        return {
            "symbol": symbol,
            "action": "buy",
            "confidence": min(abs(score), 1.0),
            "reason": " + ".join(reasons) + social_note,
            "price_at_signal": float(price),
            "suggested_stop_loss": float(price * (1 - STOP_LOSS_PCT)),
            "suggested_take_profit": float(price * (1 + TAKE_PROFIT_PCT)),
            "source_type": "mixed" if social_score is not None else "technical",
            "timestamp": ts,
            "metadata": {
                "score": round(score, 3),
                "rsi": float(rsi_val) if not np.isnan(rsi_val) else None,
                "funding_rate": funding_rate,
                "social_score": social_score,
            }
        }
    elif score <= -0.5:
        return {
            "symbol": symbol,
            "action": "sell",
            "confidence": min(abs(score), 1.0),
            "reason": " + ".join(reasons) + social_note,
            "price_at_signal": float(price),
            "source_type": "mixed" if social_score is not None else "technical",
            "timestamp": ts,
            "metadata": {
                "score": round(score, 3),
                "rsi": float(rsi_val) if not np.isnan(rsi_val) else None,
                "funding_rate": funding_rate,
                "social_score": social_score,
            }
        }

    return None


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None
    result = generate_signals(mode=mode, start_date=start, end_date=end)
    print(json.dumps(result, ensure_ascii=False, indent=2))
