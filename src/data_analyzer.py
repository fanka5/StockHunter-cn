import pandas as pd
import pandas_ta as ta
import os
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Set, Tuple

# 引入配置
from config import DATA_DIR, WATCHLIST_FILE, PROCESS_COUNT


class TechnicalAnalyzer:
    """
    负责计算全方位技术指标并筛选股票
    """

    def __init__(self, mode: str = "current", scope: str = "all", backtest_date: Optional[str] = None):
        """
        初始化分析器
        :param mode: "current" (最新) 或 "backtest" (回测)
        :param scope: "all" (全市场) 或 "watchlist_only" (仅自选)
        :param backtest_date: 回测基准日期 (YYYY-MM-DD)，仅在 backtest 模式下有效
        """
        self.mode = mode
        self.scope = scope
        self.backtest_date = backtest_date
        self.watchlist = self._load_watchlist()

    def _load_watchlist(self) -> Set[str]:
        """加载自选股列表"""
        if os.path.exists(WATCHLIST_FILE):
            try:
                with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return set(data)
            except Exception:
                return set()
        return set()

    def _get_ma_state(self, close: float, ma5: float, ma20: float, ma60: float) -> str:
        """判断均线形态"""
        if pd.isna(ma60): return "数据不足"
        if ma5 > ma20 > ma60: return "多头排列"
        if ma5 < ma20 < ma60: return "空头排列"
        if close > ma60 and ma5 > ma20: return "反弹趋势"
        return "震荡整理"

    def _process_one_stock(self, args: Tuple) -> Optional[Dict[str, Any]]:
        """
        单只股票处理逻辑 - 核心分析算法
        """
        file_path, watchlist_set, mode, scope, bt_date = args

        try:
            # 读取数据
            df = pd.read_csv(file_path)
            if len(df) < 60: return None

            # 解析文件名获取代码
            file_name = os.path.basename(file_path)
            code = file_name.split('_')[0]
            # 处理部分文件名可能不规范的情况
            name_part = file_name.split('_')[1] if '_' in file_name else "未知"
            name = name_part.replace('.csv', '')

            is_vip = code in watchlist_set

            # 范围筛选
            if scope == "watchlist_only" and not is_vip:
                return None

            # 1. 数据预处理与指标计算
            df['date'] = pd.to_datetime(df['date'])

            # 均线
            df['MA5'] = ta.sma(df['close'], length=5)
            df['MA20'] = ta.sma(df['close'], length=20)
            df['MA60'] = ta.sma(df['close'], length=60)
            df['MA250'] = ta.sma(df['close'], length=250)

            # MACD
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            # 处理 pandas_ta 返回列名可能不一致的问题 (兼容性处理)
            if macd is not None:
                df['DIF'] = macd.iloc[:, 0]
                df['DEA'] = macd.iloc[:, 1]
                # df['MACD_Hist'] = macd.iloc[:, 2]
            else:
                return None

            # KDJ
            kdj = ta.kdj(df['high'], df['low'], df['close'])
            if kdj is not None:
                df = pd.concat([df, kdj], axis=1)

            # RSI & 量能
            df['RSI'] = ta.rsi(df['close'], length=14)
            df['VOL_MA5'] = ta.sma(df['volume'], length=5)

            # 2. 确定分析的时间切片索引
            idx = -1
            if mode == "backtest" and bt_date:
                target_dt = pd.to_datetime(bt_date)
                past_data = df[df['date'] <= target_dt]
                if past_data.empty: return None
                idx = past_data.index[-1]
                if idx < 60: return None
            else:
                idx = df.index[-1]

            curr = df.iloc[idx]
            prev = df.iloc[idx - 1]

            # 3. 特征提取 (Feature Engineering)

            # A. 均线状态
            ma_state = self._get_ma_state(curr['close'], curr['MA5'], curr['MA20'], curr['MA60'])

            # B. 年线状态
            year_line_dist = 0
            year_line_state = "无数据"
            if pd.notna(curr['MA250']):
                dist_pct = (curr['close'] - curr['MA250']) / curr['MA250'] * 100
                year_line_dist = round(dist_pct, 1)
                year_line_state = "站上年线" if curr['close'] > curr['MA250'] else "年线下方"

            # C. MACD 状态
            macd_state = "死叉"
            if curr['DIF'] > curr['DEA']:
                macd_state = "金叉"

            # D. KDJ 状态 (列名通常为 K_9_3, D_9_3)
            k_col, d_col = 'K_9_3', 'D_9_3'
            kdj_state = "死叉"
            if k_col in curr and d_col in curr:
                if curr[k_col] > curr[d_col]: kdj_state = "金叉"

            # E. 支撑与压力 (过去30天)
            start_idx = max(0, idx - 30)
            period_df = df.iloc[start_idx:idx + 1]
            high_30d = period_df['high'].max()  # 压力位绝对价格
            low_30d = period_df['low'].min()  # 支撑位绝对价格

            pressure_dist = round((high_30d - curr['close']) / curr['close'] * 100, 1)
            support_dist = round((curr['close'] - low_30d) / curr['close'] * 100, 1)

            # F. 量能状态
            vol_ratio = 0.0
            if pd.notna(curr['VOL_MA5']) and curr['VOL_MA5'] > 0:
                vol_ratio = round(curr['volume'] / curr['VOL_MA5'], 2)
            vol_state = "放量" if vol_ratio > 1.2 else "缩量"

            # 4. 策略筛选规则 (Strategy Filter)
            # 规则: 收盘价站上20日线 OR (MACD金叉 OR KDJ金叉)
            cond1 = curr['close'] > curr['MA20']
            cond2 = "金叉" in macd_state or "金叉" in kdj_state

            strategy_pass = (cond1 or cond2)

            # 如果不是自选股，且不满足策略，则直接过滤
            if not strategy_pass and not is_vip:
                return None

            # 生成匹配理由
            match_reason = []
            if cond1: match_reason.append("站上月线")
            if "金叉" in macd_state: match_reason.append("MACD金叉")
            if vol_ratio > 1.5: match_reason.append("放量")
            match_str = "+".join(match_reason) if match_reason else "自选观察"

            # 5. 组装结果数据
            buy_price = curr['close']
            recent_prices = df.iloc[idx - 4:idx + 1]['close'].tolist()
            trend_str = "->".join([str(round(p, 2)) for p in recent_prices])

            res = {
                '代码': code,
                '名称': name,
                '回测日期': curr['date'].strftime("%Y-%m-%d"),
                '买入价': buy_price,
                'RSI': round(curr['RSI'], 2) if pd.notna(curr['RSI']) else 0,
                '量比': vol_ratio,

                # --- 特征字段 (用于 UI 展示和 LLM 分析) ---
                '均线形态': ma_state,
                '年线状态': f"{year_line_state}({year_line_dist}%)",
                'MACD状态': macd_state,
                'KDJ状态': kdj_state,
                '量能状态': vol_state,

                # 绝对价格 (UI用)
                '压力位': round(high_30d, 2),
                '支撑位': round(low_30d, 2),
                # 相对比例 (LLM用)
                '压力位距': f"{pressure_dist}%",
                '支撑位距': f"{support_dist}%",

                '近5日走势': trend_str,
                '策略匹配': match_str,
                'is_watchlist': is_vip,
                'AI建议': '',
                'AI点评': ''
            }

            # 6. 计算历史回测收益 (仅 backtest 模式)
            if mode == "backtest":
                future_df = df.iloc[idx + 1:].reset_index(drop=True)
                res['T+5收益(%)'] = 0.0
                res['T+10收益(%)'] = 0.0
                res['T+30收益(%)'] = 0.0
                res['后市最高涨幅(%)'] = 0.0

                if len(future_df) > 0:
                    max_price = future_df['high'].head(30).max()
                    res['后市最高涨幅(%)'] = round((max_price - buy_price) / buy_price * 100, 2)

                    if len(future_df) >= 5:
                        res['T+5收益(%)'] = round((future_df.iloc[4]['close'] - buy_price) / buy_price * 100, 2)
                    if len(future_df) >= 10:
                        res['T+10收益(%)'] = round((future_df.iloc[9]['close'] - buy_price) / buy_price * 100, 2)
                    if len(future_df) >= 30:
                        res['T+30收益(%)'] = round((future_df.iloc[29]['close'] - buy_price) / buy_price * 100, 2)

            return res
        except Exception:
            # 生产环境建议记录日志，这里为了简洁静默失败
            # print(f"Error analyzing {file_path}: {e}")
            return None

    def run_analysis(self, max_workers: int = None) -> pd.DataFrame:
        """
        执行全量分析任务
        :param max_workers: 线程池大小，默认从 config 读取
        :return: 包含分析结果的 DataFrame
        """
        # 使用 str() 转换 Path 对象
        data_dir_str = str(DATA_DIR)

        if not os.path.exists(data_dir_str):
            print(f"❌ 数据目录不存在: {data_dir_str}")
            return pd.DataFrame()

        csv_files = [os.path.join(data_dir_str, f) for f in os.listdir(data_dir_str) if f.endswith(".csv")]

        # 准备任务参数
        tasks = [(f, self.watchlist, self.mode, self.scope, self.backtest_date) for f in csv_files]
        results = []

        # 使用线程池并发处理 (IO密集/混合型任务在 Windows 下线程池更稳定)
        workers = max_workers if max_workers else PROCESS_COUNT

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # map 会按顺序返回结果，但这里顺序不重要
            for res in executor.map(self._process_one_stock, tasks):
                if res:
                    results.append(res)

        if not results:
            return pd.DataFrame()

        return pd.DataFrame(results)
