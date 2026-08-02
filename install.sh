#!/usr/bin/env bash
# ============================================================
#  乾明工作台账系统 — Linux 一键安装脚本
#  用法（任选其一）：
#    bash install.sh                # 从当前目录安装（已下载代码时）
#    curl -fsSL <raw_url> | bash    # 从 GitHub 拉取并安装
#
#  行为：
#    1) 克隆/更新仓库到 ~/QmWorkLog
#    2) 创建虚拟环境 QmWorkLog-venv 并安装依赖
#    3) 生成 /usr/local/bin/qmworklog 启动器（需 sudo）
#    4) 生成 ~/.local/share/applications/qmworklog.desktop 桌面入口
#    5) 提示启动方式
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/djrolin2023/QmWorkLog"
INSTALL_DIR="$HOME/QmWorkLog"
VENV="$INSTALL_DIR/QmWorkLog-venv"

echo "===== 乾明工作台账系统 安装开始 ====="

# ---------- 1) 获取代码 ----------
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[1/4] 检测到已存在的仓库，执行 git pull 更新 ..."
    cd "$INSTALL_DIR"
    git pull --ff-only || echo "（更新失败，将使用本地现有代码继续）"
elif [ -f "$(dirname "$0")/main.py" ]; then
    # 用户直接对下载好的目录运行本脚本
    INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
    echo "[1/4] 使用当前目录作为安装源： $INSTALL_DIR"
    cd "$INSTALL_DIR"
else
    echo "[1/4] 克隆仓库到 $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ---------- 2) 虚拟环境与依赖 ----------
echo "[2/4] 创建虚拟环境并安装依赖 ..."
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# ---------- 3) 系统级启动器（可选，需要 sudo） ----------
echo "[3/4] 创建启动器 /usr/local/bin/qmworklog ..."
LAUNCHER='/usr/local/bin/qmworklog'
if [ -w "$(dirname "$LAUNCHER")" ] || sudo -n true 2>/dev/null; then
    cat > "$LAUNCHER" <<EOF
#!/bin/bash
# 乾明工作台账系统 启动器
source "$VENV/bin/activate"
cd "$INSTALL_DIR"
exec python main.py "\$@"
EOF
    sudo chmod +x "$LAUNCHER" 2>/dev/null || chmod +x "$LAUNCHER" 2>/dev/null || true
    echo "  已创建 $LAUNCHER （终端输入 qmworklog 即可启动）"
else
    echo "  无写入 /usr/local/bin 权限，跳过系统启动器（可直接用下面的方式启动）"
fi

# ---------- 4) 桌面入口（当前用户） ----------
echo "[4/4] 创建桌面入口 ..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/qmworklog.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=乾明工作台账系统
Comment=QmWorkLog 工作台账管理
Exec=$VENV/bin/python $INSTALL_DIR/main.py
Path=$INSTALL_DIR
Icon=$INSTALL_DIR/static/Images/logo.ico
Terminal=false
Categories=Office;Utility;
EOF
chmod +x "$DESKTOP_DIR/qmworklog.desktop"

echo
echo "===== 安装完成 ====="
echo "启动方式（任选其一）："
if [ -x "$LAUNCHER" ]; then
    echo "  终端输入： qmworklog"
fi
echo "  应用菜单搜索： 乾明工作台账系统"
echo "  或手动运行： cd $INSTALL_DIR && source $VENV/bin/activate && python main.py"
echo
echo "注意：首次启动需在图形界面环境下运行（本程序为 PyQt5 桌面应用）。"
