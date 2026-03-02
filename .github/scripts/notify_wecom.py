#!/usr/bin/env python3
"""Post docs/wechat.md or daily_new.md to WeCom group robot. Used by GitHub Actions."""
import os
import sys

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

url = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
if not url:
    print("WECOM_WEBHOOK_URL not set, skip.")
    sys.exit(0)

path = "docs/wechat.md"
if not os.path.isfile(path):
    path = "daily_new.md"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

max_len = 3800
if len(content.encode("utf-8")) > max_len:
    content = content.encode("utf-8")[:max_len].decode("utf-8", errors="ignore")
    content += "\n\n（更多见仓库 docs/wechat.md）"

payload = {"msgtype": "markdown", "markdown": {"content": content}}
r = requests.post(url, json=payload, timeout=15)
print(r.status_code, r.text)
if r.json().get("errcode") != 0:
    sys.exit(1)
