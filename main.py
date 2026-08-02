# -*- coding: utf-8 -*-
"""乾明工作台账系统 - Windows 桌面客户端
内置托管 Flask 后台服务，提供主管控窗口与系统托盘驻留。
严格依据 windows.docx 需求实现：
  2.1 主窗口：局域网IP/CPU/内存/外网IP 周期刷新；启动/停止/退出按钮；状态视觉联动
  2.2 系统托盘：窗口关闭/最小化驻留托盘；图标状态联动；右键菜单(启动/停止/打开系统/退出)
  2.3 状态同步：按钮与托盘菜单双向互通
  3   多线程架构，UI 不卡顿；退出清理全部子进程
"""
import os
import sys
import json
import shutil
import subprocess
import urllib.request
import webbrowser
import threading
import time

# 修复 PyQt5 在虚拟环境下找不到字体目录的告警：
# Qt 找不到 QT_QPA_FONTDIR 时会回退到系统字体，但会疯狂打印 stderr 警告。
# 在导入 PyQt5 之前显式指向 Windows 系统字体目录即可消除该告警。
if sys.platform == "win32" and not os.environ.get("QT_QPA_FONTDIR"):
    win_fonts = r"C:\Windows\Fonts"
    if os.path.isdir(win_fonts):
        os.environ["QT_QPA_FONTDIR"] = win_fonts

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout,
    QMenu, QSystemTrayIcon, QMessageBox, QStyle,
    QInputDialog,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QFont

import system_info
from flask_host import FlaskHost
from ui_main import Ui_MainWindow


def _place_in(placeholder, widget):
    """将自绘控件塞进 .ui 预留的占位 QWidget（自定义控件无法在 Designer 中拖出）。"""
    layout = QVBoxLayout(placeholder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignCenter)
    layout.addWidget(widget)


# 本文件位于项目根目录（QmWorkLog），BASE 即根目录
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
VERSION_FILE = os.path.join(BASE, "version.json")
IMG_DIR = os.path.join(BASE, "static", "Images")
LOGO_PATH = os.path.join(IMG_DIR, "logo.ico")           # 主图标（彩色）
LOGO_SVG = os.path.join(IMG_DIR, "logo.svg")             # 矢量 LOGO（清晰）
ICON_RUN = os.path.join(IMG_DIR, "logo.ico")            # 运行中：彩色
ICON_STOP = os.path.join(IMG_DIR, "logo_gray.ico")      # 已停止：灰色
FALLBACK_ICON = os.path.join(IMG_DIR, "favicon.ico")

FLASK_PORT = 8088
FLASK_HOST = "127.0.0.1"
# 系统访问地址
SYSTEM_URL = f"http://{FLASK_HOST}:{FLASK_PORT}"
REQUIRED_DIR = "qmworklog"   # 必须在 QmWorkLog 目录运行（大小写不敏感）

# 状态色
COLOR_RUN = "#1d8a4e"       # 绿（运行中）
COLOR_STOP = "#e74c3c"       # 红（已停止）
GRAY = "#9aa0a6"


def in_required_dir():
    """判断程序是否位于名为 QmWorkLog 的目录中（大小写不敏感）。

    只校验所在文件夹自身的名字，不关心它的父路径，因此
    F:\\Python\\QmWorkLog、D:\\Tools\\abc\\QmWorkLog、C:\\QmWorkLog 均合法。
    """
    cur = os.path.basename(os.path.normpath(ROOT))
    return cur.lower() == REQUIRED_DIR


class GaugeWidget(QWidget):
    """自绘环形进度环（饼图风格），用于展示 CPU / 内存占用率。

    零额外依赖，使用 QPainter 绘制：底色环 + 占用弧 + 中心百分比文字。
    """

    def __init__(self, title, color="#1d8a4e", size=78):
        super().__init__()
        self.title = title
        self.color = color
        self.size = size
        self._percent = 0.0
        self.setFixedSize(size, size)
        self._title_lbl = None  # 由外部布局放置标题

    def set_percent(self, pct):
        pct = max(0.0, min(100.0, float(pct)))
        if abs(pct - self._percent) > 0.05:
            self._percent = pct
            self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen, QColor, QFont as QF
        from PyQt5.QtCore import Qt as QTC
        super().paintEvent(event)
        d = self.size
        margin = 6
        ring = 9
        # 把可用的圆绘制区域收缩，避免圆环被 frame 边框遮挡
        inner = int(margin + ring / 2)
        r = int(d - inner * 2)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 底环
        pen = QPen(QColor("#e6e6e6"), ring)
        pen.setCapStyle(QTC.FlatCap)
        painter.setPen(pen)
        painter.drawEllipse(inner, inner, r, r)
        # 占用弧
        pen = QPen(QColor(self.color), ring)
        pen.setCapStyle(QTC.FlatCap)
        painter.setPen(pen)
        span = int(360 * self._percent / 100.0)
        painter.drawArc(inner, inner, r, r, 90 * 16, -span * 16)
        # 中心百分比（字号随尺寸自适应，避免被圆环遮挡）
        painter.setPen(QColor("#333"))
        painter.setFont(QF("Microsoft YaHei", 13, QF.Bold))
        painter.drawText(self.rect(), QTC.AlignCenter, f"{self._percent:.0f}%")
        painter.end()


class HeartbeatWidget(QWidget):
    """网络流量波形图：浅色背景滚动折线，与窗口风格统一。"""

    def __init__(self, width=160, height=52, max_points=60):
        super().__init__()
        self.setFixedSize(width, height)
        self._w = width
        self._h = height
        self._max = max_points
        self._up = [0.0] * max_points
        self._dn = [0.0] * max_points
        self._peak = 1.0

    def push(self, up, dn):
        self._up.append(float(up))
        self._up.pop(0)
        self._dn.append(float(dn))
        self._dn.pop(0)
        peak = max(self._up + self._dn + [1.0])
        self._peak = max(self._peak * 0.9, peak)
        self.update()

    def _draw_series(self, painter, series, color, fill_alpha=35):
        from PyQt5.QtGui import QColor, QPen, QBrush, QPolygon
        from PyQt5.QtCore import Qt as QTC, QPoint
        n = len(series)
        if n < 2:
            return
        mid = int(self._h / 2.0)
        scale = (self._h / 2.0 - 5.0) / self._peak
        # 折线（加粗）
        pen = QPen(QColor(color), 2.2)
        pen.setCapStyle(QTC.RoundCap)
        pen.setJoinStyle(QTC.RoundJoin)
        painter.setPen(pen)
        step = self._w / (n - 1)
        pts = []
        for i, v in enumerate(series):
            x = int(i * step)
            y = int(mid - v * scale)
            pts.append((x, y))
        for i in range(1, len(pts)):
            painter.drawLine(pts[i - 1][0], pts[i - 1][1],
                             pts[i][0], pts[i][1])
        # 半透明填充到底边
        poly = QPolygon()
        for x, y in pts:
            poly.append(QPoint(x, y))
        poly.append(QPoint(self._w, mid))
        poly.append(QPoint(0, mid))
        painter.setPen(QTC.NoPen)
        c = QColor(color)
        c.setAlpha(fill_alpha)
        painter.setBrush(QBrush(c))
        painter.drawPolygon(poly)
        # 末端亮点
        last = pts[-1]
        painter.setBrush(QColor(color))
        painter.setPen(QColor(color))
        painter.drawEllipse(int(last[0] - 2.5), int(last[1] - 2.5), 5, 5)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QPen
        from PyQt5.QtCore import Qt as QTC
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 浅色背景（与窗口融合）
        painter.fillRect(self.rect(), QColor("#f5f5f5"))
        # 边框
        pen = QPen(QColor("#d0d0d0"), 1)
        painter.setPen(pen)
        painter.drawRect(0, 0, self._w - 1, self._h - 1)
        # 中线
        mid = int(self._h / 2)
        pen = QPen(QColor("#cccccc"), 1)
        pen.setStyle(QTC.DashLine)
        painter.setPen(pen)
        painter.drawLine(0, mid, self._w, mid)
        # 波形：上行（橙）/下行（蓝）
        self._draw_series(painter, self._up, "#e67e22", fill_alpha=40)
        self._draw_series(painter, self._dn, "#2980b9", fill_alpha=40)
        painter.end()


def list_drives():
    """返回本机所有盘符列表，如 ['C', 'D', 'E']。"""
    drives = []
    for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if os.path.exists(d + ":\\"):
            drives.append(d)
    return drives


def pick_target_drive():
    """让用户选择目标盘符，返回单个字母（如 'D'）。
    默认推荐：单分区->C，多盘符->D。"""
    drives = list_drives()
    if not drives:
        return "C"
    default = "D" if len(drives) > 1 else "C"
    if default not in drives:
        default = drives[0]
    items = [f"{d}:\\" for d in drives]
    idx = items.index(f"{default}:\\") if f"{default}:\\" in items else 0
    item, ok = QInputDialog.getItem(
        None, "选择安装盘符",
        "当前不在 QmWorkLog 目录，请选择程序所在的盘符\n"
        "将在所选盘符下创建/使用 QmWorkLog 目录：",
        items, idx, False)
    if ok and item:
        return item[0]  # 取首字母
    return None  # 用户取消


def ensure_run_dir():
    """确保程序位于 QmWorkLog 目录中运行。

    已在 QmWorkLog 目录（无论父路径是什么）-> 直接放行。
    否则让用户选盘符，将整个项目迁移到 X:\\QmWorkLog（不嵌套、
    已存在则复用），随后从新目录重启自身。
    返回 True 表示可以继续启动界面。
    """
    if in_required_dir():
        return True

    drive = pick_target_drive()
    if not drive:
        return False

    target = os.path.join(drive + ":\\", "QmWorkLog")
    if os.path.normcase(os.path.normpath(target)) == \
            os.path.normcase(os.path.normpath(ROOT)):
        return True

    try:
        os.makedirs(target, exist_ok=True)
        _copy_project(ROOT, target)
    except Exception as e:
        QMessageBox.critical(
            None, "迁移失败",
            f"无法将程序迁移到 {target}：\n{e}")
        return False

    new_script = os.path.join(target, "main.py")
    if not os.path.exists(new_script):
        QMessageBox.critical(
            None, "迁移失败",
            f"迁移后未找到入口文件：\n{new_script}")
        return False

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) \
            if os.name == "nt" else 0
        subprocess.Popen([sys.executable, new_script],
                         cwd=target,
                         creationflags=creationflags)
    except Exception as e:
        QMessageBox.critical(
            None, "启动失败",
            f"已迁移到 {target}，但重启失败：\n{e}\n请手动运行该目录下的程序。")
        return False

    QMessageBox.information(
        None, "已迁移",
        f"程序已迁移到：\n{target}\n\n将从新目录重新启动，本窗口即将关闭。")
    return False


def _copy_project(src, dst):
    """将项目文件复制到目标目录，跳过缓存/虚拟环境等无需迁移的内容。
    已存在的文件会被覆盖，目标目录中的其他文件保持不动。"""
    skip_dirs = {"__pycache__", ".git", ".venv", "venv", "node_modules",
                 ".idea", ".vscode", "build", "dist", "client", "Backup",
                 "DB", "Data", "app.log"}
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        rel = os.path.relpath(root, src)
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out_dir, exist_ok=True)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            try:
                shutil.copy2(os.path.join(root, name),
                             os.path.join(out_dir, name))
            except Exception:
                pass


def _first_existing(*paths):
    """返回第一个存在的路径，都不存在则返回 None。"""
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def _app_exe_path():
    """返回当前可执行文件路径。

    打包成 EXE 时 sys.executable 即为 exe 完整路径；
    脚本方式运行时回退为 main.py（仅用于非 EXE 调试，
    不会真正创建快捷方式，见 create_shortcuts_once 内的判断）。
    """
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def create_shortcuts_once():
    """首次运行 EXE 时，自动在「桌面」和「开始菜单」创建快捷方式。

    - 仅在 PyInstaller 打包环境（sys.frozen）下生效，脚本调试不创建。
    - 用项目目录下的标记文件 .shortcut_created 防止重复创建。
    - 通过 PowerShell 调用 WScript.Shell COM 生成 .lnk，无需额外依赖。
    失败仅记录日志，不阻断主程序启动。
    """
    if not getattr(sys, "frozen", False):
        return  # 非 EXE 环境（如 python main.py）不创建快捷方式

    marker = os.path.join(BASE, ".shortcut_created")
    if os.path.exists(marker):
        return

    exe_path = _app_exe_path()
    if not os.path.exists(exe_path) or not exe_path.lower().endswith(".exe"):
        return

    icon_path = _first_existing(LOGO_PATH, FALLBACK_ICON)
    name = "乾明工作台账系统"

    # 桌面路径
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    # 开始菜单「程序」目录
    start_menu = os.path.join(
        os.environ.get("PROGRAMDATA",
                       r"C:\ProgramData"),
        "Microsoft", "Windows", "Start Menu", "Programs")

    targets = []
    if os.path.isdir(desktop):
        targets.append(os.path.join(desktop, f"{name}.lnk"))
    if os.path.isdir(start_menu):
        targets.append(os.path.join(start_menu, f"{name}.lnk"))

    if not targets:
        return

    # 用 PowerShell 生成 .lnk（WScript.Shell COM）
    ps_lines = ["$ws = New-Object -ComObject WScript.Shell"]
    for link in targets:
        esc = link.replace("'", "\\'")
        ps_lines.append(f"$sc = $ws.CreateShortcut('{esc}')")
        ps_lines.append(f"$sc.TargetPath = '{exe_path}'")
        ps_lines.append(f"$sc.WorkingDirectory = '{BASE}'")
        ps_lines.append(f"$sc.Description = '{name}'")
        if icon_path:
            ps_lines.append(f"$sc.IconLocation = '{icon_path}'")
        ps_lines.append("$sc.Save()")
    ps_script = "\n".join(ps_lines)

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             ps_script],
            capture_output=True, text=True, timeout=30)
        # 写标记文件，避免下次重复创建
        with open(marker, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        # 失败不阻断启动，仅记录
        try:
            with open(os.path.join(BASE, "app.log"), "a",
                      encoding="utf-8") as f:
                f.write(f"[shortcut] 创建快捷方式失败：{e}\n")
        except Exception:
            pass


def get_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "未知")
    except Exception:
        return "未知"


class Worker(threading.Thread):
    """后台工作线程：周期性采集系统信息，通过回调抛给主线程更新 UI。"""

    def __init__(self, on_update, interval=1.0):
        super().__init__(daemon=True)
        self.on_update = on_update
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                data = {
                    "lan": system_info.get_lan_ip(),
                    "internal": system_info.get_internal_ip(),
                    "segment": system_info.get_lan_segment(),
                    "lan_ips": system_info.get_all_lan_ips(),
                    "cpu": system_info.get_cpu_percent(interval=0.2),
                    "mem": system_info.get_memory_percent(),
                    "mem_used_total": system_info.get_memory_used_total(),
                    "ext_v4": system_info.get_public_ipv4(),
                    "ext_v6": system_info.get_public_ipv6(),
                }
                if not self._stop.is_set():
                    self.on_update(data)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


class MainWindow(QMainWindow):
    # 信号：将工作线程的数据送到主线程刷新 UI
    data_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.version = get_version()
        self.host = FlaskHost()
        self.worker = None
        self.running = False
        self.tray = None
        self._tray_tip_shown = False
        self.start_ts = time.time()

        self._build_ui()
        self._build_tray()
        self.data_signal.connect(self._update_info)

        # 运行计时器（每秒刷新运行时长显示）
        self.uptime_timer = QTimer(self)
        self.uptime_timer.timeout.connect(self._refresh_uptime)
        self.uptime_timer.start(1000)
        # 时钟计时器（每秒刷新当前时间）
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._refresh_clock)
        self.clock_timer.start(1000)
        self._refresh_clock()

        # 启动后台采集线程
        self.worker = Worker(self.data_signal.emit, interval=1.0)
        self.worker.start()

        # 程序启动自动初始化：默认启动服务，并自动打开系统页面
        self._set_running(False)
        self.start_service()
        QTimer.singleShot(1500, self.open_system)  # 等服务起来后再开页面

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        # 从 Qt Designer 生成的 ui_main.py 加载静态布局
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 窗口图标
        win_icon = _first_existing(LOGO_PATH, FALLBACK_ICON)
        if win_icon:
            self.setWindowIcon(QIcon(win_icon))

        # 把 ui 中的控件引用挂到 self，方便后续逻辑访问
        self.logo_label = self.ui.logo_label
        self.addr_val = self.ui.addr_val
        self.addr_val2 = self.ui.addr_val2
        self.v4_val = self.ui.v4_val
        self.v6_val = self.ui.v6_val
        self.pid_label = self.ui.pid_label
        self.time_label = self.ui.time_label
        self.user_label = self.ui.user_label
        self.uptime_label = self.ui.uptime_label
        self.tip_label = self.ui.tip_label
        self.btn_toggle = self.ui.btn_toggle
        self.btn_restart = self.ui.btn_restart
        self.btn_exit = self.ui.btn_exit

        # 加载 LOGO（矢量优先 + DPR）
        self._load_logo()

        # 标题与版本号：重叠定位，版本号落在标题文字右下角
        self._build_title_overlay()

        # 地址标签：可点击链接样式
        for val in (self.addr_val2, self.v4_val, self.v6_val):
            val.setOpenExternalLinks(True)
            val.setTextInteractionFlags(Qt.TextBrowserInteraction)
            val.setStyleSheet("font-weight:600; color:#1a73e8;")
        self.addr_val2.setWordWrap(False)
        self.addr_val.setText(SYSTEM_URL)

        # ---- 硬件监控：把自绘控件塞进 .ui 预留的占位 QWidget ----
        self.cpu_gauge = GaugeWidget("CPU", color="#e67e22", size=76)
        self.mem_gauge = GaugeWidget("内存", color="#2980b9", size=76)
        self.disk_gauge = GaugeWidget("磁盘", color="#27ae60", size=76)
        _place_in(self.ui.cpuPlaceholder, self.cpu_gauge)
        _place_in(self.ui.memPlaceholder, self.mem_gauge)
        _place_in(self.ui.diskPlaceholder, self.disk_gauge)
        self.heartbeat = HeartbeatWidget(width=160, height=52, max_points=60)
        _place_in(self.ui.netPlaceholder, self.heartbeat)
        # 网络采样基准（用于计算速率）
        self._net_io_last = None
        self._net_io_ts = 0.0

        # 进程信息
        self.pid_label.setText(f"进程 PID：{os.getpid()}")
        self._load_current_user()   # 读取系统账号

        # 按钮信号
        self.btn_restart.clicked.connect(self.restart_service)
        self.btn_toggle.clicked.connect(self.toggle_service)
        self.btn_exit.clicked.connect(self.confirm_exit)
        for b in (self.btn_restart, self.btn_toggle, self.btn_exit):
            b.setCursor(Qt.PointingHandCursor)

        self._apply_style()

    def _build_title_overlay(self):
        """标题与版本号重叠定位：版本号绝对定位在标题文字右下角。

        容器 title_box 在 .ui 中尺寸固定 360x64，标题与版本号
        用 move() 绝对定位，版本号（11px 浅灰）落在标题基线右下。
        """
        box = self.ui.title_box
        self.title_label = QLabel("乾明工作台账系统", box)
        self.title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self.title_label.adjustSize()
        self.title_label.move(0, (64 - self.title_label.height()) // 2)
        self.ver_label = QLabel(f"V{self.version}", box)
        self.ver_label.setFont(QFont("Microsoft YaHei", 11))
        self.ver_label.setStyleSheet("color:#aaa;")
        self.ver_label.adjustSize()
        self.ver_label.move(
            self.title_label.x() + self.title_label.width(),
            self.title_label.y() + self.title_label.height()
            - self.ver_label.height() - 1)

    def _load_logo(self):
        # 优先用矢量 SVG，任意尺寸都清晰；其次用 ICO
        path = _first_existing(LOGO_SVG, LOGO_PATH, FALLBACK_ICON)
        icon = QIcon(path) if path else QIcon()
        # 用设备像素比渲染，提升清晰度
        from PyQt5.QtCore import QSize
        dpr = self.logo_label.devicePixelRatioF() or 1.0
        base = 64
        pix = icon.pixmap(QSize(base, base) * dpr)
        pix.setDevicePixelRatio(dpr)
        if pix.isNull():
            # 用文字兜底
            self.logo_label.setText("QM")
            self.logo_label.setStyleSheet(
                "background:#1d8a4e;color:#fff;border-radius:8px;"
                "font-weight:700;font-size:16px;"
                "qproperty-alignment:AlignCenter;"
            )
        else:
            self.logo_label.setScaledContents(True)
            self.logo_label.setPixmap(pix)

    def _apply_style(self):
        """二态按钮配色：运行中=红色「停止服务」；停止=绿色「启动服务」。
        带 hover 高亮 + 点击下压视觉效果。"""
        if self.running:
            # 运行中：按钮显示「停止服务」（红）
            self.btn_toggle.setText("停止服务")
            self.btn_toggle.setStyleSheet(f"""
                QPushButton {{
                    background:{COLOR_STOP}; color:#fff; border:none;
                    border-radius:6px; font-weight:600;
                }}
                QPushButton:hover {{ background:#c0392b; }}
                QPushButton:pressed {{ background:#a93226; padding-top:2px; }}
            """)
        else:
            # 停止：按钮显示「启动服务」（绿）
            self.btn_toggle.setText("启动服务")
            self.btn_toggle.setStyleSheet(f"""
                QPushButton {{
                    background:{COLOR_RUN}; color:#fff; border:none;
                    border-radius:6px; font-weight:600;
                }}
                QPushButton:hover {{ background:#157a43; }}
                QPushButton:pressed {{ background:#10612f; padding-top:2px; }}
            """)
        self.btn_exit.setStyleSheet("""
            QPushButton { background:#fff; color:#333; border:1px solid #ccc;
                          border-radius:6px; }
            QPushButton:hover { background:#f2f2f2; border-color:#999; }
            QPushButton:pressed { padding-top:2px; }
        """)

        # 轮询当前 Web 登录用户（每 5 秒）
        self._user_timer = QTimer(self)
        self._user_timer.timeout.connect(self._poll_current_user)
        self._user_timer.start(5000)
        self._poll_current_user()

    # ---------------- 托盘 ----------------
    def _state_icon(self, running):
        """按服务状态取图标：运行中=彩色 logo，已停止=灰色 logo。
        找不到对应文件时逐级回退，最终用系统内置图标兜底。"""
        path = _first_existing(ICON_RUN if running else ICON_STOP,
                               LOGO_PATH, FALLBACK_ICON)
        if path:
            icon = QIcon(path)
            if not icon.pixmap(32, 32).isNull():
                return icon
        return self.style().standardIcon(QStyle.SP_ComputerIcon)

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._state_icon(False))
        self.tray.setToolTip(f"乾明工作台账系统 V{self.version}")
        self.tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        # 单个动态动作：根据服务状态显示「停止服务」或「启动服务」，
        # 与窗口主按钮行为一致（点击后按当前状态切换）。
        self.tray_action_toggle = menu.addAction("启动服务")
        self.tray_action_toggle.triggered.connect(self.toggle_service)
        self.tray_action_restart = menu.addAction("重启系统")
        self.tray_action_open = menu.addAction("打开系统")
        menu.addSeparator()
        self.tray_action_exit = menu.addAction("退出系统")
        self.tray_action_restart.triggered.connect(self.restart_service)
        self.tray_action_open.triggered.connect(self.open_system)
        self.tray_action_exit.triggered.connect(self.confirm_exit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _set_tray_icon(self, running):
        """服务运行=彩色图标；停止=灰色图标，并联动菜单动态按钮。

        托盘菜单的「启动/停止」采用与窗口按钮一致的动态文案：
        运行中显示「停止服务」，停止时显示「启动服务」，二者互斥只显其一。
        """
        if not self.tray:
            return
        self.tray.setIcon(self._state_icon(running))
        # 动态动作文案随状态切换（与窗口 btn_toggle 同步）
        self.tray_action_toggle.setText("停止服务" if running else "启动服务")

    def _show_window(self):
        self.showNormal()
        safe_raise(self)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            safe_raise(self)

    # ---------------- 状态控制 ----------------
    def start_service(self):
        if self.running:
            return
        ok = self.host.start()
        if ok:
            self._set_running(True)
        else:
            QMessageBox.warning(self, "启动失败", "Flask 后台服务启动失败，请检查 app.py。")

    def stop_service(self):
        if not self.running:
            return
        self.host.stop()
        system_info.reset_cache()
        self._set_running(False)

    def toggle_service(self):
        """二态切换：运行中->停止；停止->启动。"""
        if self.running:
            self.stop_service()
        else:
            self.start_service()

    def restart_service(self):
        """重启系统：先停止后台服务，再重新启动。"""
        self.host.stop()
        system_info.reset_cache()
        self._set_running(False)
        # 稍等子进程彻底退出后再启动，避免端口占用
        QTimer.singleShot(600, self.start_service)

    def open_system(self):
        """用默认浏览器打开系统页面。"""
        webbrowser.open(SYSTEM_URL)

    def _set_running(self, running):
        """统一设置运行状态：窗口按钮 + 托盘图标/菜单 同步。"""
        self.running = running
        self._apply_style()
        self._set_tray_icon(running)
        if self.tray:
            state = "运行中" if running else "已停止"
            self.tray.setToolTip(
                f"乾明工作台账系统 V{self.version}  [{state}]")

    def confirm_exit(self):
        reply = QMessageBox.question(
            self, "退出确认", "确定要退出系统吗？将同时关闭后台服务。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._real_exit()

    def _real_exit(self):
        """主动终止全部关联子进程，释放资源。"""
        try:
            self.host.cleanup()
        except Exception:
            pass
        if self.worker:
            self.worker.stop()
        QApplication.quit()

    # ---------------- 信息刷新 ----------------
    def _update_info(self, data):
        def fmt(v, fail="获取失败"):
            if v is None:
                return fail
            return v if v != "" else "无"

        # 登录地址：列出本机所有真实网卡对应的访问网址（多网卡场景），
        # 单网卡时只显示一个，虚拟网卡已被 system_info.get_all_lan_ips 排除，
        # 端口统一为 FLASK_PORT
        lan_ips = data.get("lan_ips") or []
        if lan_ips:
            links = "".join(
                f'<a href="http://{ip}:{FLASK_PORT}">'
                f'http://{ip}:{FLASK_PORT}</a><br/>'
                for ip in lan_ips
            )
            self.addr_val2.setText(links)
            self.addr_val2.setToolTip("本机各真实网卡对应的访问网址，复制到同局域网设备浏览器打开")
        else:
            self.addr_val2.setText("获取失败")
        # 外网 IPv4（端口统一 FLASK_PORT）
        ext_v4 = data.get("ext_v4")
        if ext_v4:
            self.v4_val.setText(
                f'<a href="http://{ext_v4}:{FLASK_PORT}">'
                f'http://{ext_v4}:{FLASK_PORT}</a>')
        else:
            self.v4_val.setText(fmt(None))
        # 外网 IPv6（方括号包裹地址，端口统一 FLASK_PORT）
        ext_v6 = data.get("ext_v6")
        if ext_v6:
            self.v6_val.setText(
                f'<a href="http://[{ext_v6}]:{FLASK_PORT}">'
                f'http://[{ext_v6}]:{FLASK_PORT}</a>')
        else:
            self.v6_val.setText(fmt(None, fail="无"))

        cpu = data.get("cpu")
        if cpu is not None:
            self.cpu_gauge.set_percent(cpu)
        mem = data.get("mem")
        if mem is not None:
            self.mem_gauge.set_percent(mem)
        # 磁盘使用率
        try:
            import psutil
            du = psutil.disk_usage('/')
            self.disk_gauge.set_percent(du.percent)
        except Exception:
            pass
        # 网络流量（上传/下载速度）
        try:
            import psutil
            nio = psutil.net_io_counters()
            now = time.time()
            if self._net_io_last is not None:
                dt = now - self._net_io_ts
                if dt > 0.1:
                    up = (nio.bytes_sent - self._net_io_last[0]) / dt
                    dn = (nio.bytes_recv - self._net_io_last[1]) / dt
                    self.net_up_lbl.setText(
                        "↑ " + self._fmt_speed(up))
                    self.net_down_lbl.setText(
                        "↓ " + self._fmt_speed(dn))
                    # 推入心电图，形成滚动波形（上行橙/下行蓝）
                    self.heartbeat.push(up, dn)
            self._net_io_last = (nio.bytes_sent, nio.bytes_recv)
            self._net_io_ts = now
        except Exception:
            pass

    def _fmt_speed(self, bps):
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.1f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        return f"{bps:.0f} B/s"

    def _refresh_uptime(self):
        delta = int(time.time() - self.start_ts)
        d, rem = divmod(delta, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        self.uptime_label.setText(
            f"系统已运行：{d} 天 {h} 小时 {m} 分 {s} 秒")

    def _refresh_clock(self):
        self.time_label.setText(
            "时间：" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    def _load_current_user(self):
        """初始化账号标签占位（后续由 _poll_current_user 轮询覆盖）。"""
        self.user_label.setText("账号：--")

    def _poll_current_user(self):
        """每 5 秒轮询 Flask 后端 /api/current_user 获取真正当前登录用户。"""
        try:
            url = f"http://{FLASK_HOST}:{FLASK_PORT}/api/current_user"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            user = data.get("user")
            if user:
                self.user_label.setText(f"账号：{user}")
            else:
                self.user_label.setText("账号：未登录")
        except Exception:
            pass

    # ---------------- 窗口关闭/最小化 -> 托盘 ----------------
    def closeEvent(self, event):
        """关闭/最小化不直接终止，隐藏到托盘。"""
        # 无托盘可用时不能隐藏，否则用户再也找不回窗口 -> 走正常退出确认
        if not self.tray:
            event.ignore()
            self.confirm_exit()
            return
        event.ignore()
        self.hide()
        if not self._tray_tip_shown:
            self.tray.showMessage(
                "乾明工作台账系统",
                "窗口已关闭，程序仍在后台运行（最小化到托盘）。\n"
                "如需完全退出，请右键托盘图标选择「退出程序」。",
                QSystemTrayIcon.Information, 2500)
            self._tray_tip_shown = True

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange and self.isMinimized():
            if self.tray:
                self.hide()


def safe_raise(widget):
    """安全地置前窗口。

    部分 Qt 平台插件（如 offscreen，常因缺少显示环境/环境变量
    QT_QPA_PLATFORM=offscreen 被误设）不支持 raise_()，会抛
    'This plugin does not support raise()' 异常。这里静默忽略，
    避免因置前失败而连带让整个程序崩溃。
    """
    try:
        widget.raise_()
        widget.activateWindow()
    except Exception:
        pass


def _warn_no_display():
    """当 Qt 使用 offscreen 等无显示平台插件时给出明确提示。

    该情况下系统托盘不可用、窗口无法显示，通常是因为环境变量
    QT_QPA_PLATFORM=offscreen 被设置、或在无桌面会话中运行。
    打印提示帮助用户定位，但不阻断启动（后续托盘会自动降级）。
    """
    try:
        from PyQt5.QtCore import QCoreApplication
        platform = QCoreApplication.platformName()
    except Exception:
        platform = "unknown"
    if platform == "offscreen":
        msg = (
            "\n[警告] Qt 当前使用 offscreen 平台插件（无真实显示环境），"
            "系统托盘与窗口将无法显示。\n"
            "  常见原因：环境变量 QT_QPA_PLATFORM 被设为 offscreen，"
            "或程序在无桌面会话中运行。\n"
            "  解决：在命令行执行  [Environment]::SetEnvironmentVariable("
            "'QT_QPA_PLATFORM','')  清除该变量后重新运行；\n"
            "        或在有图形桌面的会话中双击运行程序。\n"
        )
        print(msg, file=sys.stderr)


def main():
    # QApplication 必须先创建，否则目录选择框与提示框无法弹出
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关键：关闭窗口不退出，走托盘

    _warn_no_display()  # 无显示环境下提前提示，便于用户排查

    # 确保位于 QmWorkLog 目录（不在则迁到所选盘符的 QmWorkLog 并重启）
    if not ensure_run_dir():
        return

    # 首次运行 EXE 时，自动在桌面与开始菜单创建快捷方式
    create_shortcuts_once()

    win = MainWindow()
    win.show()
    safe_raise(win)        # 提到最前（offscreen 下安全跳过）
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
