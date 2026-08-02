# -*- coding: utf-8 -*-
"""系统信息获取：
  局域网 IP、CPU 使用率、内存使用率、内网/外网 IPv4/IPv6。
所有函数设计为可独立失败，失败返回 None，由调用方负责展示「获取失败」/「无」。
"""
import socket
import threading
import urllib.request
import json

# ---- 缓存（外网 IP 无需每秒刷新，首次获取后缓存）----
_cache = {"lan": None, "ext_v4": None, "ext_v6": None}
_cache_lock = threading.Lock()

IPV4_URL = "https://v4.yinghualuo.cn/bejson"
IPV6_URL = "https://v6.yinghualuo.cn/bejson"
HTTP_TIMEOUT = 6


def _fetch_json(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "QmWorkLog-Client"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_lan_ip():
    """本机局域网 IPv4（排除回环）。"""
    if _cache["lan"]:
        return _cache["lan"]
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = None
    if not ip or ip == "127.0.0.1":
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                cand = info[4][0]
                if cand != "127.0.0.1":
                    ip = cand
                    break
        except Exception:
            ip = None
    _cache["lan"] = ip
    return ip


def get_internal_ip():
    """内网地址：主网卡 IPv4。"""
    return get_lan_ip()


def get_lan_segment():
    """局域网网段标识：主 IP 前三段 + .x。"""
    ip = get_lan_ip()
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
    return ip


def _is_private_ip(ip):
    """判断是否为局域网私有地址（同网段设备可访问）。

    包含 RFC1918 私网段与链路本地 169.254.x；排除公网 IP 与回环。
    """
    if not ip or ip == "127.0.0.1":
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 169 and b == 254:
        return True
    return False


def _is_virtual_nic(name):
    """判断网卡是否为虚拟/伪网卡（应排除，不对外提供访问网址）。

    覆盖常见虚拟网卡命名：VPN、WSL、Docker、Hyper-V、VMware、
    VirtualBox、Loopback Pseudo-Interface、Bluetooth 等。
    """
    if not name:
        return True
    n = name.lower()
    tokens = (
        "vpn", "wsl", "docker", "hyper-v", "hyperv", "vmware", "virtualbox",
        "vethernet", "loopback", "pseudo", "bluetooth", "bthpan", "tap-windows",
        "tun", "nordlynx", "zerotier", "openvpn", "ppp", "isatap", "teredo",
        "6to4", "tailscale", "wireguard",
    )
    return any(t in n for t in tokens)


def get_all_lan_ips():
    """返回本机所有真实网卡对应的局域网私有 IPv4 地址列表（多网卡场景）。

    只保留「已启用」的真实物理/桥接网卡上的私有地址（10.x / 172.16-31.x
    / 192.168.x / 169.254.x），**排除虚拟网卡**（VPN、WSL、Docker、
    Hyper-V 虚拟交换机等）与回环地址，避免登录地址里出现同网段设备
    无法访问的伪网址。顺序：优先出口网卡对应的私有 IP，其余按网卡枚举
    补充。无可用地址时返回空列表。
    """
    privates = []
    try:
        import psutil
        stats = psutil.net_if_stats()          # 网卡启用状态
        addrs = psutil.net_if_addrs()          # 网卡 -> 地址列表
        for nic, addr_list in addrs.items():
            # 跳过虚拟网卡与未启用的网卡
            if _is_virtual_nic(nic):
                continue
            st = stats.get(nic)
            if st is not None and not st.isup:
                continue
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if _is_private_ip(ip) and ip not in privates:
                        privates.append(ip)
    except Exception:
        privates = []
    # 优先把出口 IP（主网卡）排到最前
    primary = get_lan_ip()
    if primary and primary in privates:
        privates.remove(primary)
        privates.insert(0, primary)
    # 兜底：上面失败时用旧逻辑
    if not privates:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                cand = info[4][0]
                if _is_private_ip(cand) and cand not in privates:
                    privates.append(cand)
        except Exception:
            pass
    if not privates:
        p = get_lan_ip()
        if _is_private_ip(p):
            privates.append(p)
    return privates


def get_public_ipv4():
    """公网 IPv4，失败返回 None。"""
    with _cache_lock:
        if _cache["ext_v4"] is not None:
            return _cache["ext_v4"]
    try:
        data = _fetch_json(IPV4_URL)
        ip = data.get("ip") if not data.get("is_ipv6") else None
    except Exception:
        ip = None
    with _cache_lock:
        _cache["ext_v4"] = ip
    return ip


def get_public_ipv6():
    """公网 IPv6，无则返回 None。"""
    with _cache_lock:
        if _cache["ext_v6"] is not None:
            return _cache["ext_v6"]
    try:
        data = _fetch_json(IPV6_URL)
        ip = data.get("ip") if data.get("is_ipv6") else None
    except Exception:
        ip = None
    with _cache_lock:
        _cache["ext_v6"] = ip
    return ip


def get_cpu_percent(interval=0.3):
    """CPU 使用率百分比，失败返回 None。"""
    try:
        import psutil
        return psutil.cpu_percent(interval=interval)
    except Exception:
        return None


def get_memory_percent():
    """内存使用率百分比，失败返回 None。"""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return None


def get_memory_used_total():
    """内存 已用/总量（GB），返回 (used_gb, total_gb) 或 None。"""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.used / (1024 ** 3), vm.total / (1024 ** 3)
    except Exception:
        return None


def reset_cache():
    """服务重启或网络恢复后清空外网缓存，强制重新获取。"""
    with _cache_lock:
        _cache["ext_v4"] = None
        _cache["ext_v6"] = None
