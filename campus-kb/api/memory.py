"""对话记忆持久化：按 sessionId 把 user/assistant 轮次落盘。

前端刷新后仍能接着聊，后端在 Agent 请求时自动加载、回答后自动追加，
避免每次都把完整历史塞在请求体里来回传。

- 存储位置：CAMPUS_SESSION_DIR，默认 <KB>/data/sessions（Docker 里挂卷持久化）
- 安全：sessionId 只允许 [A-Za-z0-9_-]{1,64}，杜绝路径穿越
- 限长：最多 MAX_TURNS 轮，超出丢弃最早的轮次，控制 token 与磁盘占用
- 只存问答文本，不存工具轨迹与草稿状态；前端 UI 状态由浏览器自行恢复
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KB = Path(__file__).resolve().parent.parent
MAX_TURNS = 12
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def session_dir() -> Path:
    override = os.environ.get("CAMPUS_SESSION_DIR")
    return Path(override) if override else KB / "data" / "sessions"


def _path(session_id: str) -> Path:
    if not _SESSION_ID.fullmatch(session_id or ""):
        raise ValueError("sessionId 只能包含字母、数字、下划线和连字符（1-64 位）")
    return session_dir() / f"{session_id}.json"


def load(session_id: str) -> list[dict[str, str]]:
    """读取会话历史；文件损坏或非法 id 时返回空，不阻断问答。"""
    try:
        raw = json.loads(_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    turns = raw.get("turns", []) if isinstance(raw, dict) else []
    return [
        {"role": t["role"], "content": t["content"]}
        for t in turns
        if isinstance(t, dict)
        and t.get("role") in ("user", "assistant")
        and isinstance(t.get("content"), str)
    ][-MAX_TURNS * 2:]


def append(session_id: str, question: str, answer: str) -> None:
    """追加一轮问答；写入用临时文件 + 原子替换，避免并发写坏文件。"""
    if not answer.strip():
        return
    turns = load(session_id) + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    turns = turns[-MAX_TURNS * 2:]
    target = _path(session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "turns": turns,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()


def clear(session_id: str) -> None:
    """清空会话；非法 id 直接忽略，不让清理操作把接口打挂。"""
    try:
        _path(session_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        return
