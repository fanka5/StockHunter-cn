# 🏹 StockHunter AI - A股智能投资助手

StockHunter AI 是一个基于 Python 的本地化 A 股分析工具。它结合了传统技术指标（均线、MACD、KDJ、RSI）与大语言模型（LLM）的推理能力，为你提供智能化的短线交易建议。

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B)

## ✨ 主要功能

*   **📊 交互式 K 线图**：支持平移、滚轮缩放、十字光标查看，体验接近专业行情软件。
*   **⚡ 极速模式 (新)**：日常只需更新自选股数据，几秒钟完成同步与分析，无需等待全市场下载。
*   **🤖 AI 投资顾问**：自动识别形态（如多头排列、金叉），结合 LLM 生成通俗易懂的操作建议。
*   **📈 全方位回测**：支持历史数据回测（T+N 收益率统计），验证策略有效性。
*   **🛡️ 隐私安全**：数据存储在本地 CSV，仅将脱敏后的技术指标发送给 LLM 进行分析。

## 🛠️ 安装指南

1.  **克隆项目**
    ```bash
    git clone https://github.com/your-username/StockHunter-AI.git
    cd StockHunter-AI
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置环境**
    1.  在项目根目录下，将 `.env.example` 文件复制一份，并重命名为 `.env`。
    2.  打开 `.env` 文件，填入你的API Key：
        ```properties
        LLM_API_KEY=你的_API_KEY_在这里
        ```
    3. 如果需要修改模型或代理，也在 `.env` 中修改对应变量。


## 🚀 快速开始

### 启动应用
在终端中运行：
```bash
streamlit run app.py
```
*(Windows 用户也可以直接双击 `run_app.bat` 启动)*

### ⚠️ 首次使用必读
1.  启动后，请在左侧侧边栏点击 **"💾 数据同步"** -> 选择 **"🔄 全市场 (全量)"**。
2.  点击 **"📥 开始同步数据"**。
3.  **注意**：首次运行必须进行一次全量下载（约 5000 只股票），以建立本地数据库。这可能需几分钟到十几分钟时间。
4.  之后日常使用，建议添加自选股后，使用 **"⚡ 仅自选股 (极速)"** 模式，秒级更新。

## 📂 项目结构

```text
StockHunter-AI/
├── src/
│   ├── downloader.py    # 数据下载引擎 (Baostock)
│   ├── data_analyzer.py # 技术指标计算 (Pandas-TA)
│   └── llm_agent.py     # AI 智能分析代理
├── data/                # 本地数据存储 (建议加入 .gitignore)
├── app.py               # Streamlit 主程序
├── config.py            # 配置文件 (请勿上传到 GitHub)
├── requirements.txt     # 依赖列表
└── README.md            # 说明文档
```

## 📝 免责声明

本项目仅供技术研究和学习使用，生成的任何投资建议仅供参考。股市有风险，入市需谨慎。

---