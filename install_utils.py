# -*- coding: utf-8 -*-
"""跨平台安装工具：抽象快捷方式创建 / 默认安装路径 / 平台判断。

被 installer.py（安装向导）与 main.py（首次运行自动建快捷方式）共用，
避免在多处重复维护 Windows/macOS/Linux 的平台差异逻辑。

平台分支：
  - Windows：PowerShell + WScript.Shell 生成 .lnk（桌面 + 开始菜单）
  - macOS：   ~/.Applications 下生成 .app 软链 + 桌面 .app 别名（用 osascript）
  - Linux：   在 ~/.local/share/applications 与桌面生成 .desktop 文件
"""
import os
import sys
import subprocess


APP_NAME = "乾明工作台账系统"
APP_BIN = "QmWorkLog"          # 主程序文件名（无扩展名，跨平台统一）


def get_platform():
    """返回 'windows' / 'darwin' / 'linux' / 'unknown'。"""
    p = sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "darwin"
    if p.startswith("linux"):
        return "linux"
    return "unknown"


def default_install_dir():
    """返回各平台的默认安装目录。"""
    plat = get_platform()
    home = os.path.expanduser("~")
    if plat == "windows":
        # 有 D 盘建议装到 D，无 D 盘则默认 C 盘
        if os.path.exists("D:\\"):
            return r"D:\QmWorkLog"
        return r"C:\QmWorkLog"
    if plat == "darwin":
        return os.path.join(home, "Applications", "QmWorkLog")
    # linux / unknown：放到用户主目录下
    return os.path.join(home, "QmWorkLog")


def _main_bin_name():
    """当前平台主程序的可执行文件名。"""
    if get_platform() == "windows":
        return APP_BIN + ".exe"
    return APP_BIN


def _quote(path):
    """在脚本里安全包裹单引号路径。"""
    return path.replace("'", "'\\''")


def create_shortcuts(exe_path, work_dir, icon_path=None, name=APP_NAME):
    """在合适的位置为 exe 创建快捷方式/启动入口。

    参数：
      exe_path   : 主程序可执行文件的绝对路径
      work_dir   : 程序工作目录（用户数据目录）
      icon_path  : 图标路径（可选）
      name       : 显示名称
    返回：创建的入口文件列表（路径）；任何平台失败都只记录不抛异常。
    """
    plat = get_platform()
    if plat == "windows":
        return _create_shortcuts_windows(exe_path, work_dir, icon_path, name)
    if plat == "darwin":
        return _create_shortcuts_darwin(exe_path, work_dir, icon_path, name)
    if plat == "linux":
        return _create_shortcuts_linux(exe_path, work_dir, icon_path, name)
    return []


# --------------------------------------------------------------------------
# Windows：PowerShell + WScript.Shell 生成 .lnk
# --------------------------------------------------------------------------
def _create_shortcuts_windows(exe_path, work_dir, icon_path, name):
    if not exe_path.lower().endswith(".exe"):
        return []
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    start_menu = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "Microsoft", "Windows", "Start Menu", "Programs")

    targets = []
    if os.path.isdir(desktop):
        targets.append(os.path.join(desktop, f"{name}.lnk"))
    if os.path.isdir(start_menu):
        targets.append(os.path.join(start_menu, f"{name}.lnk"))
    if not targets:
        return []

    ps_lines = ["$ws = New-Object -ComObject WScript.Shell"]
    for link in targets:
        ps_lines.append("$sc = $ws.CreateShortcut('%s')" % _quote(link))
        ps_lines.append("$sc.TargetPath = '%s'" % _quote(exe_path))
        ps_lines.append("$sc.WorkingDirectory = '%s'" % _quote(work_dir))
        ps_lines.append("$sc.Description = '%s'" % _quote(name))
        if icon_path and os.path.exists(icon_path):
            ps_lines.append("$sc.IconLocation = '%s'" % _quote(icon_path))
        ps_lines.append("$sc.Save()")
    ps_script = "\n".join(ps_lines)

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=30)
        return targets
    except Exception as e:
        print("[shortcut] Windows 创建快捷方式失败：%s" % e, file=sys.stderr)
        return []


# --------------------------------------------------------------------------
# macOS：桌面放 .app 别名（osascript），并软链到 ~/Applications
# --------------------------------------------------------------------------
def _create_shortcuts_darwin(exe_path, work_dir, icon_path, name):
    created = []
    try:
        # 生成 .app 包目录（如果 exe 还不是 .app 形态，则建一个最小 .app
        # 包装，使双击体验与 Windows/Linux 一致）
        app_bundle = os.path.join(work_dir, "%s.app" % name)
        contents = os.path.join(app_bundle, "Contents", "MacOS")
        os.makedirs(contents, exist_ok=True)
        # 复制/链接主程序
        launcher = os.path.join(contents, "QmWorkLog")
        if os.path.abspath(exe_path) != os.path.abspath(launcher):
            if os.path.exists(launcher):
                os.remove(launcher)
            os.symlink(os.path.abspath(exe_path), launcher)
            os.chmod(launcher, 0o755)
        # Info.plist
        info = os.path.join(app_bundle, "Contents", "Info.plist")
        with open(info, "w", encoding="utf-8") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>\n'
                '<key>CFBundleName</key><string>%s</string>\n'
                '<key>CFBundleExecutable</key><string>QmWorkLog</string>\n'
                '<key>CFBundlePackageType</key><string>APPL</string>\n'
                '</dict></plist>\n' % name)

        # 桌面别名（用 osascript 创建真正的别名，而非符号链接）
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(desktop):
            alias = os.path.join(desktop, "%s.app" % name)
            script = (
                'tell application "Finder"\n'
                '  make alias file to POSIX file "%s" at POSIX file "%s"\n'
                'end tell' % (
                    _quote(app_bundle), _quote(desktop)))
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30)
            if os.path.exists(alias):
                created.append(alias)

        # ~/Applications 软链
        user_apps = os.path.join(os.path.expanduser("~"), "Applications")
        os.makedirs(user_apps, exist_ok=True)
        link = os.path.join(user_apps, "%s.app" % name)
        if os.path.exists(link) or os.path.islink(link):
            try:
                os.remove(link)
            except OSError:
                pass
        os.symlink(app_bundle, link)
        created.append(link)
        created.append(app_bundle)
    except Exception as e:
        print("[shortcut] macOS 创建入口失败：%s" % e, file=sys.stderr)
    return created


# --------------------------------------------------------------------------
# Linux：.desktop 文件（桌面 + ~/.local/share/applications）
# --------------------------------------------------------------------------
def _create_shortcuts_linux(exe_path, work_dir, icon_path, name):
    created = []
    try:
        desktop_file = (
            "[Desktop Entry]\n"
            "Version=1.0\n"
            "Type=Application\n"
            "Name=%s\n"
            "Exec=%s\n"
            "Path=%s\n"
            "Terminal=false\n"
            "Categories=Office;Utility;\n"
        ) % (name, exe_path, work_dir)
        if icon_path and os.path.exists(icon_path):
            desktop_file += "Icon=%s\n" % icon_path

        home = os.path.expanduser("~")
        apps_dir = os.path.join(home, ".local", "share", "applications")
        os.makedirs(apps_dir, exist_ok=True)
        app_link = os.path.join(apps_dir, "qmworklog.desktop")
        with open(app_link, "w", encoding="utf-8") as f:
            f.write(desktop_file)
        os.chmod(app_link, 0o755)
        created.append(app_link)

        desktop = os.path.join(home, "Desktop")
        if os.path.isdir(desktop):
            desk_link = os.path.join(desktop, "qmworklog.desktop")
            with open(desk_link, "w", encoding="utf-8") as f:
                f.write(desktop_file)
            os.chmod(desk_link, 0o755)
            created.append(desk_link)
    except Exception as e:
        print("[shortcut] Linux 创建入口失败：%s" % e, file=sys.stderr)
    return created
