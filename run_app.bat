@echo off
:: 切换到当前脚本所在的目录
cd /d %~dp0

echo --- 正在启动 StockHunter 看板 ---
echo.

:: 检查是否安装了 streamlit
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未检测到 streamlit，请先运行 pip install streamlit
    pause
    exit
)

:: 启动 Web App
REM 可指定启动端口，示例 streamlit run app.py --server.port 8802
streamlit run app.py

pause
