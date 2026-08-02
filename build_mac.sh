#!/usr/bin/env bash
# ============================================================
#  乾明工作台账系统 — macOS 打包脚本
#  产出：QmWorkLog-<ver>.dmg（内含 QmWorkLog.app）
#
#  前置依赖（需 macOS 本机执行，PyInstaller 不能跨平台）：
#    brew install python3
#    python3 -m venv QmWorkLog-venv && source QmWorkLog-venv/bin/activate
#    pip install -r requirements.txt pyinstaller
#
#  用法：  bash build_mac.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---------- 读取版本号 ----------
QM_VER="$(python3 -c "import json;print(json.load(open('version.json',encoding='utf-8'))['version'])")"
APP_NAME="QmWorkLog"
DMG="QmWorkLog-${QM_VER}.dmg"

echo "当前版本： ${QM_VER}"

if [ ! -d "QmWorkLog-venv" ]; then
    echo "[错误] 未找到虚拟环境 QmWorkLog-venv，请先创建并安装依赖。"
    exit 1
fi
# shellcheck disable=SC1091
source QmWorkLog-venv/bin/activate

# ---------- 第一步：PyInstaller 打 .app ----------
echo "[1/3] 正在打包 $APP_NAME.app ..."
rm -rf "dist/$APP_NAME.app"
pyinstaller --noconfirm --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "com.qmworklog.app" \
    --add-data "static:static" \
    --add-data "templates:templates" \
    --add-data "version.json:." \
    --hidden-import app --hidden-import db --hidden-import config \
    --hidden-import docx_utils --hidden-import system_info \
    main.py
if [ ! -d "dist/$APP_NAME.app" ]; then
    echo "[错误] 主程序打包失败。"
    exit 1
fi

APP_BUNDLE="dist/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"

# 确保资源目录存在并补齐（PyInstaller 已处理，这里仅稳妥）
mkdir -p "$RESOURCES_DIR"
[ -d "static" ] && cp -R static "$RESOURCES_DIR/" 2>/dev/null || true
[ -d "templates" ] && cp -R templates "$RESOURCES_DIR/" 2>/dev/null || true
cp version.json "$RESOURCES_DIR/" 2>/dev/null || true

# 补全 Info.plist 基础字段（名称/版本/类别）
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$CONTENTS/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 乾明工作台账系统" "$CONTENTS/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $QM_VER" "$CONTENTS/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleGetInfoString 乾明工作台账系统 $QM_VER" "$CONTENTS/Info.plist" 2>/dev/null || true

# ---------- 第二步：组装 .dmg 暂存目录 ----------
echo "[2/3] 正在组装 .dmg 内容 ..."
DMG_STAGE="build/dmg_stage"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "$APP_BUNDLE" "$DMG_STAGE/"

# 生成 Applications 软链，用户拖拽即可安装
ln -s /Applications "$DMG_STAGE/Applications"

# 可选：给 .app 加可执行权限
chmod +x "$MACOS_DIR/$APP_NAME" 2>/dev/null || true

# ---------- 第三步：构建 .dmg ----------
echo "[3/3] 正在构建 $DMG ..."
rm -f "$DMG"
# 计算所需大小（内容 2 倍 + 余量）
SIZE_MB=$(( ( $(du -sm "$DMG_STAGE" | cut -f1) * 2 ) + 20 ))
hdiutil create -srcfolder "$DMG_STAGE" -volname "QmWorkLog $QM_VER" \
    -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDZO -size "${SIZE_MB}m" \
    "tmp_$DMG" 2>/dev/null || \
hdiutil create -srcfolder "$DMG_STAGE" -volname "QmWorkLog $QM_VER" \
    -format UDZO -o "tmp_$DMG"
mv "tmp_$DMG" "$DMG"

echo
echo "打包完成： $(pwd)/$DMG"
echo "安装： 打开 .dmg，将 QmWorkLog.app 拖入 Applications。"
