#!/usr/bin/env python3
"""Post docs/wechat.md or daily_new.md to Feishu group bot via incoming webhook.

Used by GitHub Actions. The Feishu webhook URL should be provided via the
FEISHU_WEBHOOK_URL environment variable (recommended: store it in
GitHub Secrets as FEISHU_WEBHOOK_URL).
"""

import os
import sys

try:
    import requests
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests


def main() -> None:
    url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not url:
        print("FEISHU_WEBHOOK_URL not set, skip Feishu notification.")
        sys.exit(0)

    # 优先使用为微信/飞书定制的 wechat.md，不存在时退回 daily_new.md
    path = "docs/wechat.md"
    if not os.path.isfile(path):
        path = "daily_new.md"
    if not os.path.isfile(path):
        print("Neither docs/wechat.md nor daily_new.md exists, nothing to send.")
        sys.exit(0)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print("Content file is empty, skip Feishu notification.")
        sys.exit(0)

    # Feishu 文本消息体积限制较小，简单截断以避免失败
    max_len_bytes = 3800
    raw = content.encode("utf-8")
    if len(raw) > max_len_bytes:
        raw = raw[:max_len_bytes]
        content = raw.decode("utf-8", errors="ignore") + "\n\n（更多内容见仓库 docs/wechat.md）"

    # 使用 Feishu 的 markdown（lark_md）卡片形式，而不是纯文本：
    # https://open.feishu.cn/document/server-docs/im-v1/message-content/card-message#f6772f24
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content,
                    },
                }
            ],
        },
    }

    resp = requests.post(url, json=payload, timeout=15)
    print(resp.status_code, resp.text)
    if resp.status_code != 200:
        # Feishu webhooks 返回非 200 说明发送失败，显式退出 1 让 workflow 标红
        sys.exit(1)


if __name__ == "__main__":
    main()

