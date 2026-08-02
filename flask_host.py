# -*- coding: utf-8 -*-
"""Flask 后台服务托管：以子进程方式运行 app.py。
支持 start() / stop() / 强制清理，退出时主动终止全部关联子进程，
杜绝任务管理器残留僵尸进程。
"""
import os
import sys
import atexit
import subprocess
import threading

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

from paths import EXE_DIR, FROZEN

BASE = EXE_DIR
FLASK_PORT = 8088
FLASK_HOST = "127.0.0.1"


class FlaskHost:
    def __init__(self):
        self.proc = None
        self.running = False
        self._lock = threading.Lock()
        self._atexit_registered = False
        # 关键：无论程序在何处退出（正常退出、未捕获异常、raise 崩溃），
        # 都通过 atexit 钩子回收 Flask 子进程，避免残留僵尸进程堆积。
        self._register_atexit()

    def _register_atexit(self):
        if self._atexit_registered:
            return
        try:
            atexit.register(self.cleanup)
            self._atexit_registered = True
        except Exception:
            pass

    def start(self):
        """启动 Flask 子进程。已运行时直接返回。"""
        with self._lock:
            if self.running and self.proc and self.proc.poll() is None:
                return True
            if self.proc and self.proc.poll() is None:
                return True
        try:
            # 使用与当前客户端相同的 python 解释器（exe 模式下即自身）
            python = sys.executable
            creationflags = 0
            if os.name == "nt":
                # 不显示子进程黑窗口
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            # frozen 模式下没有独立的 app.py 源文件，由 exe 自带 --flask-worker
            # 参数自举运行 app.run()；开发模式下仍直接运行 app.py。
            if FROZEN:
                args = [python, "--flask-worker"]
            else:
                args = [python, os.path.join(BASE, "app.py")]
            self.proc = subprocess.Popen(
                args,
                cwd=BASE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            with self._lock:
                self.running = True
            return True
        except Exception:
            with self._lock:
                self.running = False
            return False

    def stop(self):
        """停止 Flask 子进程，并清理其子孙进程。

        非阻塞：向进程树发出 kill 后立刻返回，不会卡住调用方
        （GUI 主线程）；真正的进程回收在后台守护线程中 wait，
        避免残留僵尸进程，同时不阻塞 UI 事件循环。
        """
        with self._lock:
            proc, self.proc = self.proc, None
            self.running = False
        if proc is None:
            return
        self._kill_tree(proc.pid)
        # 后台线程回收已终止进程，不阻塞调用方

        def _reap():
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        threading.Thread(target=_reap, daemon=True).start()

    def _kill_tree(self, pid):
        """终止进程及其整个子树（windows 用 taskkill /F /T；跨平台用 psutil）。"""
        if _HAS_PSUTIL:
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except Exception:
                        pass
                try:
                    parent.kill()
                except Exception:
                    pass
                return
            except Exception:
                pass
        # 回退：Windows taskkill
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                )
            except Exception:
                pass

    def cleanup(self):
        """程序退出时调用，确保彻底清理。

        通过 atexit 钩子注册，即使程序在任意位置异常退出也能触发；
        重复调用安全（stop 内部对已为 None 的进程直接返回）。
        """
        self.stop()

    def is_alive(self):
        if self.proc is None:
            return False
        return self.proc.poll() is None
