import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

from modules.reference.main import process_paper

def log_cb(msg):
    print(msg, flush=True)

refs, md, plain = process_paper(
    r"D:\论文\正念训练对护理人员隐性缺勤影响机制研究(1).docx",
    year_start=2020,
    year_end=2026,
    cn_ratio=0.25,
    paper_title="正念训练对护理人员隐性缺勤影响机制研究",
    callback=log_cb,
    fast_mode=True,
    max_markers=20,
)

print("\n" + "=" * 70)
print("参考文献列表：")
print(plain)
