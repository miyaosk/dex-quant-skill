"""
策略制作 Skill 完整测试
测试所有能力：模板运行、数据拉取、指标计算、外部 API、端到端场景
"""
import sys, os, json, time, traceback
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backtester", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "strategy-maker", "assets", "templates"))

RESULTS = []

def test(name, func):
    print(f"\n{'─'*50}")
    print(f"  测试: {name}")
    print(f"{'─'*50}")
    t0 = time.time()
    try:
        result = func()
        elapsed = time.time() - t0
        print(f"  ✅ 通过 ({elapsed:.2f}s)")
        RESULTS.append({"name": name, "status": "✅ 通过", "time": f"{elapsed:.2f}s", "detail": result or ""})
        return True
    except Exception as e:
        elapsed = time.time() - t0
        detail = f"{type(e).__name__}: {e}"
        print(f"  ❌ 失败 ({elapsed:.2f}s): {detail}")
        RESULTS.append({"name": name, "status": "❌ 失败", "time": f"{elapsed:.2f}s", "detail": detail})
        return False


# ══════════════════════════════════════════════════════
# 一、技术指标策略模板
# ══════════════════════════════════════════════════════

def test_technical_backtest():
    """技术指标模板 — 回测模式"""
    from technical_strategy import generate_signals
    result = generate_signals(mode="backtest", start_date="2024-10-01", end_date="2024-12-31")
    assert result["strategy_name"] == "BTC MACD 趋势跟踪"
    assert result["mode"] == "backtest"
    signals = result["signals"]
    assert len(signals) > 0, f"回测应产生信号，实际: 0"
    buys = [s for s in signals if s["action"] == "buy"]
    sells = [s for s in signals if s["action"] == "sell"]
    for s in signals:
        assert s["symbol"] == "BTCUSDT"
        assert s["action"] in ("buy", "sell")
        assert 0 <= s["confidence"] <= 1
        assert s["source_type"] == "technical"
        assert len(s["reason"]) > 0
    return f"{len(signals)} 个信号 (买 {len(buys)}, 卖 {len(sells)})"


def test_technical_live():
    """技术指标模板 — 实时模式"""
    from technical_strategy import generate_signals
    result = generate_signals(mode="live")
    assert "signals" in result
    assert result["mode"] == "live"
    return f"{len(result['signals'])} 个实时信号"


def test_technical_signal_format():
    """技术指标模板 — 信号格式校验"""
    from technical_strategy import generate_signals
    result = generate_signals(mode="backtest", start_date="2024-11-01", end_date="2024-12-31")
    schema_path = os.path.join(os.path.dirname(__file__), "shared", "schemas", "signal_format.json")
    with open(schema_path) as f:
        schema = json.load(f)
    required_top = schema["required"]
    for field in required_top:
        assert field in result, f"缺少顶层字段: {field}"
    signal_required = schema["definitions"]["Signal"]["required"]
    for s in result["signals"][:5]:
        for field in signal_required:
            assert field in s, f"信号缺少字段: {field}"
        assert s["action"] in ("buy", "sell", "close", "hold")
        assert s["source_type"] in ("technical", "social", "onchain", "mixed")
    return f"顶层 {len(required_top)} 字段 + 信号 {len(signal_required)} 字段全部符合"


# ══════════════════════════════════════════════════════
# 二、混合策略模板
# ══════════════════════════════════════════════════════

def test_mixed_backtest():
    """混合策略模板 — 回测模式"""
    from mixed_strategy import generate_signals
    result = generate_signals(mode="backtest", start_date="2024-01-01", end_date="2024-12-31")
    assert result["strategy_name"].startswith("ETH")
    assert "signals" in result
    return f"{len(result['signals'])} 个信号"


def test_mixed_live():
    """混合策略模板 — 实时模式（含资金费率）"""
    from mixed_strategy import generate_signals
    result = generate_signals(mode="live")
    assert "signals" in result
    return f"{len(result['signals'])} 个实时信号"


# ══════════════════════════════════════════════════════
# 三、社媒策略模板
# ══════════════════════════════════════════════════════

def test_social_no_key():
    """社媒策略模板 — 无 API Key 时的降级处理"""
    from social_strategy import generate_signals
    result = generate_signals(mode="live")
    assert "signals" in result
    assert isinstance(result["signals"], list)
    return f"无 Key 降级正常，返回 {len(result['signals'])} 个信号"


def test_social_backtest_warning():
    """社媒策略模板 — 回测模式应返回警告"""
    from social_strategy import generate_signals
    result = generate_signals(mode="backtest")
    assert "warning" in result, "回测模式应返回 warning 字段"
    assert len(result["signals"]) == 0
    return f"正确警告: {result['warning'][:40]}"


# ══════════════════════════════════════════════════════
# 四、数据客户端
# ══════════════════════════════════════════════════════

def test_binance_perp_klines():
    """Binance 永续 K 线"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_perp_klines("BTC-USDT-PERP", "1d", limit=10)
    c.close()
    assert len(df) >= 5
    assert "close" in df.columns
    return f"{len(df)} 条 K 线, 最新收盘: {df.iloc[-1]['close']}"


def test_binance_funding():
    """Binance 资金费率"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_funding_rate("BTC-USDT-PERP", limit=10)
    c.close()
    assert len(df) >= 5
    assert "funding_rate" in df.columns
    rate = df.iloc[-1]["funding_rate"]
    return f"{len(df)} 条, 最新费率: {rate:.6f}"


def test_binance_mark_price():
    """Binance 标记价格 + 持仓量"""
    from data_client import DataClient
    c = DataClient()
    info = c.get_mark_price("BTC-USDT-PERP")
    c.close()
    assert "mark_price" in info
    assert info["mark_price"] > 0
    return f"BTC 标记价: ${info['mark_price']:,.2f}"


def test_binance_spot():
    """Binance 现货 K 线"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_spot_klines("BTC-USDT", "1d", limit=5)
    c.close()
    assert len(df) >= 3
    return f"{len(df)} 条现货 K 线"


def test_yfinance_stock():
    """yfinance 美股"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_stock_klines("AAPL", "2024-12-01", "2024-12-31")
    c.close()
    assert len(df) >= 3
    return f"AAPL {len(df)} 条"


def test_yfinance_gold():
    """yfinance 黄金"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_metal_spot_klines("METAL:XAU-SPOT", "2024-12-01", "2024-12-31")
    c.close()
    assert len(df) >= 3
    return f"黄金 {len(df)} 条"


def test_defillama():
    """DeFi Llama TVL"""
    from data_client import DataClient
    c = DataClient()
    df = c.get_protocol_tvl("aave")
    c.close()
    assert len(df) > 0
    return f"Aave TVL 数据 {len(df)} 条"


# ══════════════════════════════════════════════════════
# 五、指标库
# ══════════════════════════════════════════════════════

def test_all_indicators():
    """12 个技术指标全量测试"""
    from indicators import Indicators
    import numpy as np
    np.random.seed(42)
    n = 200
    close = np.cumsum(np.random.randn(n)) + 100
    close = np.abs(close)
    high = close + np.abs(np.random.randn(n))
    low = close - np.abs(np.random.randn(n))
    volume = np.random.randint(1000, 10000, n).astype(float)

    results = {}
    sma = Indicators.sma(close, 20);         results["SMA"] = not np.isnan(sma[-1])
    ema = Indicators.ema(close, 20);         results["EMA"] = not np.isnan(ema[-1])
    rsi = Indicators.rsi(close, 14);         results["RSI"] = 0 <= rsi[-1] <= 100
    dif, dea, hist = Indicators.macd(close); results["MACD"] = not np.isnan(dif[-1])
    u, m, l = Indicators.bollinger_bands(close);  results["BB"] = u[-1] > m[-1] > l[-1]
    atr = Indicators.atr(high, low, close, 14); results["ATR"] = atr[-1] > 0
    k, d, j = Indicators.kdj(high, low, close); results["KDJ"] = not np.isnan(k[-1])

    fast = Indicators.sma(close, 10)
    slow = Indicators.sma(close, 30)
    co = Indicators.crossover(fast, slow);    results["crossover"] = co.dtype == bool
    cu = Indicators.crossunder(fast, slow);   results["crossunder"] = cu.dtype == bool
    hi = Indicators.highest(high, 20);        results["highest"] = not np.isnan(hi[-1])
    lo = Indicators.lowest(low, 20);          results["lowest"] = not np.isnan(lo[-1])
    vm = Indicators.volume_ma(volume, 20);    results["volume_ma"] = not np.isnan(vm[-1])

    failed = [k for k, v in results.items() if not v]
    assert len(failed) == 0, f"指标计算失败: {failed}"
    return f"12/12 指标全部正常"


# ══════════════════════════════════════════════════════
# 六、新外部 API（DEX Screener / Owlracle）
# ══════════════════════════════════════════════════════

def test_dex_screener():
    """DEX Screener API — 查询 PEPE 交易对"""
    import httpx
    resp = httpx.get("https://api.dexscreener.com/latest/dex/search?q=PEPE", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    pairs = data.get("pairs", [])
    assert len(pairs) > 0, "应返回至少 1 个交易对"
    top = pairs[0]
    assert "baseToken" in top
    assert "volume" in top or "txns" in top
    name = top.get("baseToken", {}).get("name", "?")
    chain = top.get("chainId", "?")
    return f"找到 {len(pairs)} 个 pair, 第一个: {name} on {chain}"


def test_owlracle_gas():
    """Owlracle Gas API — 以太坊 Gas 费"""
    import httpx
    resp = httpx.get("https://api.owlracle.info/v4/eth/gas", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    assert "speeds" in data, f"应返回 speeds 字段, 实际: {list(data.keys())}"
    speeds = data["speeds"]
    assert len(speeds) > 0
    fast = speeds[-1]
    return f"ETH Gas: {fast.get('gasPrice', '?')} Gwei ({fast.get('estimatedFee', '?')} USD)"


# ══════════════════════════════════════════════════════
# 七、端到端场景
# ══════════════════════════════════════════════════════

def test_e2e_idea_to_signals():
    """端到端: 用户说想法 → 生成脚本逻辑 → 跑出信号"""
    from data_client import DataClient
    from indicators import Indicators
    import numpy as np

    # 模拟用户: "帮我做一个 ETH 的策略，RSI 低于 30 就买，高于 70 就卖"
    user_idea = {
        "symbol": "ETHUSDT",
        "buy_condition": "RSI < 30",
        "sell_condition": "RSI > 70",
        "timeframe": "4h",
    }

    # AI 根据想法生成脚本逻辑（这里直接用代码模拟）
    client = DataClient()
    df = client.get_perp_klines("ETH-USDT-PERP", "4h", "2024-06-01", "2024-12-31")
    client.close()

    close = df["close"].values
    rsi = Indicators.rsi(close, 14)

    signals = []
    for i in range(15, len(df)):
        if np.isnan(rsi[i]):
            continue
        row = df.iloc[i]
        if rsi[i] < 30:
            signals.append({
                "symbol": "ETHUSDT", "action": "buy",
                "confidence": round(1 - rsi[i] / 100, 2),
                "reason": f"RSI 超卖 ({rsi[i]:.0f})",
                "price_at_signal": float(row["close"]),
                "source_type": "technical",
                "timestamp": str(row["datetime"]),
            })
        elif rsi[i] > 70:
            signals.append({
                "symbol": "ETHUSDT", "action": "sell",
                "confidence": round(rsi[i] / 100, 2),
                "reason": f"RSI 超买 ({rsi[i]:.0f})",
                "price_at_signal": float(row["close"]),
                "source_type": "technical",
                "timestamp": str(row["datetime"]),
            })

    output = {
        "strategy_name": "ETH RSI 均值回归",
        "strategy_version": "v1.0",
        "generated_at": datetime.now().isoformat(),
        "mode": "backtest",
        "signals": signals,
    }

    assert len(signals) > 0, "应至少生成 1 个信号"
    buys = [s for s in signals if s["action"] == "buy"]
    sells = [s for s in signals if s["action"] == "sell"]

    return (f"用户想法 → {len(signals)} 个信号 (买 {len(buys)}, 卖 {len(sells)}), "
            f"ETH 2024H2, 4h 周期")


def test_e2e_dex_screener_strategy():
    """端到端: DEX Screener 驱动的策略"""
    import httpx

    # 模拟: "帮我找 DEX 上交易量暴增的币，24h 量 > 100 万且 1h 涨幅 > 3%"
    resp = httpx.get("https://api.dexscreener.com/latest/dex/search?q=PEPE", timeout=15)
    pairs = resp.json().get("pairs", [])

    signals = []
    for pair in pairs[:20]:
        vol_24h = float(pair.get("volume", {}).get("h24", 0))
        change_1h = float(pair.get("priceChange", {}).get("h1", 0))
        liquidity = float(pair.get("liquidity", {}).get("usd", 0))
        name = pair.get("baseToken", {}).get("symbol", "?")

        if vol_24h > 1_000_000 and change_1h > 3:
            signals.append({
                "symbol": name,
                "action": "buy",
                "confidence": min(change_1h / 10, 1.0),
                "reason": f"DEX 24h 量 ${vol_24h:,.0f}, 1h 涨 {change_1h}%",
                "source_type": "onchain",
                "metadata": {"volume_24h": vol_24h, "change_1h": change_1h, "liquidity": liquidity},
            })

    return f"扫描 {len(pairs[:20])} 个 pair, 找到 {len(signals)} 个符合条件的"


# ══════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("█" * 55)
    print("  策略制作 Skill — 完整能力测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█" * 55)

    # 一、技术指标模板
    test("1.1 技术指标模板 — 回测模式", test_technical_backtest)
    test("1.2 技术指标模板 — 实时模式", test_technical_live)
    test("1.3 技术指标模板 — 信号格式校验", test_technical_signal_format)

    # 二、混合策略模板
    test("2.1 混合策略模板 — 回测模式", test_mixed_backtest)
    test("2.2 混合策略模板 — 实时模式", test_mixed_live)

    # 三、社媒策略模板
    test("3.1 社媒策略 — 无 Key 降级", test_social_no_key)
    test("3.2 社媒策略 — 回测警告", test_social_backtest_warning)

    # 四、数据源
    test("4.1 Binance 永续 K 线", test_binance_perp_klines)
    test("4.2 Binance 资金费率", test_binance_funding)
    test("4.3 Binance 标记价格", test_binance_mark_price)
    test("4.4 Binance 现货 K 线", test_binance_spot)
    test("4.5 yfinance 美股", test_yfinance_stock)
    test("4.6 yfinance 黄金", test_yfinance_gold)
    test("4.7 DeFi Llama TVL", test_defillama)

    # 五、指标库
    test("5.1 12 个技术指标", test_all_indicators)

    # 六、新 API
    test("6.1 DEX Screener API", test_dex_screener)
    test("6.2 Owlracle Gas API", test_owlracle_gas)

    # 七、端到端
    test("7.1 端到端: 用户想法→信号", test_e2e_idea_to_signals)
    test("7.2 端到端: DEX Screener 策略", test_e2e_dex_screener_strategy)

    # 汇总
    print(f"\n{'═'*55}")
    print(f"  测试结果汇总")
    print(f"{'═'*55}")
    passed = sum(1 for r in RESULTS if "通过" in r["status"])
    failed = sum(1 for r in RESULTS if "失败" in r["status"])
    print(f"\n  总计: {len(RESULTS)} | 通过: {passed} | 失败: {failed}\n")
    for r in RESULTS:
        status = r["status"]
        print(f"  {status} [{r['time']:>6}] {r['name']}")
        if r["detail"]:
            print(f"         → {r['detail'][:80]}")
    print()
