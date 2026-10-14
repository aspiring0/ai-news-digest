@echo off
rem AI 资讯聚合 · 一键启动脚本（Windows）
rem 用法：双击 start.bat，或在 cmd 里运行 start.bat
rem 做了什么：检查 Python 3.11+ → 创建/复用 .venv → 安装依赖 → 启动服务
setlocal enabledelayedexpansion
cd /d %~dp0

echo === AI 资讯聚合 · 启动 ===

rem ---------- 1. 检查 Python ----------
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
) else (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PY=python"
    ) else (
        echo 错误：未找到 Python，请先到 https://www.python.org/downloads/ 安装 Python 3.11 或更高版本。
        echo 注意：安装时务必勾选 "Add python.exe to PATH"。
        pause
        exit /b 1
    )
)
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo 错误：Python 版本过低，需要 3.11 或更高版本，请升级后再试。
    pause
    exit /b 1
)
echo [1/5] Python 版本检查通过

rem ---------- 2. 加载 .env（可选） ----------
if exist .env (
    echo [2/5] 加载 .env 配置
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
) else (
    echo [2/5] 未找到 .env，使用默认配置（端口 8000、数据目录 .\data、抓取间隔 4 小时）
    echo       如需修改：copy .env.example .env 后编辑
)
if not defined PORT set "PORT=8000"
if not defined HOST set "HOST=127.0.0.1"
rem DATA_DIR 是给人看的目录；程序实际读 DB_PATH，这里做一次映射（DB_PATH 显式设置时优先）
if not defined DB_PATH (
    if defined DATA_DIR set "DB_PATH=!DATA_DIR!\news.db"
)
if not defined DATA_DIR set "DATA_DIR=.\data"
if not defined FETCH_INTERVAL_HOURS set "FETCH_INTERVAL_HOURS=4"

rem ---------- 3. 配置校验（非法配置直接报错退出，不静默带病运行） ----------
echo %PORT%| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 goto :bad_port
if %PORT% GTR 65535 goto :bad_port
goto :port_ok
:bad_port
echo 错误：PORT='%PORT%' 非法，端口必须是 1-65535 的数字。请检查 .env。
pause
exit /b 1
:port_ok

echo %FETCH_INTERVAL_HOURS%| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 (
    echo 错误：FETCH_INTERVAL_HOURS='%FETCH_INTERVAL_HOURS%' 非法，必须是 ≥1 的整数（小时）。请检查 .env。
    pause
    exit /b 1
)

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%" 2>nul
if errorlevel 1 (
    echo 错误：数据目录 '%DATA_DIR%' 无法创建。请检查 .env 的 DATA_DIR。
    pause
    exit /b 1
)
echo test > "%DATA_DIR%\.write_test" 2>nul
if errorlevel 1 (
    echo 错误：数据目录 '%DATA_DIR%' 不可写。请检查目录权限或换 DATA_DIR。
    pause
    exit /b 1
)
del "%DATA_DIR%\.write_test" 2>nul
echo [3/5] 配置校验通过（监听 %HOST%:%PORT%、数据目录 %DATA_DIR%、抓取间隔 %FETCH_INTERVAL_HOURS%h）

rem ---------- 4. 虚拟环境 + 依赖 ----------
if not exist .venv (
    echo [4/5] 创建虚拟环境 .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo 错误：虚拟环境创建失败。
        pause
        exit /b 1
    )
) else (
    echo [4/5] 复用已有虚拟环境 .venv
)

echo       安装/更新依赖（requirements.txt 有变化时会自动重装）...
.venv\Scripts\pip install -q -r requirements.txt
if errorlevel 1 (
    echo 错误：依赖安装失败，请检查网络连接后重试。
    pause
    exit /b 1
)

rem ---------- 4. 启动 ----------
echo [5/5] 启动服务 ...
echo.
echo   热榜：  http://localhost:%PORT%/hot
echo   时间线：http://localhost:%PORT%/timeline
echo   设置：  http://localhost:%PORT%/settings  （摘要功能需先在这里填模型 key）
echo.
echo   关闭此窗口即停止服务。数据保存在 .\data\news.db，备份拷走就行。
echo.
.venv\Scripts\python -m uvicorn app.main:app --host %HOST% --port %PORT%
