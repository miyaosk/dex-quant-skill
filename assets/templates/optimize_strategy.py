"""
遗传寻优模板 — 自动搜索策略最优参数

用户说: "帮我找到 MACD 策略的最优参数"
→ Agent 定义参数空间 → 遗传算法搜索 → 输出最优参数 + 回测结果

本模板示例：优化均线交叉策略的 fast/slow 周期、止损止盈、杠杆
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
from loguru import logger

from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine
from scripts.signal_builder import build_ma_cross_strategy
from scripts.optimizer import GeneticOptimizer, GridSearch, ParameterSpace


# ═══════════════════════════════════════════
#  第 1 步：拉取数据（只拉一次，所有评估共用）
# ═══════════════════════════════════════════

SYMBOL = "BTC-USDT-PERP"
BINANCE_SYMBOL = "BTCUSDT"

logger.info("拉取回测数据...")
dc = DataClient()
klines = dc.get_perp_klines(BINANCE_SYMBOL, "1d", limit=365)

CLOSES = np.array([float(k["close"]) for k in klines])
HIGHS = np.array([float(k["high"]) for k in klines])
LOWS = np.array([float(k["low"]) for k in klines])
VOLUMES = np.array([float(k["volume"]) for k in klines])

logger.info(f"数据就绪: {len(CLOSES)} 根 K 线")


# ═══════════════════════════════════════════
#  第 2 步：定义适应度函数（一组参数 → 跑回测 → 返回夏普比率）
# ═══════════════════════════════════════════

def fitness_fn(params: dict) -> float:
    """用一组参数跑回测，返回夏普比率作为适应度。"""
    # 参数合法性校验
    if params["fast_period"] >= params["slow_period"]:
        return -999.0

    strategy = build_ma_cross_strategy(
        symbol=SYMBOL,
        fast_period=params["fast_period"],
        slow_period=params["slow_period"],
        leverage=params["leverage"],
        position_size=0.2,
        stop_loss_pct=params["stop_loss_pct"],
        take_profit_pct=params["take_profit_pct"],
    )

    engine = BacktestEngine(initial_capital=100_000)
    engine.set_leverage(SYMBOL, params["leverage"])

    warmup = params["slow_period"] + 5
    prev_ctx = None
    has_long = False
    has_short = False

    for i in range(warmup, len(CLOSES)):
        ctx = strategy.compute_context(
            CLOSES[:i + 1], HIGHS[:i + 1], LOWS[:i + 1], VOLUMES[:i + 1],
            prev_ctx=prev_ctx,
        )

        signals = strategy.evaluate(
            ctx, str(i), CLOSES[i],
            has_long=has_long, has_short=has_short,
        )

        for sig in signals:
            if sig.action == "open" and sig.side == "long":
                engine.open_long(SYMBOL, sig.quantity, sig.price)
                has_long = True
                if sig.stop_loss:
                    engine.set_stop_loss(SYMBOL, sig.stop_loss)
                if sig.take_profit:
                    engine.set_take_profit(SYMBOL, sig.take_profit)
            elif sig.action == "open" and sig.side == "short":
                engine.open_short(SYMBOL, sig.quantity, sig.price)
                has_short = True
                if sig.stop_loss:
                    engine.set_stop_loss(SYMBOL, sig.stop_loss)
                if sig.take_profit:
                    engine.set_take_profit(SYMBOL, sig.take_profit)
            elif sig.action == "close" and sig.side == "long":
                engine.close_long(SYMBOL, sig.price)
                has_long = False
            elif sig.action == "close" and sig.side == "short":
                engine.close_short(SYMBOL, sig.price)
                has_short = False

        prev_ctx = ctx

    metrics = engine.get_metrics()
    sharpe = metrics.get("sharpe_ratio", -999)
    return sharpe if isinstance(sharpe, (int, float)) and sharpe == sharpe else -999.0


# ═══════════════════════════════════════════
#  第 3 步：定义参数空间
# ═══════════════════════════════════════════

space = ParameterSpace()
space.add_int("fast_period", 5, 30)
space.add_int("slow_period", 20, 120)
space.add_float("stop_loss_pct", 0.02, 0.15)
space.add_float("take_profit_pct", 0.05, 0.40)
space.add_int("leverage", 1, 10)


# ═══════════════════════════════════════════
#  第 4 步：运行寻优
# ═══════════════════════════════════════════

def run_genetic():
    """遗传算法寻优（推荐，参数空间大时用）"""
    optimizer = GeneticOptimizer(
        space=space,
        fitness_fn=fitness_fn,
        population_size=30,
        generations=20,
        mutation_rate=0.15,
        early_stop_generations=8,
        seed=42,
    )
    result = optimizer.run()
    print("\n" + result.summary())
    return result


def run_grid():
    """网格搜索（参数空间小时用）"""
    grid = GridSearch(
        param_grid={
            "fast_period": [5, 10, 15, 20],
            "slow_period": [30, 50, 80, 120],
            "stop_loss_pct": [0.03, 0.05, 0.10],
            "take_profit_pct": [0.10, 0.20, 0.30],
            "leverage": [3, 5, 10],
        },
        fitness_fn=fitness_fn,
    )
    result = grid.run()
    print("\n" + result.summary())
    return result


if __name__ == "__main__":
    # 遗传算法（默认）
    result = run_genetic()

    # 用最优参数跑一次完整回测，展示详细信号
    print("\n\n" + "=" * 70)
    print("  用最优参数跑完整回测...")
    print("=" * 70)

    best = result.best_params
    strategy = build_ma_cross_strategy(
        symbol=SYMBOL,
        fast_period=best["fast_period"],
        slow_period=best["slow_period"],
        leverage=best["leverage"],
        stop_loss_pct=best["stop_loss_pct"],
        take_profit_pct=best["take_profit_pct"],
    )

    engine = BacktestEngine(initial_capital=100_000)
    engine.set_leverage(SYMBOL, best["leverage"])

    warmup = best["slow_period"] + 5
    prev_ctx = None
    has_long, has_short = False, False

    for i in range(warmup, len(CLOSES)):
        ctx = strategy.compute_context(
            CLOSES[:i + 1], HIGHS[:i + 1], LOWS[:i + 1], VOLUMES[:i + 1],
            prev_ctx=prev_ctx,
        )
        signals = strategy.evaluate(ctx, str(i), CLOSES[i], has_long, has_short)
        for sig in signals:
            if sig.action == "open" and sig.side == "long":
                engine.open_long(SYMBOL, sig.quantity, sig.price)
                has_long = True
            elif sig.action == "open" and sig.side == "short":
                engine.open_short(SYMBOL, sig.quantity, sig.price)
                has_short = True
            elif sig.action == "close" and sig.side == "long":
                engine.close_long(SYMBOL, sig.price)
                has_long = False
            elif sig.action == "close" and sig.side == "short":
                engine.close_short(SYMBOL, sig.price)
                has_short = False
        prev_ctx = ctx

    metrics = engine.get_metrics()
    print(f"\n  最优参数: {best}")
    print(f"  夏普比率: {metrics.get('sharpe_ratio', 0):.4f}")
    print(f"  总收益率: {metrics.get('total_return', 0):.2%}")
    print(f"  最大回撤: {metrics.get('max_drawdown', 0):.2%}")
    print(f"  总交易数: {metrics.get('total_trades', 0)}")
    print(f"\n{strategy.signal_log.summary()}")
