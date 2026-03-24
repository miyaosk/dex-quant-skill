"""
机器码认证 & Token 管理

流程:
  1. get_machine_code() — 根据硬件指纹生成唯一机器码
  2. register_or_load() — 首次使用自动注册，后续复用本地缓存的 Token
  3. check_quota()     — 查询剩余策略配额

Token 存储位置: ~/.dex-quant/config.json

用法:
    from machine_auth import MachineAuth

    auth = MachineAuth("https://generous-hope-production-6cf6.up.railway.app")
    token = auth.register_or_load()   # 自动注册或读缓存
    quota = auth.check_quota()        # 查配额
    print(f"剩余 {quota['remaining']} 个策略位")
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid as uuid_lib
from pathlib import Path

import httpx
from loguru import logger

CONFIG_DIR = Path.home() / ".dex-quant"
CONFIG_FILE = CONFIG_DIR / "config.json"
API_PREFIX = "/api/v1"


def get_machine_code() -> str:
    """
    生成硬件指纹哈希（确定性，同一台机器始终相同）。

    组合因子: 主机名 + 操作系统 + 网卡 MAC 地址
    """
    raw = f"{platform.node()}-{platform.system()}-{platform.machine()}-{uuid_lib.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class MachineAuth:
    """机器码认证客户端"""

    def __init__(self, server_url: str = "https://generous-hope-production-6cf6.up.railway.app"):
        self.server_url = server_url.rstrip("/")
        self.base_url = self.server_url + API_PREFIX
        self._client = httpx.Client(timeout=30.0)
        self._config: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                self._config = json.loads(CONFIG_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._config = {}

    def _save_config(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._config, indent=2, ensure_ascii=False))

    @property
    def machine_code(self) -> str:
        return get_machine_code()

    @property
    def token(self) -> str:
        return self._config.get("token", "")

    def register_or_load(self) -> str:
        """
        获取 Token（自动注册或读本地缓存）。

        返回: Token 字符串
        """
        if self.token:
            logger.info(f"使用已缓存 Token: {self.token[:12]}...")
            return self.token

        mc = self.machine_code
        logger.info(f"机器码: {mc[:8]}... | 向 Server 注册")

        resp = self._client.post(
            f"{self.base_url}/auth/register",
            json={"machine_code": mc},
        )
        resp.raise_for_status()
        data = resp.json()

        self._config["machine_code"] = mc
        self._config["token"] = data["token"]
        self._config["server_url"] = self.server_url
        self._config["max_strategies"] = data["max_strategies"]
        self._save_config()

        logger.info(
            "注册成功 | Token={} | 配额 {}/{}",
            data["token"][:12] + "...",
            data["used_strategies"],
            data["max_strategies"],
        )
        return data["token"]

    def check_quota(self) -> dict:
        """
        查询当前配额使用情况。

        返回: {"machine_code", "max_strategies", "used_strategies", "remaining", "strategies"}
        """
        token = self.register_or_load()
        resp = self._client.get(
            f"{self.base_url}/auth/quota",
            headers={"X-Token": token},
        )
        resp.raise_for_status()
        return resp.json()

    def print_quota(self) -> None:
        """格式化打印配额信息"""
        q = self.check_quota()
        print("\n" + "=" * 45)
        print("  策略配额")
        print("=" * 45)
        print(f"  机器码:     {q['machine_code'][:8]}...")
        print(f"  已用/上限:  {q['used_strategies']}/{q['max_strategies']}")
        print(f"  剩余:       {q['remaining']}")
        if q.get("strategies"):
            print("-" * 45)
            for s in q["strategies"]:
                print(f"  - {s['name']} ({s['strategy_id']}) [{s['status']}]")
        print("=" * 45)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    import sys
    server = sys.argv[1] if len(sys.argv) > 1 else "https://generous-hope-production-6cf6.up.railway.app"
    auth = MachineAuth(server)
    auth.register_or_load()
    auth.print_quota()
    auth.close()
