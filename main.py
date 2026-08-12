#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钢铁雄心4 AI自动汉化助手 - 主入口
Hearts of Iron IV AI Localization Assistant

使用本地大语言模型翻译Paradox YML本地化文件，支持多语言。
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.gui import launch_gui


def main():
    """Main entry point."""
    # Check Python version
    if sys.version_info < (3, 8):
        print("错误: 需要 Python 3.8 或更高版本")
        print(f"当前版本: {sys.version}")
        sys.exit(1)
    
    # Launch GUI
    launch_gui()


if __name__ == "__main__":
    main()
