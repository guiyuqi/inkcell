# -*- coding: utf-8 -*-
"""inkcell app —— 打包手机离线 APK（转发到包内的 build_apk.sh）。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print("用法：inkcell app [--project DIR] [TAG=xx PASS=n ALL=1 ...]\n"
              "环境变量直接透传给 build_apk.sh：TAG / PASS / ALL / APP_ID / OUT\n"
              f"脚本位置：{HERE / 'build_apk.sh'}")
        return 0
    env = dict(os.environ)
    # --project 透传给页面生成
    if "--project" in argv:
        i = argv.index("--project")
        env["PROJECT"] = argv[i + 1]
        del argv[i:i + 2]
    env.setdefault("INKCELL_BIN", "inkcell")
    r = subprocess.run(["bash", str(HERE / "build_apk.sh"), *argv], env=env)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
