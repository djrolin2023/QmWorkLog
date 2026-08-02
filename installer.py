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
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication

APP_NAME = "乾明工作台账系统"
DEFAULT_DIR = r"D:\QmWorkLog"
MAIN_EXE_NAME = "QmWorkLog.exe"
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

    def run(self):
        try:
            target = self.target_dir
            os.makedirs(target, exist_ok=True)

            # 主程序 exe（由 PyInstaller add-binary 嵌入）
            src_exe = _resource(MAIN_EXE_NAME)
            if not os.path.exists(src_exe):
                self.finished.emit(False, "未找到主程序文件：%s" % src_exe)
                return
            self.progress.emit(20, "正在复制主程序...")
            dst_exe = os.path.join(target, MAIN_EXE_NAME)
            shutil.copyfile(src_exe, dst_exe)
            os.chmod(dst_exe, 0o755)

            self.progress.emit(60, "正在创建快捷方式...")
            self._create_shortcuts(dst_exe, target)

            self.progress.emit(100, "安装完成")
            self.finished.emit(True, target)
        except Exception as e:
            self.finished.emit(False, "安装失败：%s" % e)

    def _create_shortcuts(self, exe_path, work_dir):
        """用 PowerShell + WScript.Shell 创建桌面与开始菜单快捷方式。"""
        name = APP_NAME
        icon_path = _resource("static\\Images\\logo.ico")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        start_menu = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                                  "Microsoft\\Windows\\Start Menu\\Programs")
        for base in (desktop, start_menu):
            if not os.path.isdir(base):
                continue
            link = os.path.join(base, "%s.lnk" % name)
            ps = [
                "$ws = New-Object -ComObject WScript.Shell",
                "$sc = $ws.CreateShortcut('%s')" % link,
                "$sc.TargetPath = '%s'" % exe_path,
                "$sc.WorkingDirectory = '%s'" % work_dir,
                "$sc.Description = '%s'" % name,
            ]
            if icon_path and os.path.exists(icon_path):
                ps.append("$sc.IconLocation = '%s'" % icon_path)
            ps.append("$sc.Save()")
            try:
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                                "-Command", "\n".join(ps)],
                               capture_output=True, text=True, timeout=30)
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
        self._done = False

    def initializePage(self):
        target = self.field("targetDir")
        self.bar.setValue(0)
        self.status.setText("目标目录：%s" % target)
        self.worker = InstallWorker(target)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, val, msg):
        self.bar.setValue(val)
        self.status.setText(msg)

    def _on_finished(self, ok, msg):
        self._done = ok
        self.status.setText(msg)
        self.completeChanged.emit()

    def isComplete(self):
        return self._done

    def validatePage(self):
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
        icon_path = _resource("static\\Images\\logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(640, 480)
        self.setOption(QWizard.NoCancelButton, False)

        self.addPage(LicensePage())
        self.addPage(PathPage())
        self.addPage(InstallPage())
        self.addPage(FinishPage())


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    wiz = InstallWizard()
    wiz.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
