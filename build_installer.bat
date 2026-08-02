@echo off
chcp 65001 >nul
REM ============================================================
REM  乾明工作台账系统 打包脚本
REM  1) 用 PyInstaller 把 main.py 打成单文件主程序 QmWorkLog.exe
REM  2) 把主程序 exe 作为二进制嵌入 installer.py，生成带内置向导的
REM     QmWorkLog_Setup.exe（许可协议 + 默认路径 D:\QmWorkLog + 快捷方式）
REM  产物均输出到项目根目录（按规范不放入 dist 子目录）。
REM ============================================================

setlocal
cd /d %~dp0

if not exist "QmWorkLog-venv\Scripts\activate.bat" (
    echo [错误] 未找到虚拟环境 QmWorkLog-venv，请先创建。
    pause
    exit /b 1
)
call QmWorkLog-venv\Scripts\activate.bat

REM ---------- 读取版本号（来自 version.json） ----------
for /f "delims=" %%i in ('python -c "import json;print(json.load(open('version.json',encoding='utf-8'))['version'])"') do set QM_VER=%%i
if "%QM_VER%"=="" (
    echo [错误] 无法从 version.json 读取版本号。
    pause
    exit /b 1
)
set QM_MAIN=QmWorkLog_v%QM_VER%
set QM_SETUP=QmWorkLog_Setup_v%QM_VER%
echo 当前版本： %QM_VER%

REM ---------- 第一步：主程序 exe ----------
echo [1/2] 正在打包主程序 %QM_MAIN%.exe ...
pyinstaller --noconfirm --onefile --windowed ^
    --name %QM_MAIN% ^
    --icon "static\Images\logo.ico" ^
    --add-data "static;static" ^
    --add-data "templates;templates" ^
    --add-data "version.json;." ^
    --hidden-import app --hidden-import db --hidden-import config ^
    --hidden-import docx_utils --hidden-import system_info ^
    main.py
if errorlevel 1 (
    echo [错误] 主程序打包失败。
    pause
    exit /b 1
)

REM 主程序 exe 移到根目录
if exist "%QM_MAIN%.exe" del /f /q "%QM_MAIN%.exe"
move /y "dist\%QM_MAIN%.exe" "%QM_MAIN%.exe" >nul

REM ---------- 第二步：安装向导 exe（内嵌上面带版本号的主程序） ----------
echo [2/2] 正在打包安装向导 %QM_SETUP%.exe ...
pyinstaller --noconfirm --onefile --windowed ^
    --name %QM_SETUP% ^
    --icon "static\Images\logo.ico" ^
    --add-data "LICENSE_INSTALL.txt;." ^
    --add-binary "%QM_MAIN%.exe;." ^
    --hidden-import PyQt5.QtWidgets --hidden-import PyQt5.QtCore --hidden-import PyQt5.QtGui ^
    installer.py
if errorlevel 1 (
    echo [错误] 安装向导打包失败。
    pause
    exit /b 1
)

REM 安装向导 exe 移到根目录
if exist "%QM_SETUP%.exe" del /f /q "%QM_SETUP%.exe"
move /y "dist\%QM_SETUP%.exe" "%QM_SETUP%.exe" >nul

echo.
echo 打包完成：
echo   主程序： %cd%\%QM_MAIN%.exe
echo   安装包： %cd%\%QM_SETUP%.exe
echo.
pause
endlocal
