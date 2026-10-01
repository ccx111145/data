# -*- coding: utf-8 -*-
"""clean_c_temp.py —— 清理 C 盘可安全释放的临时文件。

原则（这批文件都是"快照/构建缓存"，误删代价不同，所以分级处理）：
  1. dsh-workspace-changes-* 早于今天的快照 —— 会话已结束的残留，删除
  2. 本次会话的两个最新快照 —— **保留**（GUI 可能仍引用，删了会影响撤销）
  3. VS Build 临时目录 qhn21pkp —— 10 天前的残留，删除
  4. uv / pip 缓存 —— 删除（下次跑会自动重建）

硬性护栏：
  * 只允许删除 $env:TEMP 下**白名单前缀**的目录，或明确的缓存根目录
  * 每个目标删除前打印路径与体积；删除后复核是否存在
  * **绝不**触碰桌面交付物、.dsh\\attachments、pandoc-dsh

用法：python code/clean_c_temp.py --dry-run   # 先看会删什么
      python code/clean_c_temp.py            # 实际执行
"""
from __future__ import annotations

import os
import shutil
import sys
import time

TEMP = os.environ.get("TEMP", r"C:\Users\ASUS\AppData\Local\Temp")
LOCAL = os.environ.get("LOCALAPPDATA", r"C:\Users\ASUS\AppData\Local")

# 保护名单：任何情况下都不删
PROTECT = [
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), ".dsh", "attachments"),
    os.path.join(LOCAL, "pandoc-dsh"),
]

SNAPSHOT_PREFIX = "dsh-workspace-changes-"
# 本次会话保留的快照（按目录名）
KEEP_SNAPSHOTS = {"dsh-workspace-changes-Dd99Tt", "dsh-workspace-changes-Xl0l7U"}


def size_of(p: str) -> int:
    t = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return t


def guarded(p: str) -> bool:
    """目标是否在允许范围内、且不在保护名单里。"""
    rp = os.path.realpath(p)
    for g in PROTECT:
        if rp.lower().startswith(os.path.realpath(g).lower()):
            return False
    allowed = (os.path.join(TEMP, SNAPSHOT_PREFIX),
               os.path.join(TEMP, "qhn21pkp"),
               os.path.join(LOCAL, "uv", "cache"),
               os.path.join(LOCAL, "pip", "Cache"))
    return any(rp.lower().startswith(os.path.realpath(a).lower()) for a in allowed)


def main() -> int:
    dry = "--dry-run" in sys.argv
    targets: list[str] = []

    # 1) 过期快照
    if os.path.isdir(TEMP):
        for n in os.listdir(TEMP):
            if not n.startswith(SNAPSHOT_PREFIX):
                continue
            if n in KEEP_SNAPSHOTS:
                continue
            targets.append(os.path.join(TEMP, n))
    # 2) VS 构建残留
    vs = os.path.join(TEMP, "qhn21pkp")
    if os.path.isdir(vs):
        targets.append(vs)
    # 3) 包管理器缓存
    for c in (os.path.join(LOCAL, "uv", "cache"), os.path.join(LOCAL, "pip", "Cache")):
        if os.path.isdir(c):
            targets.append(c)

    total = 0
    print("%s 共 %d 个目标" % ("[DRY-RUN]" if dry else "[执行]", len(targets)))
    print()
    kept = [n for n in SNAPSHOT_PREFIX and os.listdir(TEMP)
            if n.startswith(SNAPSHOT_PREFIX) and n in KEEP_SNAPSHOTS]
    for n in kept:
        print("  [保留] %-34s %s" % (n, "本次会话快照"))
    print()

    for p in sorted(targets):
        if not os.path.isdir(p):
            continue
        if not guarded(p):
            print("  [跳过] %s —— 不在允许范围内" % p)
            continue
        s = size_of(p)
        if dry:
            print("  将删 %-42s %8.0f MB" % (os.path.basename(p), s / 1e6))
            total += s
            continue
        # 用 cmd 的 rmdir 而不是 shutil.rmtree：
        # 快照文件名是 40 位十六进制哈希，深路径下 shutil.rmtree 会大面积
        # WinError 5 拒绝访问，而 rmdir /s /q 能正常删（实测）。
        try:
            import subprocess
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", p],
                           capture_output=True, timeout=900)
        except Exception as e:                                       # noqa: BLE001
            print("  [失败] %-42s %s" % (os.path.basename(p), str(e)[:60]))
            continue
        ok = not os.path.exists(p)
        print("  %s %-42s %8.0f MB" % ("[已删]" if ok else "[残留]", os.path.basename(p), s / 1e6))
        if ok:
            total += s
        else:
            # 退一步：rmdir 失败时用 shutil 再试一次
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:                                        # noqa: BLE001
                pass

    print()
    print("%s 可释放/已释放 %.1f GB" % ("预计" if dry else "实际", total / 1e9))
    return 0


if __name__ == "__main__":
    sys.exit(main())
