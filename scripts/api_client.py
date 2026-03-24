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

import time as _time
from typing import Optional

import httpx
from loguru import logger

from machine_auth import MachineAuth

DEFAULT_SERVER_URL = "https://generous-hope-production-6cf6.up.railway.app"
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

    def submit_backtest(
        self,
        script_content: str,
        strategy_name: str,
        symbol: str = "BTCUSDT",
        timeframe: str = "4h",
        start_date: str = "",
        end_date: str = "",
        strategy_id: str = "",
        initial_capital: float = 100_000.0,
        leverage: int = 1,
        fee_rate: float = 0.0005,
        slippage_bps: float = 5.0,
        margin_mode: str = "isolated",
        direction: str = "long_short",
    ) -> str:
        """
        提交回测任务，立即返回 job_id（不等待结果）。

        用 check_backtest(job_id) 查看进度和获取结果。
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

        resp = self._client.post(
            f"{self.base_url}/backtest/submit",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        job_id = resp.json()["job_id"]
        print(f"📋 回测已提交: {job_id} | {strategy_name} ({symbol} {timeframe}, {start_date} → {end_date})")
        return job_id

    def check_backtest(self, job_id: str) -> dict:
        """
        查询回测任务状态。返回 dict，status 为 running/completed/failed。

        completed 时包含完整的 metrics/trades/equity_curve。
        """
        resp = self._client.get(
            f"{self.base_url}/backtest/job/{job_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        job = resp.json()

        status = job.get("status", "running")
        stage = job.get("stage_label", "")
        progress = job.get("progress_pct", 0)
        elapsed_s = job.get("elapsed_ms", 0) / 1000

        if status == "running":
            print(f"⏳ [{elapsed_s:.0f}s] {stage} ({progress:.0f}%)")
        elif status == "completed":
            print(f"✅ 回测完成（耗时 {elapsed_s:.1f}s）")
        elif status == "failed":
            print(f"❌ 回测失败: {job.get('error', '未知错误')}")

        return job

    def run_server_backtest(
        self,
        script_content: str,
        strategy_name: str,
        symbol: str = "BTCUSDT",
        timeframe: str = "4h",
        start_date: str = "",
        end_date: str = "",
        strategy_id: str = "",
        initial_capital: float = 100_000.0,
        leverage: int = 1,
        fee_rate: float = 0.0005,
        slippage_bps: float = 5.0,
        margin_mode: str = "isolated",
        direction: str = "long_short",
        poll_interval: float = 5.0,
    ) -> dict:
        """
        提交 + 轮询一步到位（适合支持流式输出的平台）。

        如果平台不支持流式输出（如 OpenClaw），请改用：
        1. job_id = client.submit_backtest(...)
        2. result = client.check_backtest(job_id)
        """
        job_id = self.submit_backtest(
            script_content=script_content,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy_id=strategy_id,
            initial_capital=initial_capital,
            leverage=leverage,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            margin_mode=margin_mode,
            direction=direction,
        )

        while True:
            _time.sleep(poll_interval)
            job = self.check_backtest(job_id)
            if job.get("status") in ("completed", "failed"):
                return job

    # ═══════════════ 参数优化 ═══════════════

    def run_optimization(
        self,
        script_content: str,
        params: list[dict],
        strategy_name: str = "",
        symbol: str = "BTCUSDT",
        timeframe: str = "4h",
        start_date: str = "",
        end_date: str = "",
        initial_capital: float = 100_000.0,
        leverage: int = 3,
        fee_rate: float = 0.0005,
        slippage_bps: float = 5.0,
        margin_mode: str = "isolated",
        direction: str = "long_short",
        method: str = "grid",
        max_combinations: int = 200,
        fitness_metric: str = "sharpe_ratio",
        poll_interval: int = 10,
    ) -> dict:
        """
        参数优化 — 提交任务后自动轮询进度，完成后返回结果。

        脚本中用 PARAMS['xxx'] 引用可调参数。
        服务器异步执行，客户端每 poll_interval 秒查一次进度并打印。

        参数:
            params: 参数空间列表，每项:
                {"name": "fast_ema", "type": "int", "low": 5, "high": 30, "step": 5}
                {"name": "sl_pct", "type": "float", "low": 0.01, "high": 0.10, "step": 0.01}
                {"name": "direction", "type": "choice", "choices": ["long", "short"]}
            method: 搜索算法
                "grid"      — 网格穷举（组合数 ≤ 200）
                "genetic"   — 遗传算法（推荐，大空间通用）
                "bayesian"  — 贝叶斯 TPE（少量评估快速收敛）
                "random"    — 随机采样
                "annealing" — 模拟退火
                "pso"       — 粒子群优化
            fitness_metric: 优化目标 (sharpe_ratio / total_return_pct / sortino_ratio / win_rate)
            poll_interval: 轮询间隔秒数（默认10秒）

        返回:
            {status, best_params, best_fitness, results: [{rank, params, fitness, metrics...}]}
        """
        payload = {
            "script_content": script_content,
            "params": params,
            "strategy_name": strategy_name,
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
            "method": method,
            "max_combinations": max_combinations,
            "fitness_metric": fitness_metric,
        }

        logger.info(
            "提交参数优化 | {} {} {} | {} → {} | 目标={}",
            strategy_name, symbol, timeframe, start_date, end_date, fitness_metric,
        )

        resp = self._client.post(
            f"{self.base_url}/backtest/optimize",
            json=payload,
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        submit_result = resp.json()

        job_id = submit_result.get("job_id")
        total = submit_result.get("total_combinations", 0)
        logger.info("任务已提交 | job_id={} | 共{}种组合", job_id, total)
        print(f"\n⏳ 优化任务已提交 (job_id: {job_id})，共 {total} 种参数组合\n")

        last_completed = 0
        printed_milestones = set()
        milestones = {25, 50, 90}
        interval = 5

        while True:
            _time.sleep(interval)

            try:
                resp = self._client.get(
                    f"{self.base_url}/backtest/optimize/{job_id}",
                    headers=self._headers(),
                    timeout=15.0,
                )
                resp.raise_for_status()
                progress = resp.json()
            except Exception as e:
                logger.warning("查询进度失败: {}", e)
                interval = min(interval * 2, 300)
                continue

            status = progress.get("status", "running")
            completed = progress.get("completed", 0)
            failed = progress.get("failed", 0)
            progress_pct = progress.get("progress_pct", 0)
            best_fitness = progress.get("current_best_fitness", 0)
            best_params = progress.get("current_best_params", {})
            elapsed = progress.get("elapsed_ms", 0)

            for ms in sorted(milestones):
                if ms not in printed_milestones and progress_pct >= ms:
                    params_str = ", ".join(f"{k}={v}" for k, v in best_params.items()) if best_params else "-"
                    print(
                        f"   📊 {ms}% ({completed}/{total}) | "
                        f"最优 fitness={best_fitness:.4f} | "
                        f"{params_str} | "
                        f"{elapsed/1000:.0f}s"
                    )
                    printed_milestones.add(ms)

            if completed > last_completed:
                done_delta = completed - last_completed
                time_per_item = (elapsed / 1000) / max(completed, 1)
                remaining = (total - completed) * time_per_item
                interval = max(5, min(remaining / 4, 300))
            last_completed = completed

            if status == "completed":
                logger.info(
                    "优化完成 | 评估={} 失败={} | 最优fitness={:.4f} | 耗时={}ms",
                    completed - failed, failed, best_fitness, elapsed,
                )
                return progress

            if status == "failed":
                logger.error("优化失败: {}", progress.get("error", ""))
                print(f"\n❌ 优化失败: {progress.get('error', '未知错误')}")
                return progress

    @staticmethod
    def print_optimization(result: dict) -> None:
        """格式化打印参数优化结果。"""
        status = result.get("status", "")
        if status != "completed":
            print(f"优化失败: {result.get('error', '未知错误')}")
            return

        total = result.get("total", result.get("total_combinations", 0))
        completed = result.get("completed", result.get("evaluated", 0))
        failed = result.get("failed", 0)

        print("\n" + "=" * 70)
        print("  参数优化结果")
        print("=" * 70)
        print(f"  总组合数:      {total}")
        print(f"  成功评估:      {completed - failed}")
        print(f"  失败:          {failed}")
        print(f"  耗时:          {result.get('elapsed_ms', 0)/1000:.1f}s")
        print("-" * 70)
        print(f"  🏆 最优参数:   {result.get('best_params', result.get('current_best_params', {}))}")
        print(f"  🏆 最优fitness: {result.get('best_fitness', result.get('current_best_fitness', 0)):.6f}")
        print("=" * 70)

        results = result.get("results", [])
        if results:
            print(f"\n{'排名':>4}  {'收益率':>8}  {'Sharpe':>7}  {'回撤':>7}  {'胜率':>6}  {'交易':>4}  参数")
            print("-" * 70)
            for r in results[:10]:
                params_str = ", ".join(f"{k}={v}" for k, v in r.get("params", {}).items())
                print(
                    f"  #{r.get('rank', 0):<3}"
                    f"  {r.get('total_return_pct', 0):>+7.2%}"
                    f"  {r.get('sharpe_ratio', 0):>7.2f}"
                    f"  {r.get('max_drawdown_pct', 0):>7.2%}"
                    f"  {r.get('win_rate', 0):>5.1%}"
                    f"  {r.get('total_trades', 0):>4}"
                    f"  {params_str}"
                )
            print()

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
        """格式化打印回测结果（含结论）"""
        if result.get("status") != "completed":
            print(f"回测失败: {result.get('error', '未知错误')}")
            return

        m = result.get("metrics", {})
        conclusion = result.get("conclusion", "")
        conclusion_map = {
            "approved": "✅ 通过",
            "paper_trade_first": "⚠️ 先模拟",
            "rejected": "❌ 驳回",
        }

        ret = m.get('total_return_pct', 0)
        bal = m.get('final_balance', 0)

        print(f"\n{'─' * 40}")
        print(f"  {result.get('strategy_name', '策略')}  {conclusion_map.get(conclusion, conclusion)}")
        print(f"{'─' * 40}")
        print(f"  收益  {ret:>+.2%}    余额  {bal:>,.0f}")
        print(f"  Sharpe {m.get('sharpe_ratio', 0):>.2f}    Sortino {m.get('sortino_ratio', 0):>.2f}")
        print(f"  回撤  {abs(m.get('max_drawdown_pct', 0)):>.2%}    胜率  {m.get('win_rate', 0):>.1%}")
        print(f"  交易  {m.get('total_trades', 0)}笔    盈亏比  {m.get('profit_loss_ratio', 0):>.2f}")
        if m.get('liquidation_count', 0) > 0:
            print(f"  ⚠ 爆仓 {m['liquidation_count']} 次")
        print(f"{'─' * 40}")

    @staticmethod
    def print_trades(result: dict, limit: int = 20) -> None:
        """打印交易记录（默认不调用）"""
        trades = result.get("trades", [])
        if not trades:
            return
        print(f"\n交易记录（共 {len(trades)} 笔，显示前 {min(limit, len(trades))} 笔）")
        print(f"{'#':>3} {'时间':<20} {'动作':<8} {'方向':<5} {'价格':>10} {'盈亏':>10}")
        for t in trades[:limit]:
            print(
                f"{t.get('trade_id', 0):>3} "
                f"{t.get('datetime', ''):<20} "
                f"{t.get('action', ''):<8} "
                f"{t.get('side', ''):<5} "
                f"{t.get('price', 0):>10.2f} "
                f"{t.get('pnl', 0):>+10.2f}"
            )

    @staticmethod
    def print_conclusion(result: dict) -> None:
        """兼容旧调用，现在 print_metrics 已包含结论"""
        pass

    # ═══════════════ 生命周期 ═══════════════

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
