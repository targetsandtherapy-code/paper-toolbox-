@echo off
chcp 65001 >nul
title 论文工具箱 - 本地服务器
echo.
echo ========================================
echo   论文工具箱 - 启动中...
echo ========================================
echo.

cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
if not exist "venv" (
    echo [首次运行] 创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [安装依赖] 请稍候...
    pip install -r requirements.txt -q
) else (
    call venv\Scripts\activate.bat
)

:: 启动 Streamlit
echo.
echo [启动] 正在打开浏览器...
echo [提示] 关闭此窗口即可停止服务
echo.
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
pause
