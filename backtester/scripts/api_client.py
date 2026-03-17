"""
DEX Quant Server API 客户端 — 信号驱动架构（含 Token 认证）

Skill 端调用流程:
  1. strategy-maker 生成策略脚本
  2. 本地运行脚本，拿到信号列表
  3. 调 run_backtest() 把信号发给 Server（自动携带 Token）
  4. Server 拉 K 线（带缓存）+ 回测引擎回放信号
  5. 返回绩效结果，展示给用户

认证:
  - 首次使用自动注册机器码，获取 Token（免费 3 个策略配额）
  - Token 缓存在 ~/.dex-quant/config.json
  - 所有请求自动携带 X-Token 头

用法:
    client = QuantAPIClient("http://your-server:8000")
    result = client.run_backtest(
        strategy_name="BTC MACD 策略",
        symbol="BTCUSDT",
        timeframe="1h",
        start_date="2024-01-01",
        end_date="2024-12-31",
        signals=[...],
    )
    client.print_metrics(result)
"""

from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger

from machine_auth import MachineAuth

DEFAULT_SERVER_URL = "https://quant.qa1.dex.hashkeydev.com"
API_PREFIX = "/api/v1"


class QuantAPIClient:
    """DEX Quant Server HTTP 客户端（自动认证）"""

    def __init__(self, server_url: str = DEFAULT_SERVER_URL, timeout: float = 300.0):
        self.server_url = server_url
        self.base_url = server_url.rstrip("/") + API_PREFIX
        self._client = httpx.Client(timeout=timeout)

        self._auth = MachineAuth(server_url)
        self._token = self._auth.register_or_load()

    def _headers(self) -> dict:
        return {"X-Token": self._token}

    # ═══════════════ 回测 ═══════════════

    def run_backtest(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        signals: list[dict],
        strategy_id: str = "",
        initial_capital: float = 100_000.0,
        leverage: int = 1,
        fee_rate: float = 0.0005,
        slippage_bps: float = 5.0,
        margin_mode: str = "isolated",
        direction: str = "long_short",
    ) -> dict:
        """
        提交信号驱动回测。

        参数:
            strategy_name: 策略名称
            symbol: 交易对 (BTCUSDT)
            timeframe: K 线周期 (15m / 1h / 2h / 1d)
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            signals: 信号列表，每个信号包含:
                timestamp, symbol, action (buy/sell/close),
                direction (long/short), confidence, reason,
                price_at_signal, suggested_stop_loss, suggested_take_profit

        返回:
            BacktestResponse 字典:
                backtest_id, status, metrics, trades, equity_curve, conclusion
        """
        payload = {
            "strategy_name": strategy_name,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "signals": signals,
            "initial_capital": initial_capital,
            "leverage": leverage,
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
            "margin_mode": margin_mode,
            "direction": direction,
        }

        logger.info(
            "提交回测 | {} {} {} | {} → {} | {} 个信号",
            strategy_name, symbol, timeframe, start_date, end_date, len(signals),
        )
        resp = self._client.post(f"{self.base_url}/backtest/run", json=payload, headers=self._headers())
        resp.raise_for_status()
        result = resp.json()

        status = result.get("status", "unknown")
        if status == "completed":
            metrics = result.get("metrics", {})
            logger.info(
                "回测完成 | 收益={:.2%} | Sharpe={:.2f} | 回撤={:.2%} | "
                "交易={} | 结论={}",
                metrics.get("total_return_pct", 0),
                metrics.get("sharpe_ratio", 0),
                abs(metrics.get("max_drawdown_pct", 0)),
                metrics.get("total_trades", 0),
                result.get("conclusion", ""),
            )
        else:
            logger.error("回测失败 | {}", result.get("error"))

        return result

    def get_backtest(self, backtest_id: str) -> dict:
        """查询已保存的回测结果"""
        resp = self._client.get(f"{self.base_url}/backtest/{backtest_id}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_trades(self, backtest_id: str) -> dict:
        """获取回测交易记录"""
        resp = self._client.get(f"{self.base_url}/backtest/{backtest_id}/trades", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_equity(self, backtest_id: str) -> dict:
        """获取权益曲线"""
        resp = self._client.get(f"{self.base_url}/backtest/{backtest_id}/equity", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 数据 ═══════════════

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        exchange: str = "binance",
    ) -> list[dict]:
        """获取 K 线数据（Server 端带缓存，同币同周期不重复下载）"""
        payload = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "exchange": exchange,
        }
        resp = self._client.post(f"{self.base_url}/data/klines", json=payload, headers=self._headers())
        resp.raise_for_status()
        result = resp.json()
        logger.info("K线 | {} {} | {} 条", symbol, interval, result.get("rows", 0))
        return result.get("data", [])

    def list_symbols(self, exchange: str = "binance") -> list[str]:
        """列出可用交易对"""
        resp = self._client.get(f"{self.base_url}/data/symbols", params={"exchange": exchange}, headers=self._headers())
        resp.raise_for_status()
        return resp.json().get("symbols", [])

    # ═══════════════ 策略 ═══════════════

    def save_strategy(
        self,
        name: str,
        script_content: str = "",
        description: str = "",
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        direction: str = "long_short",
        version: str = "v1.0",
        tags: list[str] = None,
    ) -> dict:
        """保存策略到 Server（含脚本源码）"""
        payload = {
            "name": name,
            "description": description,
            "script_content": script_content,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "version": version,
            "tags": tags or [],
        }
        resp = self._client.post(f"{self.base_url}/strategies/", json=payload, headers=self._headers())
        resp.raise_for_status()
        result = resp.json()
        logger.info("策略已保存 | {} ({})", name, result.get("strategy_id", ""))
        return result

    def list_strategies(self) -> list[dict]:
        """列出所有策略"""
        resp = self._client.get(f"{self.base_url}/strategies/", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_strategy(self, strategy_id: str) -> dict:
        """获取策略详情（含脚本源码）"""
        resp = self._client.get(f"{self.base_url}/strategies/{strategy_id}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 信号 ═══════════════

    def save_signals(self, strategy_id: str, signals: list[dict]) -> dict:
        """批量保存信号到 Server"""
        resp = self._client.post(
            f"{self.base_url}/signals/batch",
            json=signals,
            params={"strategy_id": strategy_id},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def query_signals(
        self,
        strategy_id: str = None,
        symbol: str = None,
        start_date: str = None,
        end_date: str = None,
        limit: int = 200,
    ) -> dict:
        """查询信号"""
        payload = {"limit": limit}
        if strategy_id:
            payload["strategy_id"] = strategy_id
        if symbol:
            payload["symbol"] = symbol
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        resp = self._client.post(f"{self.base_url}/signals/query", json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # ═══════════════ 服务器端执行回测 ═══════════════

    def run_server_backtest(
        self,
        script_content: str,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy_id: str = "",
        initial_capital: float = 100_000.0,
        leverage: int = 1,
        fee_rate: float = 0.0005,
        slippage_bps: float = 5.0,
        margin_mode: str = "isolated",
        direction: str = "long_short",
    ) -> dict:
        """
        服务器端一站式回测 — 上传脚本，服务器执行+回测。

        与 run_backtest() 的区别:
        - run_backtest(): 本地跑脚本生成信号，只传信号给服务器
        - run_server_backtest(): 把脚本源码传给服务器，服务器执行一切
        """
        payload = {
            "script_content": script_content,
            "strategy_name": strategy_name,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "leverage": leverage,
            "fee_rate": fee_rate,
            "slippage_bps": slippage_bps,
            "margin_mode": margin_mode,
            "direction": direction,
        }

        logger.info(
            "上传脚本到服务器执行 | {} {} {} | {} → {}",
            strategy_name, symbol, timeframe, start_date, end_date,
        )
        resp = self._client.post(
            f"{self.base_url}/backtest/run-server",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        result = resp.json()

        status = result.get("status", "unknown")
        if status == "completed":
            metrics = result.get("metrics", {})
            logger.info(
                "服务器回测完成 | 收益={:.2%} | Sharpe={:.2f} | 交易={} | 结论={}",
                metrics.get("total_return_pct", 0),
                metrics.get("sharpe_ratio", 0),
                metrics.get("total_trades", 0),
                result.get("conclusion", ""),
            )
        else:
            logger.error("服务器回测失败 | {}", result.get("error"))

        return result

    # ═══════════════ 配额 ═══════════════

    def check_quota(self) -> dict:
        """查询当前机器码的策略配额"""
        return self._auth.check_quota()

    def print_quota(self) -> None:
        """打印配额信息"""
        self._auth.print_quota()

    # ═══════════════ 展示工具 ═══════════════

    @staticmethod
    def print_metrics(result: dict) -> None:
        """格式化打印回测结果"""
        if result.get("status") != "completed":
            print(f"回测失败: {result.get('error', '未知错误')}")
            return

        m = result.get("metrics", {})
        conclusion = result.get("conclusion", "")
        conclusion_map = {
            "approved": "✅ 通过 — 可以上线",
            "paper_trade_first": "⚠️  先模拟 — 建议观察",
            "rejected": "❌ 驳回 — 需要调整",
        }

        print("\n" + "=" * 55)
        print("  回测绩效报告")
        print("=" * 55)
        print(f"  策略:          {result.get('strategy_name', '')}")
        print(f"  结论:          {conclusion_map.get(conclusion, conclusion)}")
        print("-" * 55)
        print(f"  总收益率:      {m.get('total_return_pct', 0):>+10.2%}")
        print(f"  年化收益:      {m.get('annual_return_pct', 0):>+10.2%}")
        print(f"  Sharpe:        {m.get('sharpe_ratio', 0):>10.3f}")
        print(f"  Sortino:       {m.get('sortino_ratio', 0):>10.3f}")
        print(f"  最大回撤:      {abs(m.get('max_drawdown_pct', 0)):>10.2%}")
        print(f"  Calmar:        {m.get('calmar_ratio', 0):>10.3f}")
        print("-" * 55)
        print(f"  胜率:          {m.get('win_rate', 0):>10.2%}")
        print(f"  盈亏比:        {m.get('profit_loss_ratio', 0):>10.2f}")
        print(f"  总交易数:      {m.get('total_trades', 0):>10d}")
        print(f"  盈利交易:      {m.get('winning_trades', 0):>10d}")
        print(f"  亏损交易:      {m.get('losing_trades', 0):>10d}")
        print(f"  平均持仓:      {m.get('avg_holding_bars', 0):>10.1f} bars")
        print("-" * 55)
        print(f"  总手续费:      {m.get('total_commission', 0):>10.2f}")
        print(f"  总滑点成本:    {m.get('total_slippage_cost', 0):>10.2f}")
        print(f"  资金费率净值:  {m.get('net_funding', 0):>+10.2f}")
        print(f"  爆仓次数:      {m.get('liquidation_count', 0):>10d}")
        print("-" * 55)
        print(f"  总信号数:      {m.get('total_signals', 0):>10d}")
        print(f"  已执行信号:    {m.get('signals_executed', 0):>10d}")
        print(f"  最终余额:      {m.get('final_balance', 0):>10.2f}")
        print("=" * 55)

    @staticmethod
    def print_trades(result: dict, limit: int = 20) -> None:
        """格式化打印交易记录"""
        trades = result.get("trades", [])
        if not trades:
            print("无交易记录")
            return

        print(f"\n交易记录（共 {len(trades)} 笔，显示前 {min(limit, len(trades))} 笔）")
        print("-" * 100)
        print(f"{'#':>4} {'时间':<20} {'动作':<10} {'方向':<6} {'价格':>12} {'数量':>10} {'盈亏':>12} {'余额':>14}")
        print("-" * 100)

        for t in trades[:limit]:
            print(
                f"{t.get('trade_id', 0):>4} "
                f"{t.get('datetime', ''):<20} "
                f"{t.get('action', ''):<10} "
                f"{t.get('side', ''):<6} "
                f"{t.get('price', 0):>12.2f} "
                f"{t.get('quantity', 0):>10.4f} "
                f"{t.get('pnl', 0):>+12.2f} "
                f"{t.get('balance_after', 0):>14.2f}"
            )

        if len(trades) > limit:
            print(f"  ... 还有 {len(trades) - limit} 笔交易")
        print("-" * 100)

    @staticmethod
    def print_conclusion(result: dict) -> None:
        """打印回测结论和建议"""
        conclusion = result.get("conclusion", "")
        metrics = result.get("metrics", {})

        print("\n" + "=" * 50)
        if conclusion == "approved":
            print("  结论: 通过")
            print("  建议: 可以进入监控执行阶段")
        elif conclusion == "paper_trade_first":
            print("  结论: 先模拟")
            print("  建议: 先跑模拟盘观察 1-2 周")
        elif conclusion == "rejected":
            print("  结论: 驳回")
            print("  建议: 调整策略参数后重新回测")
        else:
            print(f"  结论: {conclusion}")

        if metrics:
            issues = []
            if metrics.get("total_return_pct", 0) < 0:
                issues.append("总收益为负")
            if abs(metrics.get("max_drawdown_pct", 0)) > 0.2:
                issues.append("最大回撤超过 20%")
            if metrics.get("sharpe_ratio", 0) < 1.0:
                issues.append("夏普比率低于 1.0")
            if metrics.get("win_rate", 0) < 0.3:
                issues.append("胜率低于 30%")
            if metrics.get("liquidation_count", 0) > 0:
                issues.append(f"发生 {metrics['liquidation_count']} 次爆仓")

            if issues:
                print("  风险点:")
                for issue in issues:
                    print(f"    - {issue}")
        print("=" * 50)

    # ═══════════════ 生命周期 ═══════════════

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
