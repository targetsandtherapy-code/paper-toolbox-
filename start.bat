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

:: 检查 streamlit 是否安装
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [安装依赖] 请稍候...
    pip install -r requirements.txt -q
)

:: 清除旧缓存
if exist "__pycache__" rd /s /q "__pycache__" 2>nul
if exist "modules\__pycache__" rd /s /q "modules\__pycache__" 2>nul
if exist "modules\reference\__pycache__" rd /s /q "modules\reference\__pycache__" 2>nul

:: 启动 Streamlit
echo.
echo [启动] 正在打开浏览器 http://localhost:8501
echo [提示] 关闭此窗口即可停止服务
echo.
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
pause
