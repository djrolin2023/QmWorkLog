# -*- coding: utf-8 -*-
"""路径解析公共模块：统一处理 开发模式 / PyInstaller 单文件冻结模式 下的目录。

- EXE_DIR：可执行文件（或脚本）所在目录。用户数据（Data/DB/Backup/users.json/
  config.json）一律放这里，确保发布后数据与程序并列、可持久化。
- RES_DIR：静态资源（static/templates/version.json 等打包进 exe 的文件）所在目录。
  冻结模式下由 PyInstaller 释放到 sys._MEIPASS；开发模式下等同 EXE_DIR。
"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    # PyInstaller 单文件会把 --add-data 的资源释放到临时目录 _MEIPASS
    RES_DIR = getattr(sys, "_MEIPASS", EXE_DIR)
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = EXE_DIR
