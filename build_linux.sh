#!/usr/bin/env bash
# ============================================================
#  乾明工作台账系统 — Linux 打包脚本
#  产出：QmWorkLog_<ver>_amd64.deb
#
#  前置依赖（Debian/Ubuntu）：
#    sudo apt install python3 python3-venv python3-pip dpkg fakeroot
#    python3 -m venv QmWorkLog-venv && source QmWorkLog-venv/bin/activate
#    pip install -r requirements.txt pyinstaller
#
#  用法：  bash build_linux.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---------- 读取版本号 ----------
QM_VER="$(python3 -c "import json;print(json.load(open('version.json',encoding='utf-8'))['version'])")"
PKG_NAME="qmworklog"
PKG_VER="${QM_VER}"
ARCH="amd64"
DEB="QmWorkLog_${QM_VER}_${ARCH}.deb"

echo "当前版本： ${QM_VER}"

if [ ! -d "QmWorkLog-venv" ]; then
    echo "[错误] 未找到虚拟环境 QmWorkLog-venv，请先创建并安装依赖。"
    exit 1
fi
# shellcheck disable=SC1091
source QmWorkLog-venv/bin/activate

# ---------- 第一步：PyInstaller 打主程序 ----------
echo "[1/3] 正在打包主程序 QmWorkLog ..."
rm -rf dist/QmWorkLog
pyinstaller --noconfirm --onefile --windowed \
    --name QmWorkLog \
    --add-data "static:static" \
    --add-data "templates:templates" \
    --add-data "version.json:." \
    --hidden-import app --hidden-import db --hidden-import config \
    --hidden-import docx_utils --hidden-import system_info \
    main.py
if [ ! -f "dist/QmWorkLog" ]; then
    echo "[错误] 主程序打包失败。"
    exit 1
fi
chmod +x "dist/QmWorkLog"

# ---------- 第二步：组装 .deb 目录树 ----------
echo "[2/3] 正在组装 .deb 目录树 ..."
BUILD_ROOT="build/deb"
rm -rf "$BUILD_ROOT"
OPT_DIR="$BUILD_ROOT/opt/qmworklog"
mkdir -p "$OPT_DIR" \
         "$BUILD_ROOT/usr/share/applications" \
         "$BUILD_ROOT/usr/bin"

cp "dist/QmWorkLog" "$OPT_DIR/QmWorkLog"
cp -r static templates "$OPT_DIR/" 2>/dev/null || true
cp version.json "$OPT_DIR/" 2>/dev/null || true

# 桌面入口 .desktop
cat > "$BUILD_ROOT/usr/share/applications/qmworklog.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=乾明工作台账系统
Exec=/opt/qmworklog/QmWorkLog
Path=/opt/qmworklog
Terminal=false
Categories=Office;Utility;
EOF

# 命令行启动器 /usr/bin/qmworklog
cat > "$BUILD_ROOT/usr/bin/qmworklog" <<'EOF'
#!/bin/bash
exec /opt/qmworklog/QmWorkLog "$@"
EOF
chmod +x "$BUILD_ROOT/usr/bin/qmworklog"

# 卸载脚本
cat > "$OPT_DIR/uninstall.sh" <<'EOF'
#!/bin/bash
# 卸载乾明工作台账系统
set -e
rm -f /usr/bin/qmworklog
rm -f /usr/share/applications/qmworklog.desktop
rm -rf /opt/qmworklog
echo "已卸载乾明工作台账系统（用户数据 /opt/qmworklog/Data 等请手动确认是否保留）。"
EOF
chmod +x "$OPT_DIR/uninstall.sh"

# 控制信息
mkdir -p "$BUILD_ROOT/DEBIAN"
SIZE_KB=$(du -sk "$OPT_DIR" | cut -f1)
cat > "$BUILD_ROOT/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $PKG_VER
Section: office
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE_KB
Maintainer: QmWorkLog <djrolin2023@github>
Description: 乾明工作台账系统
 基于 Flask + PyQt5 的单机工作台账管理桌面应用，
 提供台账录入、导入导出、统计大屏与系统日志等功能。
EOF

cat > "$BUILD_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
exit 0
EOF
chmod +x "$BUILD_ROOT/DEBIAN/postinst"

# ---------- 第三步：构建 .deb ----------
echo "[3/3] 正在构建 $DEB ..."
rm -f "$DEB"
fakeroot dpkg-deb --build "$BUILD_ROOT" "$DEB"

echo
echo "打包完成： $(pwd)/$DEB"
echo "安装： sudo dpkg -i $DEB   卸载： sudo /opt/qmworklog/uninstall.sh"
