"""桥接到根 config，保持 reference 模块内部导入不变"""
import sys
from pathlib import Path

# 确保根目录在 sys.path 中（兼容 Streamlit Cloud 等部署环境）
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from config import *  # noqa: F401,F403
