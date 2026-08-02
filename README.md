# 乾明工作台账系统 (QmWorkLog)

一个面向企事业单位的本地化工作台账管理系统，支持台账录入、图片留痕、智能总结、数据可视化大屏、归档备份与导入导出。所有数据均保存在本地，**不上云**，保障数据安全。

> 开源协议：[GNU GPL v3.0](LICENSE)
> 项目仓库：https://github.com/djrolin2023/QmWorkLog

---

## 功能特性

- **工作台账录入**：按类型 + 日期组织工作记录，支持多图上传与现场照片留痕。
- **台账管理**：自定义台账类型（安保巡查、设备维护、消防演练等）。
- **智能总结**：基于台账内容自动生成周期总结（年度 / 月度 / 自定义）。
- **数据大屏**：可视化呈现台账占比、类型分布与月度趋势。
- **归档管理**：历史台账一键归档、下载与恢复，数据不丢失。
- **导入导出**：整库备份、按年 / 类型导出，支持恢复。
- **用户与权限**：管理员 / 普通用户两级角色。
- **系统设置**：维护公司名称、LOGO 等品牌信息。
- **桌面控制台**：PyQt5 托盘程序，内置 CPU / 内存 / 磁盘占用环图、实时网络流量、运行时长、进程 PID、当前登录账号与时钟。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + Flask |
| 前端 | 原生 HTML / CSS / JavaScript（SPA 单页结构） |
| 桌面端 | PyQt5 系统托盘控制台 |
| 文档 | python-docx（Word 模板 / 导出） |
| 图像处理 | Pillow |
| 系统监控 | psutil |

---

## 环境要求

- Python ≥ 3.10（开发与运行环境使用 3.12）
- Windows（桌面控制台基于 PyQt5，托盘程序针对 Windows 优化）

---

## 安装

推荐使用虚拟环境（依赖统一安装在 `F:\Python\venv\QmWorkLog-venv`）：

```bash
# 1. 获取代码
git clone https://github.com/djrolin2023/QmWorkLog.git
cd QmWorkLog

# 2. 创建虚拟环境（可选但推荐）
python -m venv venv
.\venv\Scripts\activate        # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

---

## 运行

### 方式一：桌面控制台（推荐）

双击启动或运行：

```bash
python main.py
```

启动后：
- 自动拉起 Flask Web 服务（默认端口 **8088**）；
- 系统托盘显示控制台，可查看监控指标、启动 / 停止 / 重启服务；
- 浏览器访问 `http://<本机IP>:8088` 使用系统；
- 关闭窗口仅最小化到托盘，程序继续运行；完全退出请右键托盘「退出程序」。

### 方式二：直接运行 Web 服务

```bash
python app.py
```

然后浏览器访问 `http://127.0.0.1:8088`。

---

## 打包与分发

> PyInstaller **不能跨平台打包**：在哪个系统上运行，就只能打出该平台的包。跨平台安装逻辑已抽象在 `install_utils.py`（快捷方式 / 启动入口按 Windows / macOS / Linux 分支处理）。

### Windows（.exe 主程序）

在已激活的虚拟环境中执行：

```bat
pyinstaller --noconfirm --onefile --windowed ^
    --name QmWorkLog_v%QM_VER% ^
    --icon "static\Images\logo.ico" ^
    --add-data "static;static" ^
    --add-data "templates;templates" ^
    --add-data "version.json;." ^
    --hidden-import app --hidden-import db --hidden-import config ^
    --hidden-import docx_utils --hidden-import system_info ^
    main.py
```

产物 `QmWorkLog_v<ver>.exe`（自动带版本号）即程序本体，老用户直接覆盖即可。
> 说明：本项目不再提供内置安装向导（`QmWorkLog_Setup*.exe`），跨平台分发请使用下方的 `.deb` / `.dmg`。

### Linux（.deb）

在 Debian/Ubuntu 本机执行：

```bash
sudo apt install python3-venv python3-pip dpkg fakeroot
python3 -m venv QmWorkLog-venv && source QmWorkLog-venv/bin/activate
pip install -r requirements.txt pyinstaller
bash build_linux.sh
```

产出 `QmWorkLog_<ver>_amd64.deb`：

```bash
sudo dpkg -i QmWorkLog_<ver>_amd64.deb      # 安装
sudo /opt/qmworklog/uninstall.sh            # 卸载
```

### macOS（.dmg）

在 macOS 本机执行：

```bash
brew install python3
python3 -m venv QmWorkLog-venv && source QmWorkLog-venv/bin/activate
pip install -r requirements.txt pyinstaller
bash build_mac.sh
```

产出 `QmWorkLog-<ver>.dmg`，打开后将 `QmWorkLog.app` 拖入「应用程序」即可。

> 注：Linux 默认安装目录 `~/.local/QmWorkLog`、macOS 为 `~/Applications/QmWorkLog`（GUI 向导默认路径见 `install_utils.default_install_dir`）。

---

## 默认账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | admin | admin |

> ⚠ **首次使用请务必修改管理员密码**（左侧「用户管理」→ 重置密码）。

---

## 数据说明与更新保护

系统所有数据保存在本地目录，**更新程序时不会改动任何用户数据**：

| 目录 / 文件 | 内容 | 更新时是否保留 |
|---|---|---|
| `DB/` | SQLite 数据库（台账、用户、日志） | ✅ 始终保留 |
| `Data/` | 台账 Word 文档（`*.docx`） | ✅ 始终保留 |
| `users.json` | 账号信息 | ✅ 始终保留 |
| `config.json` | 系统配置 | ✅ 始终保留 |
| `Backup/` | 备份文件 | ✅ 始终保留 |
| `static/`、`templates/`、`*.py` | 程序代码 | 🔄 更新覆盖 |

**更新方式**：从 [GitHub Releases](https://github.com/djrolin2023/QmWorkLog) 下载最新版本，仅覆盖代码与静态资源文件即可，**切勿删除** `DB/`、`Data/`、`users.json`、`config.json` 等数据目录。重要变更前建议先通过「导入导出」执行整库备份。

---

## 项目结构

```
QmWorkLog/
├── app.py              # Flask 后端主程序
├── main.py             # PyQt5 桌面控制台
├── flask_host.py       # Web 服务宿主（子进程管理）
├── system_info.py      # 系统 / 网络信息
├── db.py / config.py   # 数据库与配置
├── docx_utils.py       # Word 文档工具
├── templates/          # 页面模板（SPA）
├── static/             # 样式、脚本、图片
├── DB/                 # 数据库（数据）
├── Data/               # 台账文档（数据）
├── Backup/             # 备份（数据）
├── requirements.txt
└── LICENSE
```

---

## 开源许可

本项目基于 **GNU GPL v3.0** 开源。您可以自由使用、修改与分发，但衍生作品必须以相同的 GPL v3 协议开源。详见 [LICENSE](LICENSE)。

---

## 反馈与更新

- 仓库地址：https://github.com/djrolin2023/QmWorkLog
- 后续版本更新均通过该仓库发布，下载更新请前往上述地址。
