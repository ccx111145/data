# -*- coding: utf-8 -*-
"""clean_attachments.py —— 清理 DSH 附件缓存。

这是什么：C:\\Users\\ASUS\\.dsh\\attachments\\v1\\objects\\<2位>\\<sha256>
是**内容寻址缓存**（按 sha256 分桶），存的是会话里出现过的图片 / PDF / Office 文件
的规范化副本。它是缓存，不是唯一副本：原始文件仍在原位置（桌面、仓库等）。

护栏：
  * 只允许操作 attachments/v1/objects 下的内容
  * 保护桌面四套交付、pandoc-dsh、--out 指定的保留目录
  * 先 --dry-run 打印将删数量与体积

用法：python code/clean_attachments.py --dry-run
      python code/clean_attachments.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HOME = os.path.expanduser("~")
# attachments/v1 下是四套内容寻址缓存。上一版只清了 objects（157 MB），
# 实际还有 files / file-objects / request-images，合计 373 MB。
# v1\tmp 是运行时临时目录，**不清**（可能正被占用）。
V1 = os.path.join(HOME, ".dsh", "attachments", "v1")
CACHE_DIRS = ["objects", "files", "file-objects", "request-images"]
ROOT = V1  # guarded() 的边界就是 v1，但删除时只遍历 CACHE_DIRS

PROTECT = [
    os.path.join(HOME, "Desktop"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "pandoc-dsh"),
]


def size_of(p: str) -> int:
    t = 0
    for root, _d, files in os.walk(p):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return t


def guarded(p: str) -> bool:
    rp = os.path.realpath(p)
    for g in PROTECT:
        if g and rp.lower().startswith(os.path.realpath(g).lower()):
            return False
    if not rp.lower().startswith(os.path.realpath(V1).lower()):
        return False
    # v1\tmp 是运行时临时，永不清
    return os.path.basename(rp) != "tmp"


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not os.path.isdir(ROOT):
        print("附件缓存目录不存在：%s" % ROOT)
        return 0

    targets = [os.path.join(V1, d) for d in CACHE_DIRS]
    targets = [d for d in targets if os.path.isdir(d)]

    n_files = 0
    total = 0
    for root, _d, files in os.walk(V1):
        if os.path.basename(root) == "tmp" or os.sep + "tmp" + os.sep in root:
            continue
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                n_files += 1
            except OSError:
                pass
    print("将清这些缓存：%s" % ", ".join(os.path.basename(d) for d in targets))

    print("缓存根：%s" % ROOT)
    print("将清 %d 个文件 / %.1f MB" % (n_files, total / 1e6))
    print()
    if dry:
        print("[DRY-RUN] 未执行任何删除。去掉 --dry-run 即实际清理。")
        return 0

    if not all(guarded(d) for d in targets) or not targets:
        print("[中止] 目标不在允许范围内")
        return 1

    # 与 clean_c_temp 同样的理由：哈希文件名 + 深路径会让 shutil.rmtree 大面积
    # WinError 5；cmd 的 rmdir 实测可靠。
    freed = 0
    for d in targets:
        for bucket in sorted(os.listdir(d)):
            bp = os.path.join(d, bucket)
            if not os.path.isdir(bp):
                continue
            s = size_of(bp)
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", bp],
                           capture_output=True, timeout=600)
            if not os.path.exists(bp):
                freed += s
    # 复核（排除 tmp）
    left = 0
    for r, _d, fs in os.walk(V1):
        if os.path.basename(r) == "tmp" or os.sep + "tmp" + os.sep in r:
            continue
        left += len(fs)
    print()
    print("已释放 %.1f MB" % (freed / 1e6))
    print("剩余文件 %d 个" % left)
    return 0


if __name__ == "__main__":
    sys.exit(main())
