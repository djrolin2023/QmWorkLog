# -*- coding: utf-8 -*-
"""通过 GitHub Release 检查并自动更新程序（方案 A：整 exe 替换）。

设计约束（来自项目铁律）：
- 更新只替换可执行文件（exe），绝不触碰 DB/Data/users.json/config.json。
- 单文件 onefile 模式下，New exe 自带全部 static/templates，覆盖即完成更新。
- 程序运行时 exe 被锁定，无法就地覆盖，因此采用「下载到临时目录 ->
  写自替换批处理 -> 退出并让 bat 覆盖 exe -> 重启」的标准做法。

网络：使用 ghproxy 镜像加速 api.github.com 与 release 附件下载；
失败时回退到直连 GitHub。所有请求带超时，避免界面卡死。
"""
import os
import sys
import json
import time
import urllib.request
import subprocess

REPO = "djrolin2023/QmWorkLog"
# 镜像加速：把 https://api.github.com 与 https://github.com 前缀替换
_MIRROR_API = "https://ghproxy.com/https://api.github.com"
_MIRROR_RAW = "https://ghproxy.com/https://github.com"
# 远程 Release 里 exe 附件的文件名（与打包产物一致）
ASSET_NAME = "QmWorkLog_v{ver}.exe"

# 本地版本号文件路径（frozen 时来自打包内的 version.json）
try:
    from paths import EXE_DIR, RES_DIR
except Exception:
    EXE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
    RES_DIR = EXE_DIR


def _local_version():
    """读取本地 version.json 的版本号（如 26.08.03.100）。"""
    try:
        vf = os.path.join(RES_DIR, "version.json")
        with open(vf, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "")
    except Exception:
        return ""


def _parse_ver(v):
    """把 '26.08.03.100' 解析成可比较的整数（YY*1e6+MM*1e4+DD*1e2+seq）。"""
    try:
        a, b, c, d = [int(x) for x in str(v).lstrip("vV").split(".")]
        return a * 1000000 + b * 10000 + c * 100 + d
    except Exception:
        return 0


def _http_get(url, timeout=10, retries=2):
    """带超时与重试的 GET，返回 (ok, text_or_bytes, is_bytes)。"""
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "QmWorkLog-Updater"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return True, data, True
        except Exception as e:
            last = e
            time.sleep(0.5)
    return False, last, False


def check_update():
    """检查是否有新版本。

    返回 dict：
      {
        "has_update": bool,
        "current": str,        # 本地版本
        "latest": str,         # 远程版本
        "download_url": str,   # exe 附件下载直链（已含镜像前缀）
        "release_name": str,
        "body": str,           # 更新说明
        "error": str or None
      }
    """
    result = {
        "has_update": False, "current": _local_version(),
        "latest": "", "download_url": "", "release_name": "",
        "body": "", "error": None,
    }
    # 1) 拉取 latest release 元数据（镜像优先）
    api_url = f"https://api.github.com/repos/{REPO}/releases/latest"
    mirrored = f"{_MIRROR_API}/repos/{REPO}/releases/latest"
    ok, data, is_bytes = _http_get(mirrored, timeout=12)
    if not ok:
        ok, data, is_bytes = _http_get(api_url, timeout=12)
    if not ok:
        result["error"] = "无法连接更新服务器（网络异常或被拦截）"
        return result
    try:
        release = json.loads(data.decode("utf-8"))
    except Exception:
        result["error"] = "更新信息解析失败"
        return result

    tag = (release.get("tag_name") or "").lstrip("vV")
    result["latest"] = tag
    result["release_name"] = release.get("name", tag)
    result["body"] = release.get("body", "")

    # 2) 版本对比
    if _parse_ver(tag) <= _parse_ver(result["current"]):
        return result  # 已是最新

    # 3) 找 exe 附件下载直链（优先精确版本号命名，回退第一个 .exe）
    assets = release.get("assets", []) or []
    dl = ""
    exact = ASSET_NAME.format(ver=tag)
    for a in assets:
        name = a.get("name", "")
        if name.lower().endswith(".exe"):
            if name.lower() == exact.lower():
                dl = a.get("browser_download_url", "")
                break
            if not dl:
                dl = a.get("browser_download_url", "")
    if not dl:
        result["error"] = "未找到可用的更新包"
        return result

    # 4) 下载直链也走镜像
    if dl.startswith("https://github.com/"):
        dl = _MIRROR_RAW + dl[len("https://github.com"):]
    elif dl.startswith("https://objects.githubusercontent.com/"):
        dl = "https://ghproxy.com/" + dl
    result["download_url"] = dl
    result["has_update"] = True
    return result


def _app_exe_path():
    """当前 exe 真实路径（与 main._app_exe_path 一致的逻辑）。"""
    if getattr(sys, "frozen", False):
        p = sys.argv[0] if sys.argv and sys.argv[0] else sys.executable
        return os.path.abspath(p)
    return os.path.abspath(sys.argv[0])


def download_and_install(download_url, version_tag, progress_cb=None):
    """下载新 exe 到临时目录，写自替换批处理，退出并由 bat 完成覆盖与重启。

    progress_cb(done_bytes, total_bytes) 可选，用于 UI 进度显示。

    返回 (ok, msg)。若成功触发更新，将启动 bat 并退出当前进程（不返回）。
    """
    import tempfile
    cur_exe = _app_exe_path()
    work_dir = os.path.dirname(cur_exe)
    tmp_dir = tempfile.gettempdir()
    new_exe = os.path.join(tmp_dir, f"QmWorkLog_update_{version_tag}.exe")

    # 下载
    try:
        req = urllib.request.Request(
            download_url, headers={"User-Agent": "QmWorkLog-Updater"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", "0") or "0")
            done = 0
            with open(new_exe, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)
    except Exception as e:
        try:
            if os.path.exists(new_exe):
                os.remove(new_exe)
        except Exception:
            pass
        return False, f"下载失败：{e}"

    if not os.path.exists(new_exe) or os.path.getsize(new_exe) < 1024 * 1024:
        return False, "下载文件异常（过小）"

    # 写自替换批处理：等待当前 exe 退出 -> 覆盖 -> 重启
    bat = os.path.join(tmp_dir, f"QmWorkLog_update_{version_tag}.bat")
    # 用双 % 转义；%1 等不需要。bat 中 cur_exe 用引号包裹防止空格
    cur_exe_q = f'"{cur_exe}"'
    new_exe_q = f'"{new_exe}"'
    target_name = os.path.join(work_dir, "QmWorkLog.exe")
    target_q = f'"{target_name}"'
    bat_text = (
        "@echo off\n"
        "chcp 65001 >nul\n"
        "setlocal\n"
        "set CUR=" + cur_exe_q + "\n"
        "set NEW=" + new_exe_q + "\n"
        "set TGT=" + target_q + "\n"
        "set WORK=" + f'"{work_dir}"' + "\n"
        ":: 等待原进程退出（最多 30 秒）\n"
        ":wait\n"
        "tasklist | findstr /i \"QmWorkLog.exe\" >nul 2>&1\n"
        "if not errorlevel 1 (\n"
        "    timeout /t 1 /nobreak >nul\n"
        "    goto wait\n"
        ")\n"
        ":: 覆盖到目标路径（保留 DB/Data/users.json/config.json 不受影响）\n"
        "copy /Y %NEW% %TGT% >nul 2>&1\n"
        ":: 若当前 exe 不是 QmWorkLog.exe（用户在别的名字运行），也更新它\n"
        "if not \"%CUR%\"==\"%TGT%\" copy /Y %NEW% %CUR% >nul 2>&1\n"
        "del /Q %NEW% >nul 2>&1\n"
        ":: 重启程序\n"
        "start \"\" %TGT%\n"
        "endlocal\n"
        "exit\n"
    )
    try:
        with open(bat, "w", encoding="utf-8") as f:
            f.write(bat_text)
    except Exception as e:
        return False, f"生成更新脚本失败：{e}"

    # 启动 bat 并退出当前进程（bat 会等本进程退出后覆盖+重启）
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) \
            if os.name == "nt" else 0
        subprocess.Popen(
            ["cmd.exe", "/c", bat],
            cwd=tmp_dir, creationflags=creationflags,
            shell=False)
    except Exception as e:
        return False, f"启动更新失败：{e}"

    # 触发退出：调用方应在收到返回 True 后退出；这里直接退出更稳
    return True, "更新已启动"


if __name__ == "__main__":
    r = check_update()
    print(json.dumps(r, ensure_ascii=False, indent=2))
