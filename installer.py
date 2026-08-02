# -*- coding: utf-8 -*-
"""乾明工作台账系统 — 安装向导。

内置向导流程：
  1) 许可协议页：展示 MIT 风格中文开源协议，必须勾选“已阅读并同意”方可继续；
  2) 安装路径页：默认 D:\\QmWorkLog，可浏览更改；
  3) 安装进度页：把打包进本安装程序的主程序 exe 释放到目标目录，并创建快捷方式；
  4) 完成页：提示安装结束，可选择“启动程序”。

主程序 exe 由 PyInstaller 以 add-binary 形式嵌入本安装程序，运行时位于
sys._MEIPASS\\QmWorkLog.exe，安装时复制到用户选择的目标目录。
"""
import os
import sys
import shutil
import subprocess

from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QTextEdit, QCheckBox,
    QLabel, QLineEdit, QPushButton, QFileDialog, QProgressBar, QMessageBox,
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication

import install_utils as iu

APP_NAME = iu.APP_NAME
DEFAULT_DIR = iu.default_install_dir()
MAIN_EXE_NAME = iu._main_bin_name()
LICENSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LICENSE_INSTALL.txt")


def _resource(name):
    """在冻结/脚本模式下定位资源文件。"""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", ""), name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


# ---------------------------------------------------------------------------
# 第 1 页：许可协议
# ---------------------------------------------------------------------------
class LicensePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("许可协议")
        self.setSubTitle("请阅读以下软件许可协议，勾选“我已阅读并接受”后方可继续。")
        layout = QVBoxLayout(self)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Microsoft YaHei", 10))
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                self.text.setPlainText(f.read())
        except Exception as e:
            self.text.setPlainText("无法加载协议文本：%s" % e)
        layout.addWidget(self.text)

        self.agree = QCheckBox("我已阅读并接受上述许可协议")
        self.agree.stateChanged.connect(self._on_agree)
        layout.addWidget(self.agree)

    def _on_agree(self, state):
        self.completeChanged.emit()

    def isComplete(self):
        return self.agree.isChecked()


# ---------------------------------------------------------------------------
# 第 2 页：安装路径
# ---------------------------------------------------------------------------
class PathPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("选择安装位置")
        self.setSubTitle("程序将安装到以下目录（用户数据也会保存在该目录下）。")
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.edit = QLineEdit(DEFAULT_DIR)
        self.registerField("targetDir*", self.edit)
        btn = QPushButton("浏览...")
        btn.clicked.connect(self._browse)
        row.addWidget(self.edit)
        row.addWidget(btn)
        layout.addLayout(row)

        hint = QLabel("默认路径：%s\n程序文件、数据库与台账文档均保存在此目录，" % DEFAULT_DIR
                      + "卸载时直接删除该目录即可。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择安装目录", self.edit.text())
        if d:
            self.edit.setText(d)

    def validatePage(self):
        path = self.edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请填写安装路径。")
            return False
        # 若目录非空且已存在主程序，提示会覆盖
        if os.path.isdir(path) and os.listdir(path):
            reply = QMessageBox.question(
                self, "目录非空",
                "目标目录已存在且非空，继续安装会向其中写入/覆盖文件。是否继续？",
                QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
            if reply != QMessageBox.Ok:
                return False
        return True


# ---------------------------------------------------------------------------
# 第 3 页：安装进度（后台线程复制）
# ---------------------------------------------------------------------------
class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, target_dir):
        super().__init__()
        self.target_dir = target_dir

    def _find_main_exe(self):
        """在多种可能位置查找内嵌主程序，返回首个存在的绝对路径。"""
        candidates = [
            _resource(MAIN_EXE_NAME),
            os.path.join(getattr(sys, "_MEIPASS", ""), MAIN_EXE_NAME),
            os.path.join(os.path.dirname(os.path.abspath(sys.executable)), MAIN_EXE_NAME),
            os.path.join(os.getcwd(), MAIN_EXE_NAME),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def _safe_makedirs(self, path):
        """创建目录；若盘符不可写，回退到用户主目录（最终兜底）。"""
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            fallback = os.path.join(os.path.expanduser("~"), "QmWorkLog")
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def run(self):
        try:
            target = self._safe_makedirs(self.target_dir)

            # 主程序 exe（由 PyInstaller add-binary 嵌入）
            src_exe = self._find_main_exe()
            if not src_exe:
                self.finished.emit(
                    False,
                    "未找到主程序文件（%s）。请确认安装包完整，或重新下载安装程序。" % MAIN_EXE_NAME)
                return
            self.progress.emit(20, "正在复制主程序...")
            dst_exe = os.path.join(target, MAIN_EXE_NAME)
            shutil.copyfile(src_exe, dst_exe)
            os.chmod(dst_exe, 0o755)

            self.progress.emit(60, "正在创建快捷方式...")
            self._create_shortcuts(dst_exe, target)

            self.progress.emit(100, "安装完成，目标目录：%s" % target)
            self.finished.emit(True, target)
        except Exception as e:
            self.finished.emit(False, "安装失败：%s" % e)

    def _create_shortcuts(self, exe_path, work_dir):
        """按平台创建快捷方式/启动入口（Windows .lnk / macOS .app / Linux .desktop）。"""
        icon_path = _resource("static\\Images\\logo.ico")
        try:
            iu.create_shortcuts(exe_path, work_dir, icon_path, APP_NAME)
        except Exception:
            pass


class InstallPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("正在安装")
        self.setSubTitle("请稍候，正在将程序安装到所选目录...")
        layout = QVBoxLayout(self)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.worker = None
        self._done = False      # 安装成功
        self._failed = False    # 安装失败（也允许离开页面）

    def initializePage(self):
        target = self.field("targetDir")
        self.bar.setValue(0)
        self._done = False
        self._failed = False
        self.status.setText("正在准备安装...\n目标目录：%s" % target)
        # 安装进行中禁用“下一步/完成”，防止中途离开
        btn = self.wizard().button(QWizard.NextButton)
        if btn:
            btn.setEnabled(False)
        self.worker = InstallWorker(target)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, val, msg):
        self.bar.setValue(val)
        self.status.setText(msg)

    def _on_finished(self, ok, msg):
        self._done = ok
        self._failed = not ok
        self.status.setText(msg)
        self.bar.setValue(100 if ok else self.bar.value())
        # 安装结束（成功或失败）后恢复“下一步”按钮
        btn = self.wizard().button(QWizard.NextButton)
        if btn:
            btn.setEnabled(True)
        self.completeChanged.emit()
        if not ok:
            # 安装失败：提示用户并关闭向导（不进入完成页）
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: (
                QMessageBox.critical(self, "安装失败", msg),
                self.wizard().reject(),
            ))

    def isComplete(self):
        # 安装成功可进入完成页；安装失败也允许“完成”退出向导
        return self._done or self._failed

    def validatePage(self):
        if self._failed:
            # 安装失败时，若用户点“完成”，给出提示后允许退出（不进入完成页）
            return True
        return self._done


# ---------------------------------------------------------------------------
# 第 4 页：完成
# ---------------------------------------------------------------------------
class FinishPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("安装完成")
        layout = QVBoxLayout(self)
        self.label = QLabel("乾明工作台账系统已成功安装。\n点击“完成”后您可以选择立即启动程序。")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.launch = QCheckBox("立即启动程序")
        self.launch.setChecked(True)
        layout.addWidget(self.launch)

    def initializePage(self):
        target = self.field("targetDir")
        exe = os.path.join(target, MAIN_EXE_NAME)
        self._exe = exe

    def validatePage(self):
        if self.launch.isChecked() and getattr(self, "_exe", ""):
            try:
                subprocess.Popen([self._exe])
            except Exception as e:
                QMessageBox.warning(self, "启动失败", str(e))
        return True


# ---------------------------------------------------------------------------
# 向导主体
# ---------------------------------------------------------------------------
class InstallWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("%s 安装向导" % APP_NAME)
        self.setWizardStyle(QWizard.ModernStyle)
        # 屏蔽整个安装向导的右键菜单
        self.setContextMenuPolicy(Qt.NoContextMenu)
        icon_path = _resource("static\\Images\\logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(640, 480)
        self.setOption(QWizard.NoCancelButton, False)

        self.addPage(LicensePage())
        self.addPage(PathPage())
        self.addPage(InstallPage())
        self.addPage(FinishPage())

        # 统一按钮中文
        self.setButtonText(QWizard.NextButton, "下一步")
        self.setButtonText(QWizard.BackButton, "上一步")
        self.setButtonText(QWizard.CancelButton, "取消")
        self.setButtonText(QWizard.FinishButton, "完成")
        self.setButtonText(QWizard.CommitButton, "开始安装")

        # 所有页面统一屏蔽右键菜单
        for pid in self.pageIds():
            self.page(pid).setContextMenuPolicy(Qt.NoContextMenu)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    wiz = InstallWizard()
    wiz.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
