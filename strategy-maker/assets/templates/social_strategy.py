"""
社交媒体策略模板
监控推特/新闻等社交信号，结合价格数据生成交易信号。

使用方式:
  回测: 社媒策略无法回测历史（API 不支持），仅支持实时模式
  实时: python social_strategy.py live
  单次: python social_strategy.py live --once

依赖: pip install httpx loguru

注意: 需要自行配置社媒 API 的 Key（通过环境变量传入）
"""

import json
import sys
import os
import re
from datetime import datetime, timezone, timedelta

import httpx
from loguru import logger

# ═══════════════════════════════════════════════════
# 策略配置
# ═══════════════════════════════════════════════════

STRATEGY_NAME = "Crypto 推特情绪追踪"
STRATEGY_VERSION = "v1.0"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# ── 社媒 API 配置（从环境变量读取，不要硬编码） ──
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ── 监控的 KOL 列表 ──
WATCHED_ACCOUNTS = [
    "elonmusk",
    "VitalikButerin",
    "caborek",
    "CryptoCapo_",
]

# ── 关键词规则 ──
BULLISH_KEYWORDS = ["bullish", "买入", "moon", "breakout", "pump", "ath", "accumulate", "long"]
BEARISH_KEYWORDS = ["bearish", "卖出", "dump", "crash", "sell", "short", "top", "overvalued"]
SYMBOL_KEYWORDS = {
    "BTCUSDT": ["btc", "bitcoin", "$btc"],
    "ETHUSDT": ["eth", "ethereum", "$eth"],
    "SOLUSDT": ["sol", "solana", "$sol"],
}


# ═══════════════════════════════════════════════════
# 社媒数据获取
# ═══════════════════════════════════════════════════

def fetch_twitter_mentions(symbol_keywords: list[str], minutes_back: int = 60) -> list[dict]:
    """
    获取最近 N 分钟内提到指定关键词的推文。
    需要 Twitter API v2 Bearer Token。
    """
    if not TWITTER_BEARER_TOKEN:
        logger.warning("TWITTER_BEARER_TOKEN 未设置，跳过推特数据")
        return []

    query = " OR ".join(symbol_keywords) + " -is:retweet lang:en"
    start_time = (datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = httpx.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"},
            params={
                "query": query,
                "start_time": start_time,
                "max_results": 100,
                "tweet.fields": "author_id,created_at,public_metrics",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"推特 API 调用失败: {e}")
        return []


def fetch_crypto_news(keywords: list[str], hours_back: int = 6) -> list[dict]:
    """
    获取最近 N 小时的加密货币新闻。
    可以对接 CryptoPanic、NewsAPI 等。
    """
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY 未设置，跳过新闻数据")
        return []

    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": " OR ".join(keywords),
                "from": (datetime.now(tz=timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S"),
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": NEWS_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("articles", [])
    except Exception as e:
        logger.error(f"新闻 API 调用失败: {e}")
        return []


# ═══════════════════════════════════════════════════
# 情绪分析
# ═══════════════════════════════════════════════════

def analyze_sentiment(texts: list[str]) -> dict:
    """
    简单关键词情绪分析。
    生产环境建议用 LLM 或专用情绪分析 API 替换。
    """
    bullish_count = 0
    bearish_count = 0
    total = len(texts)

    for text in texts:
        lower = text.lower()
        if any(kw in lower for kw in BULLISH_KEYWORDS):
            bullish_count += 1
        if any(kw in lower for kw in BEARISH_KEYWORDS):
            bearish_count += 1

    if total == 0:
        return {"sentiment": "neutral", "score": 0.5, "bullish": 0, "bearish": 0, "total": 0}

    score = (bullish_count - bearish_count) / total * 0.5 + 0.5  # 归一化到 0~1
    score = max(0, min(1, score))

    if score > 0.65:
        sentiment = "bullish"
    elif score < 0.35:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "score": round(score, 3),
        "bullish": bullish_count,
        "bearish": bearish_count,
        "total": total,
    }


def check_kol_mentions(tweets: list[dict]) -> list[dict]:
    """检查 KOL 是否发了相关推文。"""
    kol_alerts = []
    for tweet in tweets:
        author = tweet.get("author_id", "")
        if author in WATCHED_ACCOUNTS:
            kol_alerts.append({
                "author": author,
                "text": tweet.get("text", ""),
                "created_at": tweet.get("created_at", ""),
            })
    return kol_alerts


# ═══════════════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    """
    策略主函数。
    社媒策略不支持 backtest 模式（历史社媒数据不可用）。
    """
    if mode == "backtest":
        logger.warning("社媒策略不支持回测模式（无历史社媒数据），仅返回空信号")
        return {
            "strategy_name": STRATEGY_NAME,
            "strategy_version": STRATEGY_VERSION,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "mode": mode,
            "signals": [],
            "warning": "社媒策略不支持回测，历史社媒数据无法获取",
        }

    signals = []

    for symbol in SYMBOLS:
        keywords = SYMBOL_KEYWORDS.get(symbol, [])
        if not keywords:
            continue

        # 获取推特数据
        tweets = fetch_twitter_mentions(keywords, minutes_back=60)
        tweet_texts = [t.get("text", "") for t in tweets]

        # 获取新闻数据
        news = fetch_crypto_news(keywords, hours_back=6)
        news_texts = [n.get("title", "") + " " + n.get("description", "") for n in news]

        # 合并分析
        all_texts = tweet_texts + news_texts
        sentiment = analyze_sentiment(all_texts)

        # KOL 提及检查
        kol_alerts = check_kol_mentions(tweets)

        # ── 生成信号 ──
        if sentiment["sentiment"] == "bullish" and sentiment["score"] > 0.7:
            signals.append({
                "symbol": symbol,
                "action": "buy",
                "confidence": sentiment["score"],
                "reason": f"社媒情绪强烈看多 (得分 {sentiment['score']:.2f}, "
                         f"{sentiment['bullish']}/{sentiment['total']} 条看多)",
                "source_type": "social",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "metadata": {
                    "sentiment": sentiment,
                    "kol_alerts": kol_alerts[:3],
                    "tweet_count": len(tweet_texts),
                    "news_count": len(news_texts),
                }
            })
        elif sentiment["sentiment"] == "bearish" and sentiment["score"] < 0.3:
            signals.append({
                "symbol": symbol,
                "action": "sell",
                "confidence": 1 - sentiment["score"],
                "reason": f"社媒情绪强烈看空 (得分 {sentiment['score']:.2f}, "
                         f"{sentiment['bearish']}/{sentiment['total']} 条看空)",
                "source_type": "social",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "metadata": {
                    "sentiment": sentiment,
                    "kol_alerts": kol_alerts[:3],
                    "tweet_count": len(tweet_texts),
                    "news_count": len(news_texts),
                }
            })

    return {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "signals": signals,
    }


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    result = generate_signals(mode=mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
