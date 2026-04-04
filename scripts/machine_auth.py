"""
机器认证 & Token 管理

认证方式:
  使用本地生成的随机 UUID 作为设备标识（不采集硬件信息）。
  UUID 和 Token 保存在 skill 目录下的 .auth.json 文件中。

流程:
  1. 首次使用 → 生成随机 UUID → 向服务器注册 → 获取 Token
  2. 后续使用 → 直接读本地缓存的 Token

不采集: 主机名、操作系统、MAC 地址、IP 等任何硬件/网络信息。
"""

from __future__ import annotations

import json
import uuid as uuid_lib
from pathlib import Path

import httpx
from loguru import logger

API_PREFIX = "/api/v1"

# auth 文件存在 skill 目录下 (scripts/../.auth.json)
_AUTH_FILE = Path(__file__).parent.parent / ".auth.json"


def _generate_device_id() -> str:
    """生成随机 UUID 作为设备标识，不采集任何硬件信息。"""
    return uuid_lib.uuid4().hex[:32]


class MachineAuth:
    """设备认证客户端"""

    def __init__(self, server_url: str = "https://dex-quant-app-production.up.railway.app"):
        self.server_url = server_url.rstrip("/")
        self.base_url = self.server_url + API_PREFIX
        self._client = httpx.Client(timeout=30.0)
        self._config: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        if _AUTH_FILE.exists():
            try:
                self._config = json.loads(_AUTH_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._config = {}

    def _save_config(self) -> None:
        _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AUTH_FILE.write_text(json.dumps(self._config, indent=2, ensure_ascii=False))

    @property
    def machine_code(self) -> str:
        code = self._config.get("device_id", "")
        if not code:
            code = _generate_device_id()
            self._config["device_id"] = code
            self._save_config()
        return code

    @property
    def token(self) -> str:
        return self._config.get("token", "")

    def register_or_load(self) -> str:
        """获取 Token（自动注册或读本地缓存）。"""
        if self.token:
            return self.token

        device_id = self.machine_code
        logger.info(f"首次使用，注册设备: {device_id[:8]}...")

        resp = self._client.post(
            f"{self.base_url}/auth/register",
            json={"machine_code": device_id},
        )
        resp.raise_for_status()
        data = resp.json()

        self._config["device_id"] = device_id
        self._config["token"] = data["token"]
        self._config["max_strategies"] = data["max_strategies"]
        self._save_config()

        logger.info(f"注册成功 | 配额 {data['used_strategies']}/{data['max_strategies']}")
        return data["token"]

    def check_quota(self) -> dict:
        """查询当前配额使用情况。"""
        token = self.register_or_load()
        resp = self._client.get(
            f"{self.base_url}/auth/quota",
            headers={"X-Token": token},
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
