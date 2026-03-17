"""
本地回测引擎 — 永续合约专项

支持:
  - 多空双向持仓
  - 逐仓/全仓保证金
  - 杠杆 1x-125x
  - 资金费率每 8h 结算（使用真实历史数据）
  - 强制平仓
  - 止损/止盈
  - 固定滑点
  - 手续费（Maker/Taker）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


# ═══════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════

@dataclass
class Position:
    """单个持仓。"""
    symbol: str
    side: str = "none"          # "long" / "short" / "none"
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    leverage: int = 1
    margin: float = 0.0
    margin_mode: str = "isolated"
    maintenance_margin_rate: float = 0.005
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0

    @property
    def nominal_value(self) -> float:
        return self.quantity * self.avg_entry_price

    def calc_unrealized_pnl(self, mark_price: float) -> float:
        if self.side == "long":
            return self.quantity * (mark_price - self.avg_entry_price)
        elif self.side == "short":
            return self.quantity * (self.avg_entry_price - mark_price)
        return 0.0

    def calc_liquidation_price(self) -> float:
        """
        逐仓强平价格:
            多单: entry × (1 - 1/leverage + mmr)
            空单: entry × (1 + 1/leverage - mmr)
        """
        if self.quantity == 0 or self.side == "none":
            return 0.0
        mmr = self.maintenance_margin_rate
        if self.side == "long":
            return self.avg_entry_price * (1 - 1 / self.leverage + mmr)
        else:
            return self.avg_entry_price * (1 + 1 / self.leverage - mmr)

    def calc_margin_ratio(self, mark_price: float) -> float:
        """保证金率 = (保证金 + 未实现盈亏) / 名义价值"""
        nominal = self.quantity * mark_price
        if nominal == 0:
            return float("inf")
        pnl = self.calc_unrealized_pnl(mark_price)
        return (self.margin + pnl) / nominal


@dataclass
class TradeRecord:
    """单笔交易记录。"""
    datetime: str
    symbol: str
    side: str
    action: str           # "open" / "close" / "liquidation"
    quantity: float
    price: float
    mark_price: float
    leverage: int
    margin_used: float
    commission: float
    slippage: float
    funding_fee: float
    realized_pnl: float


@dataclass
class Account:
    """账户状态。"""
    initial_capital: float
    balance: float = 0.0
    positions: dict = field(default_factory=dict)
    trade_log: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    funding_log: list = field(default_factory=list)
    liquidation_count: int = 0
    total_commission: float = 0.0
    total_slippage_cost: float = 0.0
    total_funding_paid: float = 0.0
    total_funding_received: float = 0.0

    def __post_init__(self):
        self.balance = self.initial_capital

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.balance + self.total_unrealized_pnl

    @property
    def used_margin(self) -> float:
        return sum(p.margin for p in self.positions.values() if p.side != "none")

    @property
    def available_balance(self) -> float:
        return self.balance - self.used_margin


# ═══════════════════════════════════════════
#  回测配置
# ═══════════════════════════════════════════

@dataclass
class BacktestConfig:
    """回测引擎配置。所有参数均可外部化。"""
    initial_capital: float = 100_000.0
    default_leverage: int = 1
    margin_mode: str = "isolated"       # "isolated" / "cross"
    slippage_bps: float = 5.0           # 滑点（基点）
    taker_fee: float = 0.0005           # Taker 手续费 0.05%
    maker_fee: float = 0.0002           # Maker 手续费 0.02%
    enable_funding: bool = True         # 是否启用资金费率结算
    enable_liquidation: bool = True     # 是否启用强平检查
    maintenance_margin_rate: float = 0.005  # 维持保证金率 0.5%


# ═══════════════════════════════════════════
#  回测引擎
# ═══════════════════════════════════════════

class BacktestEngine:
    """
    永续合约回测引擎。

    使用方式:
        config = BacktestConfig(initial_capital=100000, default_leverage=5)
        engine = BacktestEngine(config)

        for i, row in df.iterrows():
            # 交易逻辑
            if signal_long:
                engine.open_long(symbol, qty, row["close"], row["close"], dt)
            # 每 bar 更新
            engine.on_bar(dt, prices, funding_rates)

        result = engine.get_result()
    """

    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.account = Account(initial_capital=self.config.initial_capital)

    # ── 交易操作 ──

    def open_long(self, symbol: str, qty: float, price: float,
                  mark_price: float, dt: str, leverage: int = None):
        """开多仓。"""
        self._open_position(symbol, "long", qty, price, mark_price, dt, leverage)

    def open_short(self, symbol: str, qty: float, price: float,
                   mark_price: float, dt: str, leverage: int = None):
        """开空仓。"""
        self._open_position(symbol, "short", qty, price, mark_price, dt, leverage)

    def close_long(self, symbol: str, qty: float, price: float,
                   mark_price: float, dt: str):
        """平多仓。qty=0 表示全部平仓。"""
        self._close_position(symbol, "long", qty, price, mark_price, dt)

    def close_short(self, symbol: str, qty: float, price: float,
                    mark_price: float, dt: str):
        """平空仓。qty=0 表示全部平仓。"""
        self._close_position(symbol, "short", qty, price, mark_price, dt)

    def set_stop_loss(self, symbol: str, price: float):
        """设置止损价。"""
        self.account.get_position(symbol).stop_loss = price

    def set_take_profit(self, symbol: str, price: float):
        """设置止盈价。"""
        self.account.get_position(symbol).take_profit = price

    def set_leverage(self, symbol: str, leverage: int):
        """设置杠杆倍数 (1-125)。"""
        pos = self.account.get_position(symbol)
        pos.leverage = max(1, min(125, leverage))

    def set_margin_mode(self, symbol: str, mode: str):
        """设置保证金模式: 'isolated' 或 'cross'。"""
        pos = self.account.get_position(symbol)
        pos.margin_mode = mode

    def get_position(self, symbol: str) -> dict:
        """获取当前持仓信息。"""
        pos = self.account.get_position(symbol)
        return {
            "side": pos.side,
            "quantity": pos.quantity,
            "avg_entry_price": pos.avg_entry_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "liquidation_price": pos.liquidation_price,
            "leverage": pos.leverage,
            "margin": pos.margin,
            "margin_ratio": pos.calc_margin_ratio(pos.avg_entry_price) if pos.side != "none" else 0,
        }

    # ── 内部: 开仓 ──

    def _open_position(self, symbol: str, side: str, qty: float, price: float,
                       mark_price: float, dt: str, leverage: int = None):
        pos = self.account.get_position(symbol)
        lev = leverage or pos.leverage or self.config.default_leverage
        pos.leverage = lev
        pos.margin_mode = pos.margin_mode or self.config.margin_mode
        pos.maintenance_margin_rate = self.config.maintenance_margin_rate

        slippage = price * self.config.slippage_bps / 10000
        fill_price = price + slippage if side == "long" else price - slippage

        nominal = qty * fill_price
        required_margin = nominal / lev
        commission = nominal * self.config.taker_fee

        if self.account.available_balance < required_margin + commission:
            logger.warning(
                f"[{dt}] 余额不足: 需要 {required_margin + commission:.2f}, "
                f"可用 {self.account.available_balance:.2f}"
            )
            return

        if pos.side == side and pos.quantity > 0:
            total_qty = pos.quantity + qty
            pos.avg_entry_price = (
                pos.avg_entry_price * pos.quantity + fill_price * qty
            ) / total_qty
            pos.quantity = total_qty
            pos.margin += required_margin
        else:
            pos.side = side
            pos.quantity = qty
            pos.avg_entry_price = fill_price
            pos.margin = required_margin

        pos.liquidation_price = pos.calc_liquidation_price()

        self.account.balance -= commission
        self.account.total_commission += commission
        self.account.total_slippage_cost += abs(slippage * qty)

        self.account.trade_log.append(TradeRecord(
            datetime=dt, symbol=symbol, side=side, action="open",
            quantity=qty, price=fill_price, mark_price=mark_price,
            leverage=lev, margin_used=required_margin,
            commission=commission, slippage=abs(slippage * qty),
            funding_fee=0.0, realized_pnl=0.0,
        ))

    # ── 内部: 平仓 ──

    def _close_position(self, symbol: str, side: str, qty: float, price: float,
                        mark_price: float, dt: str, action: str = "close"):
        pos = self.account.get_position(symbol)
        if pos.side != side or pos.quantity == 0:
            return

        close_qty = min(qty, pos.quantity) if qty else pos.quantity

        slippage = price * self.config.slippage_bps / 10000
        fill_price = price - slippage if side == "long" else price + slippage

        if side == "long":
            realized_pnl = close_qty * (fill_price - pos.avg_entry_price)
        else:
            realized_pnl = close_qty * (pos.avg_entry_price - fill_price)

        nominal = close_qty * fill_price
        commission = nominal * self.config.taker_fee

        margin_released = pos.margin * (close_qty / pos.quantity)
        pos.margin -= margin_released
        self.account.balance += margin_released + realized_pnl - commission
        self.account.total_commission += commission
        self.account.total_slippage_cost += abs(slippage * close_qty)

        pos.quantity -= close_qty
        if pos.quantity <= 1e-10:
            pos.quantity = 0
            pos.side = "none"
            pos.margin = 0
            pos.stop_loss = None
            pos.take_profit = None

        self.account.trade_log.append(TradeRecord(
            datetime=dt, symbol=symbol, side=side, action=action,
            quantity=close_qty, price=fill_price, mark_price=mark_price,
            leverage=pos.leverage, margin_used=0,
            commission=commission, slippage=abs(slippage * close_qty),
            funding_fee=0.0, realized_pnl=realized_pnl,
        ))

    # ── 每 bar 检查 ──

    def on_bar(self, dt: str, prices: dict[str, dict],
               funding_rates: dict[str, float] = None):
        """
        每个 bar 调用一次。

        执行顺序: 更新盈亏 → 资金费率结算 → 止损止盈 → 强平检查 → 记录净值

        参数:
            dt: 当前 bar 时间
            prices: {symbol: {"close": float, "high": float, "low": float, "mark_price": float}}
            funding_rates: {symbol: float} — 仅在 8h 结算时刻传入
        """
        for symbol, pos in list(self.account.positions.items()):
            if pos.side == "none":
                continue

            bar = prices.get(symbol, {})
            mark = bar.get("mark_price", bar.get("close", pos.avg_entry_price))

            pos.unrealized_pnl = pos.calc_unrealized_pnl(mark)

            if self.config.enable_funding and funding_rates and symbol in funding_rates:
                self._settle_funding(pos, funding_rates[symbol], mark, dt)

            if pos.side != "none":
                self._check_stop_loss_take_profit(pos, bar, dt)

            if self.config.enable_liquidation and pos.side != "none":
                self._check_liquidation(pos, mark, dt)

        self.account.equity_curve.append({
            "datetime": dt,
            "equity": self.account.equity,
            "balance": self.account.balance,
            "unrealized_pnl": self.account.total_unrealized_pnl,
            "used_margin": self.account.used_margin,
            "drawdown": 0.0,
        })

    def _settle_funding(self, pos: Position, funding_rate: float,
                        mark_price: float, dt: str):
        """资金费率结算。"""
        nominal = pos.quantity * mark_price
        fee = nominal * funding_rate

        if pos.side == "long":
            pos.margin -= fee
            self.account.balance -= fee
            if fee > 0:
                self.account.total_funding_paid += fee
            else:
                self.account.total_funding_received += abs(fee)
        else:
            pos.margin += fee
            self.account.balance += fee
            if fee > 0:
                self.account.total_funding_received += fee
            else:
                self.account.total_funding_paid += abs(fee)

        self.account.funding_log.append({
            "datetime": dt,
            "symbol": pos.symbol,
            "side": pos.side,
            "funding_rate": funding_rate,
            "position_value": nominal,
            "fee": fee,
        })

    def _check_stop_loss_take_profit(self, pos: Position, bar: dict, dt: str):
        """检查止损/止盈是否触发。"""
        high = bar.get("high", bar.get("close", 0))
        low = bar.get("low", bar.get("close", 0))
        mark = bar.get("mark_price", bar.get("close", 0))

        if pos.stop_loss is not None:
            triggered = (
                (pos.side == "long" and low <= pos.stop_loss)
                or (pos.side == "short" and high >= pos.stop_loss)
            )
            if triggered:
                logger.info(f"[{dt}] 止损触发: {pos.symbol} {pos.side} @ {pos.stop_loss}")
                self._close_position(
                    pos.symbol, pos.side, pos.quantity,
                    pos.stop_loss, mark, dt, "close",
                )
                return

        if pos.take_profit is not None:
            triggered = (
                (pos.side == "long" and high >= pos.take_profit)
                or (pos.side == "short" and low <= pos.take_profit)
            )
            if triggered:
                logger.info(f"[{dt}] 止盈触发: {pos.symbol} {pos.side} @ {pos.take_profit}")
                self._close_position(
                    pos.symbol, pos.side, pos.quantity,
                    pos.take_profit, mark, dt, "close",
                )

    def _check_liquidation(self, pos: Position, mark_price: float, dt: str):
        """强平检查。"""
        if pos.side == "none" or pos.quantity == 0:
            return

        margin_ratio = pos.calc_margin_ratio(mark_price)

        if margin_ratio <= pos.maintenance_margin_rate:
            logger.warning(
                f"[{dt}] 强平: {pos.symbol} {pos.side} "
                f"保证金率 {margin_ratio:.4f} <= {pos.maintenance_margin_rate}"
            )
            lost_margin = pos.margin
            pos.quantity = 0
            pos.side = "none"
            pos.margin = 0
            pos.unrealized_pnl = 0
            pos.stop_loss = None
            pos.take_profit = None

            self.account.liquidation_count += 1
            self.account.trade_log.append(TradeRecord(
                datetime=dt, symbol=pos.symbol, side=pos.side, action="liquidation",
                quantity=0, price=mark_price, mark_price=mark_price,
                leverage=pos.leverage, margin_used=0,
                commission=0, slippage=0, funding_fee=0,
                realized_pnl=-lost_margin,
            ))

    # ── 结果汇总 ──

    def get_result(self) -> dict:
        """获取完整回测结果。"""
        eq_df = pd.DataFrame(self.account.equity_curve)
        if eq_df.empty:
            return {"error": "无回测数据"}

        equities = eq_df["equity"].values
        peak = np.maximum.accumulate(equities)
        drawdowns = (equities - peak) / peak
        eq_df["drawdown"] = drawdowns

        returns = np.diff(equities) / equities[:-1] if len(equities) > 1 else np.array([0])

        total_return = (equities[-1] / equities[0]) - 1
        n_days = len(equities)
        annual_return = (1 + total_return) ** (365 / max(n_days, 1)) - 1
        volatility = float(np.std(returns) * np.sqrt(365)) if len(returns) > 1 else 0

        rf = 0.0
        sharpe = (annual_return - rf) / volatility if volatility > 0 else 0
        downside = returns[returns < 0]
        downside_std = float(np.std(downside) * np.sqrt(365)) if len(downside) > 0 else 0
        sortino = (annual_return - rf) / downside_std if downside_std > 0 else 0

        max_dd = float(np.min(drawdowns))
        max_dd_idx = int(np.argmin(drawdowns))
        peak_idx = int(np.argmax(equities[:max_dd_idx + 1])) if max_dd_idx > 0 else 0
        max_dd_duration = max_dd_idx - peak_idx

        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        trades = self.account.trade_log
        close_trades = [
            t for t in trades
            if t.action in ("close", "liquidation") and t.realized_pnl != 0
        ]
        wins = [t for t in close_trades if t.realized_pnl > 0]
        losses = [t for t in close_trades if t.realized_pnl < 0]
        win_rate = len(wins) / len(close_trades) if close_trades else 0
        avg_win = float(np.mean([t.realized_pnl for t in wins])) if wins else 0
        avg_loss = float(abs(np.mean([t.realized_pnl for t in losses]))) if losses else 0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

        net_funding = self.account.total_funding_received - self.account.total_funding_paid

        return {
            "performance": {
                "total_return": total_return,
                "annual_return": annual_return,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "max_drawdown": max_dd,
                "max_drawdown_duration": int(max_dd_duration),
                "calmar_ratio": calmar,
                "volatility": volatility,
                "win_rate": win_rate,
                "profit_loss_ratio": profit_loss_ratio,
                "total_trades": len(trades),
                "total_funding_paid": self.account.total_funding_paid,
                "total_funding_received": self.account.total_funding_received,
                "net_funding": net_funding,
                "total_commission": self.account.total_commission,
                "total_slippage_cost": self.account.total_slippage_cost,
                "liquidation_count": self.account.liquidation_count,
            },
            "equity_curve": eq_df.to_dict("records"),
            "trade_log": [vars(t) for t in trades],
            "funding_log": self.account.funding_log,
        }

    def get_metrics(self) -> dict:
        """获取绩效指标摘要（不含完整曲线和日志）。"""
        result = self.get_result()
        return result.get("performance", result)

    @staticmethod
    def format_summary(result: dict) -> str:
        """格式化输出回测结果摘要。"""
        p = result.get("performance", {})
        lines = [
            "═══ 回测结果摘要 ═══",
            f"总收益率:     {p.get('total_return', 0):.2%}",
            f"年化收益率:   {p.get('annual_return', 0):.2%}",
            f"夏普比率:     {p.get('sharpe_ratio', 0):.3f}",
            f"索提诺比率:   {p.get('sortino_ratio', 0):.3f}",
            f"最大回撤:     {p.get('max_drawdown', 0):.2%}",
            f"卡尔玛比率:   {p.get('calmar_ratio', 0):.3f}",
            f"年化波动率:   {p.get('volatility', 0):.2%}",
            f"胜率:         {p.get('win_rate', 0):.2%}",
            f"盈亏比:       {p.get('profit_loss_ratio', 0):.2f}",
            f"总交易次数:   {p.get('total_trades', 0)}",
            "─── 资金费率 ───",
            f"支付:         {p.get('total_funding_paid', 0):.2f} USDT",
            f"收到:         {p.get('total_funding_received', 0):.2f} USDT",
            f"净损益:       {p.get('net_funding', 0):.2f} USDT",
            "─── 费用与风控 ───",
            f"累计手续费:   {p.get('total_commission', 0):.2f} USDT",
            f"累计滑点:     {p.get('total_slippage_cost', 0):.2f} USDT",
            f"强平次数:     {p.get('liquidation_count', 0)}",
        ]
        return "\n".join(lines)
