# 🏹 StockHunter-AI - A股智能投资助手

StockHunter-AI 是一个基于 Python 的本地化 A 股分析工具。它结合了传统技术指标（均线、MACD、KDJ、RSI）与大语言模型（LLM）的推理能力，为你提供智能化的短线交易建议。

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B)

## ✨ 主要功能

- **🚀 全自动数据管线**：基于 `Baostock` 接口，获取全市场 5000+ 只A股股票的日线数据，自动清洗并存入本地数据库。
- **📊 多维度量化筛选**：
  - **形态识别**：自动判断均线多头、空头及纠缠形态。
  - **经典指标**：内置 MACD、KDJ、RSI、OBV 等核心指标计算。
  - **关键点位**：自动测算支撑位、压力位及年线乖离率，辅助买卖决策。
- **🤖 AI 投资顾问**：
  - **多模型支持**：支持 DeepSeek、GPT-4、Gemini 等主流大语言模型。
  - **双重诊断**：对量化筛选后的股票进行“技术面数据 + 市场情绪”的双重深度分析。
  - **结构化建议**：输出清晰的自然语言投资报告，给出明确的（推荐/观望/谨慎）评级。
- **📈 交互式仪表盘**：
  - 基于 Streamlit 构建的现代化 Web 界面。
  - 支持交互式 K 线图（缩放/平移/十字光标）。
  - 便捷的自选股管理及历史回测报告查看功能。

## 🛠️ 安装指南

1.  **克隆项目**
    ```bash
    git clone https://github.com/fanka5/StockHunter-cn.git
    cd StockHunter-cn
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置环境**
    1.  在项目根目录下，将 `.env.example` 文件复制一份，并重命名为 `.env`。
    2.  打开 `.env` 文件，填入你的 API Key：
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
4.  之后日常使用，建议添加自选股后，使用 **"⚡ 仅自选股 (极速)"** 模式，仅更新关注的自选股票。

## 📂 项目结构

```text
StockHunter-cn/
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

本项目仅供技术研究和学习使用，生成的任何投资建议仅供参考，对建议可靠性不做任何保证。股市有风险，入市需谨慎。