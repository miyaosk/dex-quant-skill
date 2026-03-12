"""
永续合约策略模板 — 完整回测流程

本模板演示从 StrategySpec JSON 到回测结果的端到端流程:
    1. 加载策略规格 (StrategySpec)
    2. 拉取行情 + 资金费率数据
    3. 计算技术指标
    4. 生成交易信号
    5. 运行回测引擎
    6. 输出绩效指标 + 交易日志

使用方式:
    1. 修改 STRATEGY_SPEC 中的策略参数
    2. python perpetual_strategy.py

依赖:
    pip install httpx pandas numpy loguru
"""

from __future__ import annotations

import json
import sys
import os

import numpy as np
import pandas as pd
from loguru import logger

# 将 scripts 目录加入 path
SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPT_DIR))

from data_client import DataClient
from backtest_engine import BacktestEngine, BacktestConfig
from indicators import Indicators

# ═══════════════════════════════════════════
#  策略规格定义 (StrategySpec)
#  实际使用时可从 JSON 文件加载
# ═══════════════════════════════════════════

STRATEGY_SPEC = {
    "name": "BTC 均线交叉策略",
    "version": "1.0",
    "symbol": "BTC-USDT-PERP",
    "interval": "1d",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",

    # 回测配置
    "backtest": {
        "initial_capital": 100_000,
        "leverage": 5,
        "margin_mode": "isolated",
        "slippage_bps": 2,
        "taker_fee": 0.0005,
        "maker_fee": 0.0002,
        "enable_funding": True,
        "enable_liquidation": True,
        "maintenance_margin_rate": 0.005,
    },

    # 指标参数
    "indicators": {
        "fast_ma_period": 10,
        "slow_ma_period": 30,
        "ma_type": "ema",
        "rsi_period": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
    },

    # 信号规则
    "signals": {
        "long_entry": "fast_ma 上穿 slow_ma 且 RSI < rsi_overbought",
        "long_exit": "fast_ma 下穿 slow_ma 或 RSI > rsi_overbought",
        "short_entry": "fast_ma 下穿 slow_ma 且 RSI > rsi_oversold",
        "short_exit": "fast_ma 上穿 slow_ma 或 RSI < rsi_oversold",
    },

    # 风控参数
    "risk": {
        "position_size_pct": 0.5,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.15,
    },
}


def load_spec(spec_path: str = None) -> dict:
    """加载策略规格。优先从文件加载，否则使用内置默认。"""
    if spec_path and os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return STRATEGY_SPEC


def build_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """根据 spec 参数计算技术指标。"""
    close = df["close"].values
    ma_type = params.get("ma_type", "ema")
    fast_period = params["fast_ma_period"]
    slow_period = params["slow_ma_period"]

    if ma_type == "ema":
        df["fast_ma"] = Indicators.ema(close, fast_period)
        df["slow_ma"] = Indicators.ema(close, slow_period)
    else:
        df["fast_ma"] = Indicators.sma(close, fast_period)
        df["slow_ma"] = Indicators.sma(close, slow_period)

    df["rsi"] = Indicators.rsi(close, params.get("rsi_period", 14))

    fast_ma = df["fast_ma"].values
    slow_ma = df["slow_ma"].values
    df["golden_cross"] = Indicators.crossover(fast_ma, slow_ma)
    df["death_cross"] = Indicators.crossunder(fast_ma, slow_ma)

    return df


def generate_signals(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """根据 spec 信号规则生成交易信号。"""
    rsi_ob = params.get("rsi_overbought", 70)
    rsi_os = params.get("rsi_oversold", 30)

    df["signal"] = 0

    for i in range(len(df)):
        if pd.isna(df.iloc[i]["fast_ma"]) or pd.isna(df.iloc[i]["rsi"]):
            continue

        # 多头入场: 金叉 且 RSI 未超买
        if df.iloc[i]["golden_cross"] and df.iloc[i]["rsi"] < rsi_ob:
            df.iloc[i, df.columns.get_loc("signal")] = 1

        # 空头入场: 死叉 且 RSI 未超卖
        elif df.iloc[i]["death_cross"] and df.iloc[i]["rsi"] > rsi_os:
            df.iloc[i, df.columns.get_loc("signal")] = -1

    return df


def merge_funding_rates(
    klines: pd.DataFrame,
    funding: pd.DataFrame,
    interval: str,
) -> dict[str, float]:
    """
    将资金费率数据映射到 K 线时间。

    返回 {datetime_str: funding_rate} 字典，
    仅包含结算时刻 (00:00/08:00/16:00 UTC)。
    """
    if funding.empty:
        return {}

    funding_map = {}
    for _, row in funding.iterrows():
        dt_str = str(row["datetime"])
        funding_map[dt_str] = row["funding_rate"]

    return funding_map


def run_backtest(spec: dict):
    """执行完整回测流程。"""

    symbol = spec["symbol"]
    interval = spec["interval"]
    bt_config = spec["backtest"]
    ind_params = spec["indicators"]
    risk_params = spec["risk"]

    logger.info(f"═══ 开始回测: {spec['name']} ═══")
    logger.info(f"标的: {symbol} | 周期: {interval} | 杠杆: {bt_config['leverage']}x")

    # ── 步骤 1: 拉取数据 ──
    logger.info("步骤 1/6: 拉取行情数据...")
    client = DataClient()

    klines = client.get_perp_klines(
        symbol=symbol,
        interval=interval,
        start_date=spec["start_date"],
        end_date=spec["end_date"],
    )

    if klines.empty:
        logger.error("K 线数据为空，无法继续")
        return

    logger.info(f"获取 {len(klines)} 条 K 线")

    funding = pd.DataFrame()
    if bt_config.get("enable_funding", True):
        logger.info("拉取资金费率数据...")
        funding = client.get_funding_rate(
            symbol=symbol,
            start_date=spec["start_date"],
            end_date=spec["end_date"],
        )
        logger.info(f"获取 {len(funding)} 条资金费率")

    client.close()

    # ── 步骤 2: 计算指标 ──
    logger.info("步骤 2/6: 计算技术指标...")
    klines = build_indicators(klines, ind_params)

    # ── 步骤 3: 生成信号 ──
    logger.info("步骤 3/6: 生成交易信号...")
    klines = generate_signals(klines, ind_params)

    signal_count = (klines["signal"] != 0).sum()
    logger.info(f"信号总数: {signal_count} (多: {(klines['signal'] == 1).sum()}, 空: {(klines['signal'] == -1).sum()})")

    # ── 步骤 4: 配置回测引擎 ──
    logger.info("步骤 4/6: 配置回测引擎...")
    config = BacktestConfig(
        initial_capital=bt_config["initial_capital"],
        default_leverage=bt_config["leverage"],
        margin_mode=bt_config["margin_mode"],
        slippage_bps=bt_config["slippage_bps"],
        taker_fee=bt_config["taker_fee"],
        maker_fee=bt_config["maker_fee"],
        enable_funding=bt_config.get("enable_funding", True),
        enable_liquidation=bt_config.get("enable_liquidation", True),
        maintenance_margin_rate=bt_config.get("maintenance_margin_rate", 0.005),
    )
    engine = BacktestEngine(config)

    # 构建资金费率映射
    funding_map = merge_funding_rates(klines, funding, interval)

    # ── 步骤 5: 逐 bar 执行 ──
    logger.info("步骤 5/6: 执行回测...")
    leverage = bt_config["leverage"]
    position_pct = risk_params["position_size_pct"]
    sl_pct = risk_params["stop_loss_pct"]
    tp_pct = risk_params["take_profit_pct"]

    for i, row in klines.iterrows():
        dt = str(row["datetime"])
        price = row["close"]
        high = row["high"]
        low = row["low"]

        bar_prices = {
            symbol: {
                "close": price,
                "high": high,
                "low": low,
                "mark_price": price,
            }
        }

        # 检查当前 bar 是否有资金费率结算
        bar_funding = {}
        if funding_map:
            for f_dt, f_rate in funding_map.items():
                if f_dt.startswith(dt[:10]):
                    bar_funding[symbol] = f_rate

        pos = engine.get_position(symbol)
        signal = row["signal"]

        # 开多信号
        if signal == 1 and pos["side"] == "none":
            equity = engine.account.equity
            capital_for_position = equity * position_pct
            qty = (capital_for_position * leverage) / price
            if qty > 0:
                engine.open_long(symbol, qty, price, price, dt, leverage)
                engine.set_stop_loss(symbol, price * (1 - sl_pct))
                engine.set_take_profit(symbol, price * (1 + tp_pct))

        # 开空信号
        elif signal == -1 and pos["side"] == "none":
            equity = engine.account.equity
            capital_for_position = equity * position_pct
            qty = (capital_for_position * leverage) / price
            if qty > 0:
                engine.open_short(symbol, qty, price, price, dt, leverage)
                engine.set_stop_loss(symbol, price * (1 + sl_pct))
                engine.set_take_profit(symbol, price * (1 - tp_pct))

        # 平多信号
        elif signal == -1 and pos["side"] == "long":
            engine.close_long(symbol, 0, price, price, dt)

        # 平空信号
        elif signal == 1 and pos["side"] == "short":
            engine.close_short(symbol, 0, price, price, dt)

        engine.on_bar(dt, bar_prices, bar_funding if bar_funding else None)

    # ── 步骤 6: 输出结果 ──
    logger.info("步骤 6/6: 汇总结果...")
    result = engine.get_result()

    print("\n" + BacktestEngine.format_summary(result))

    # 输出交易日志
    trades = result.get("trade_log", [])
    if trades:
        print(f"\n─── 交易日志 ({len(trades)} 笔) ───")
        trade_df = pd.DataFrame(trades)
        cols = ["datetime", "side", "action", "quantity", "price",
                "leverage", "commission", "realized_pnl"]
        available_cols = [c for c in cols if c in trade_df.columns]
        print(trade_df[available_cols].to_string(index=False))

    return result


# ═══════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    spec_file = sys.argv[1] if len(sys.argv) > 1 else None
    spec = load_spec(spec_file)
    run_backtest(spec)
