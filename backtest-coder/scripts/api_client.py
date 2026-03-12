"""
DEX Quant Server API 客户端

替代本地回测引擎，将计算请求发送到后端服务器。
Skill 端只负责构造请求和展示结果，重计算在服务器完成。

用法:
    client = QuantAPIClient("http://localhost:8000")
    result = client.run_backtest(strategy_spec, backtest_config)
    client.print_metrics(result)
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
from loguru import logger

DEFAULT_SERVER_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"


class QuantAPIClient:
    """DEX Quant Server 的 HTTP 客户端"""

    def __init__(self, server_url: str = DEFAULT_SERVER_URL, timeout: float = 300.0):
        self.base_url = server_url.rstrip("/") + API_PREFIX
        self._client = httpx.Client(timeout=timeout)

    # ═══════════════ 回测 ═══════════════

    def run_backtest(
        self,
        strategy: dict,
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000.0,
        fee_rate: float = 0.0005,
        slippage_bps: float = 2.0,
        margin_mode: str = "isolated",
        funding_rate_enabled: bool = True,
    ) -> dict:
        """
        提交回测请求到服务器。

        参数:
            strategy: StrategySpec 字典
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"

        返回:
            BacktestResponse 字典，包含 metrics, trades, equity_curve
        """
        payload = {
            "strategy": strategy,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
            "margin_mode": margin_mode,
            "funding_rate_enabled": funding_rate_enabled,
        }

        logger.info("提交回测请求 | symbols={} | {} → {}", strategy.get("universe"), start_date, end_date)
        resp = self._client.post(f"{self.base_url}/backtest/run", json=payload)
        resp.raise_for_status()
        result = resp.json()

        status = result.get("status", "unknown")
        if status == "completed":
            metrics = result.get("metrics", {})
            logger.info(
                "回测完成 | 总收益={:.2f}% | Sharpe={:.2f} | 最大回撤={:.2f}% | 交易数={}",
                metrics.get("total_return_pct", 0),
                metrics.get("sharpe_ratio", 0),
                metrics.get("max_drawdown_pct", 0),
                metrics.get("total_trades", 0),
            )
        else:
            logger.error("回测失败 | error={}", result.get("error"))

        return result

    def get_backtest(self, backtest_id: str) -> dict:
        """查询已有的回测结果"""
        resp = self._client.get(f"{self.base_url}/backtest/{backtest_id}")
        resp.raise_for_status()
        return resp.json()

    def get_trades(self, backtest_id: str) -> list[dict]:
        """获取回测的交易记录"""
        resp = self._client.get(f"{self.base_url}/backtest/{backtest_id}/trades")
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 数据 ═══════════════

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        market: str = "crypto_futures",
    ) -> list[dict]:
        """获取 K 线数据（服务器端缓存）"""
        payload = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "market": market,
        }
        resp = self._client.post(f"{self.base_url}/data/klines", json=payload)
        resp.raise_for_status()
        result = resp.json()
        logger.info("获取 K 线 | {} {} | {} 条", symbol, interval, result.get("rows", 0))
        return result.get("data", [])

    def list_symbols(self) -> list[str]:
        """列出可用交易对"""
        resp = self._client.get(f"{self.base_url}/data/symbols")
        resp.raise_for_status()
        return resp.json().get("symbols", [])

    # ═══════════════ 策略 ═══════════════

    def save_strategy(self, spec: dict) -> dict:
        """保存策略到服务器"""
        resp = self._client.post(f"{self.base_url}/strategies/", json=spec)
        resp.raise_for_status()
        return resp.json()

    def list_strategies(self) -> list[dict]:
        """列出所有策略"""
        resp = self._client.get(f"{self.base_url}/strategies/")
        resp.raise_for_status()
        return resp.json()

    def get_strategy(self, strategy_id: str) -> dict:
        """获取策略详情"""
        resp = self._client.get(f"{self.base_url}/strategies/{strategy_id}")
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 信号 ═══════════════

    def save_signal(self, signal: dict) -> dict:
        """保存一条交易信号到服务器"""
        resp = self._client.post(f"{self.base_url}/signals/", json=signal)
        resp.raise_for_status()
        logger.info("信号已保存 | {} {} {}", signal.get("symbol"), signal.get("signal_type"), signal.get("signal_id"))
        return resp.json()

    def save_signals_batch(self, signals: list[dict]) -> dict:
        """批量保存信号"""
        resp = self._client.post(f"{self.base_url}/signals/batch", json=signals)
        resp.raise_for_status()
        return resp.json()

    def query_signals(
        self,
        strategy_id: str = None,
        symbol: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询信号"""
        payload = {"limit": limit}
        if strategy_id:
            payload["strategy_id"] = strategy_id
        if symbol:
            payload["symbol"] = symbol
        resp = self._client.post(f"{self.base_url}/signals/query", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_signal(self, signal_id: str) -> dict:
        """获取单条信号详情"""
        resp = self._client.get(f"{self.base_url}/signals/{signal_id}")
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 展示工具 ═══════════════

    @staticmethod
    def print_metrics(result: dict) -> None:
        """格式化打印回测结果"""
        if result.get("status") != "completed":
            print(f"回测失败: {result.get('error', '未知错误')}")
            return

        m = result.get("metrics", {})
        print("\n" + "=" * 50)
        print("  回测绩效报告")
        print("=" * 50)
        print(f"  总收益:        {m.get('total_return_pct', 0):>10.2f}%")
        print(f"  年化收益:      {m.get('annual_return_pct', 0):>10.2f}%")
        print(f"  Sharpe 比率:   {m.get('sharpe_ratio', 0):>10.2f}")
        print(f"  最大回撤:      {m.get('max_drawdown_pct', 0):>10.2f}%")
        print(f"  胜率:          {m.get('win_rate', 0):>10.2f}%")
        print(f"  盈亏比:        {m.get('profit_loss_ratio', 0):>10.2f}")
        print(f"  总交易数:      {m.get('total_trades', 0):>10d}")
        print(f"  盈利交易:      {m.get('winning_trades', 0):>10d}")
        print(f"  亏损交易:      {m.get('losing_trades', 0):>10d}")
        print(f"  总手续费:      {m.get('total_commission', 0):>10.2f}")
        print(f"  资金费率净值:  {m.get('net_funding', 0):>10.2f}")
        print(f"  爆仓次数:      {m.get('liquidation_count', 0):>10d}")
        print(f"  最终余额:      {m.get('final_balance', 0):>10.2f}")
        print("=" * 50)

    @staticmethod
    def print_trades(result: dict, limit: int = 20) -> None:
        """格式化打印交易记录"""
        trades = result.get("trades", [])
        if not trades:
            print("无交易记录")
            return

        print(f"\n交易记录（共 {len(trades)} 笔，显示前 {min(limit, len(trades))} 笔）")
        print("-" * 90)
        print(f"{'#':>4} {'时间':<20} {'动作':<12} {'价格':>12} {'数量':>10} {'盈亏':>12} {'余额':>14}")
        print("-" * 90)

        for t in trades[:limit]:
            pnl_str = f"{t.get('pnl', 0):+.2f}"
            print(
                f"{t.get('trade_id', 0):>4} "
                f"{t.get('datetime', ''):<20} "
                f"{t.get('action', ''):<12} "
                f"{t.get('price', 0):>12.2f} "
                f"{t.get('quantity', 0):>10.4f} "
                f"{pnl_str:>12} "
                f"{t.get('balance_after', 0):>14.2f}"
            )

        if len(trades) > limit:
            print(f"  ... 还有 {len(trades) - limit} 笔交易")
        print("-" * 90)

    # ═══════════════ 生命周期 ═══════════════

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
