# -*- coding: utf-8 -*-
"""跨平台安装工具：抽象快捷方式创建 / 默认安装路径 / 平台判断。

被 main.py（首次运行自动建快捷方式）使用，
避免在多处重复维护 Windows/macOS/Linux 的平台差异逻辑。

平台分支：
  - Windows：PowerShell + WScript.Shell 生成 .lnk（桌面 + 开始菜单）
  - macOS：   ~/.Applications 下生成 .app 软链 + 桌面 .app 别名（用 osascript）
  - Linux：   在 ~/.local/share/applications 与桌面生成 .desktop 文件
"""
import os
import sys
import ctypes
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
    """在合适的位置为 exe 创建快捷方式/启动入口（桌面 + 开始菜单/应用）。

    参数：
      exe_path   : 主程序可执行文件的绝对路径
      work_dir   : 程序工作目录（用户数据目录）
      icon_path  : 图标路径（可选）
      name       : 显示名称
    返回：创建的入口文件列表（路径）。
    失败抛出 RuntimeError，便于调用方提示用户。
    """
    plat = get_platform()
    if plat == "windows":
        return _create_shortcuts_windows(exe_path, work_dir, icon_path, name)
    if plat == "darwin":
        return _create_shortcuts_darwin(exe_path, work_dir, icon_path, name)
    if plat == "linux":
        return _create_shortcuts_linux(exe_path, work_dir, icon_path, name)
    return []


def create_desktop_shortcut(exe_path, work_dir, icon_path=None, name=APP_NAME):
    """仅创建桌面快捷方式，返回创建的路径列表（Windows 用）。"""
    if get_platform() != "windows":
        # 非 Windows 复用通用逻辑（桌面也在其中）
        return create_shortcuts(exe_path, work_dir, icon_path, name)
    return _create_desktop_windows(exe_path, work_dir, icon_path, name)


# --------------------------------------------------------------------------
# Windows：PowerShell 脚本文件（WScript.Shell）生成 .lnk
#   注：powershell -Command 传递含括号的脚本易解析失败，故改为写入临时
#   .ps1 文件后用 powershell -File 执行，稳定可靠。
# --------------------------------------------------------------------------
def _real_user_desktop():
    """返回「当前交互登录用户」的桌面真实路径。

    用户的用户配置文件可能被重定向到非系统盘（例如本机 Desktop 实际在
    D:\\Users\\Administrator\\Desktop，而 USERPROFILE 仍是 C:\\Users\\Administrator）。
    因此不能简单拼 C:\\Users\\<user>\\Desktop，必须以注册表 / Shell API 中的
    权威桌面路径为准。

    优先级：
      1) 注册表 HKCU\\...\\User Shell Folders\\Desktop（系统权威，可能为 D: 盘）；
      2) SHGetKnownFolderPath(FOLDERID_Desktop)（提权下可能不准，作兜底）；
      3) WTS 取会话用户后拼 C:\\Users\\<user>\\Desktop；
      4) USERPROFILE/Desktop；
      5) 枚举 C:\\Users\\*\\Desktop（排除系统账户）；
      6) 以上都没有则创建 USERPROFILE/Desktop。
    """
    # 1) 注册表权威桌面路径（最可靠，能正确返回被重定向到 D: 的桌面）
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, "Desktop")
        if val:
            # 支持 %USERPROFILE% 等环境变量展开
            val = os.path.expandvars(val)
            if os.path.isdir(val):
                return val
    except Exception:
        pass
    # 2) SHGetKnownFolderPath（提权进程可能回退到 C:，但仍是系统 API）
    try:
        FOLDERID_Desktop = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
        if hasattr(ctypes.windll, "shcore"):
            ptr = ctypes.c_void_p()
            hr = ctypes.windll.shcore.SHGetKnownFolderPath(
                ctypes.byref(_guid(FOLDERID_Desktop)), 0, None, ctypes.byref(ptr))
            if hr == 0 and ptr:
                buf = ctypes.cast(ptr, ctypes.c_wchar_p).value
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                if buf and os.path.isdir(buf):
                    return buf
    except Exception:
        pass
    # 3) WTS 取当前会话登录用户，拼 C:\Users\<user>\Desktop
    try:
        WTS_CURRENT_SERVER_HANDLE = 0
        WTS_CURRENT_SESSION = -1
        buf = ctypes.c_void_p()
        bytes_ret = ctypes.c_ulong()
        if ctypes.windll.wtsapi32.WTSQuerySessionInformationW(
                WTS_CURRENT_SERVER_HANDLE, WTS_CURRENT_SESSION, 5,  # 5 = WTSUserName
                ctypes.byref(buf), ctypes.byref(bytes_ret)):
            user = ctypes.cast(buf, ctypes.c_wchar_p).value
            ctypes.windll.wtsapi32.WTSFreeMemory(buf)
            if user:
                cand = os.path.join(r"C:\Users", user, "Desktop")
                if os.path.isdir(cand):
                    return cand
    except Exception:
        pass
    # 4) USERPROFILE/Desktop
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    desk = os.path.join(base, "Desktop")
    if os.path.isdir(desk):
        return desk
    # 5) 枚举 C:\Users\*\Desktop 找第一个真实用户桌面（排除 Public）
    users_root = r"C:\Users"
    if os.path.isdir(users_root):
        for u in os.listdir(users_root):
            if u.lower() in ("public", "all users", "default", "default user"):
                continue
            cand = os.path.join(users_root, u, "Desktop")
            if os.path.isdir(cand):
                return cand
    # 6) 用户桌面不存在则创建它（保证可写）
    try:
        os.makedirs(desk, exist_ok=True)
        return desk
    except Exception:
        pass
    return desk
    return desk


def _user_desktop_path():
    """兼容旧调用：返回当前登录用户的桌面真实路径。"""
    return _real_user_desktop()


def _guid(s):
    """把 GUID 字符串转成 ctypes 结构（供 SHGetKnownFolderPath 等使用）。"""
    class _G(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_byte * 8)]
    import uuid
    u = uuid.UUID(s)
    g = _G()
    g.Data1 = u.time_low
    g.Data2 = u.time_mid
    g.Data3 = u.time_hi_version
    for i in range(8):
        g.Data4[i] = u.bytes[8 + i]
    return g


def _create_lnk(link_path, target, work_dir, desc, icon):
    """用 PowerShell 的 WScript.Shell COM 创建 .lnk（图标可靠写入）。

    早期用 ctypes 直接调 IShellLink 在提权进程下 SetIconLocation 写入后
    被 Save 忽略（读回 IconLocation 为空，导致桌面/开始菜单快捷方式无图标）。
    WScript.Shell 方案能稳定把 IconLocation 写成 "<exe>,0"，图标取自 exe
    内嵌资源（PyInstaller 编译进 exe，永久有效，不依赖 _MEIPASS 临时目录）。

    写入路径由调用方传入（已用 _real_user_desktop 定位真实桌面，避免提权
    下落到不可见目录）。脚本写入临时 .ps1 后用 powershell -File 执行，避免
    -Command 传递含括号路径解析失败。
    """
    # 清掉同名旧文件，确保真正重新写入
    try:
        if os.path.exists(link_path):
            os.remove(link_path)
    except Exception:
        pass
    # 图标统一指向 exe 自身内嵌图标（icon 参数被忽略，理由同上）
    icon_loc = "%s,0" % target
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "$link = %s\n" % _ps_str(link_path) +
        "$exe = %s\n" % _ps_str(target) +
        "$work = %s\n" % _ps_str(work_dir or "") +
        "$desc = %s\n" % _ps_str(desc or "") +
        "$icon = %s\n" % _ps_str(icon_loc) +
        "if (Test-Path $link) { Remove-Item $link -Force }\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$s = $ws.CreateShortcut($link)\n"
        "$s.TargetPath = $exe\n"
        "$s.WorkingDirectory = $work\n"
        "$s.Description = $desc\n"
        "$s.IconLocation = $icon\n"
        "$s.Save()\n"
        "if (-not (Test-Path $link)) { exit 1 }\n"
    )
    tmp = link_path + ".lnkbuild.tmp.ps1"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(ps)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", tmp],
            capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and os.path.exists(link_path)
    except Exception:
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _ps_str(s):
    """把 Python 字符串转成 PowerShell 单引号安全字面量。"""
    return "'" + (s or "").replace("'", "''") + "'"


def _create_desktop_windows(exe_path, work_dir, icon_path, name):
    if not exe_path.lower().endswith(".exe"):
        raise RuntimeError("仅支持 .exe 创建 Windows 快捷方式")
    desktop = _real_user_desktop()
    if not os.path.isdir(desktop):
        raise RuntimeError("未找到桌面目录：%s" % desktop)
    link = os.path.join(desktop, "%s.lnk" % name)
    # 快捷方式图标统一使用 exe 内嵌图标（PyInstaller 已将 logo.ico 编译进 exe
    # 资源，永久有效），不再引用 _MEIPASS 临时目录里的 ico（程序退出后被删除，
    # 会导致图标失效）。因此无论传入的 icon_path 是什么都不设外部图标。
    if not _create_lnk(link, exe_path, work_dir, name, None):
        raise RuntimeError("创建桌面快捷方式失败：%s" % link)
    return [link]


def _create_shortcuts_windows(exe_path, work_dir, icon_path, name):
    if not exe_path.lower().endswith(".exe"):
        return []
    desktop = _real_user_desktop()
    # 开始菜单：优先当前用户（APPDATA），再试公共（PROGRAMDATA），均失败不致命
    start_menu_user = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs")
    start_menu_common = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "Microsoft", "Windows", "Start Menu", "Programs")
    # 图标用 exe 内嵌，不引用外部临时 ico（理由同上）
    icon = None

    created = []
    # 桌面快捷方式（落到真实登录用户桌面，必成功）
    if os.path.isdir(desktop):
        link = os.path.join(desktop, "%s.lnk" % name)
        if _create_lnk(link, exe_path, work_dir, name, icon) and os.path.exists(link):
            created.append(link)
    # 开始菜单：先用户后公共，都不行也不致命
    for sm in (start_menu_user, start_menu_common):
        if not sm or not os.path.isdir(sm):
            continue
        link = os.path.join(sm, "%s.lnk" % name)
        try:
            if _create_lnk(link, exe_path, work_dir, name, icon) and os.path.exists(link):
                created.append(link)
                break
        except Exception:
            continue
    if not created:
        raise RuntimeError("未能创建快捷方式（桌面或开始菜单均失败）")
    return created


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
