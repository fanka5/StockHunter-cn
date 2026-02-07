import requests
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from typing import List, Dict, Any, Optional
import pandas as pd

# 引入配置
from config import LLM_API_KEY, LLM_API_URL, LLM_MODEL, AI_BATCH_SIZE, AI_MAX_THREADS


class LLMAgent:
    """
    AI 投资顾问代理
    负责与 LLM 交互，将技术分析数据转化为自然语言建议
    """

    def __init__(self):
        # 系统提示词：设定 AI 角色和输出规范
        self.system_prompt = """
        你是一名拥有20年实战经验的A股资深技术分析师。我将提供一组股票的详细技术面数据。
        我是股市新手，请根据数据预测短线走势，并用通俗易懂的语言为我讲解。我是一个短线玩家。

        【输入数据说明】
        - 均线/年线：判断大趋势（多头/空头/震荡）。年线(MA250)是牛熊分界线。
        - MACD/KDJ/RSI：判断短线买卖时机（金叉/死叉/背离/超买超卖）。
        - 压力位/支撑位距：判断上涨空间和止损位置。
        - 量能：验证趋势有效性（放量上涨/缩量回调）。

        【分析逻辑要求】
        1. **趋势第一**：优先关注“多头排列”且“站上年线”的股票。
        2. **指标共振**：如果MACD和KDJ同时金叉，且伴随放量，视为高胜率信号。
        3. **盈亏比**：如果当前价距“压力位”很近（<3%）且量能不足，应提示风险；如果距“支撑位”很近，可视为低吸机会。

        【输出格式要求】
        1. 必须以严格的 JSON 格式返回，不要包含 markdown 标记。
        2. 这是一个 JSON 列表，每个元素包含：
           - "code": 股票代码
           - "suggestion": 结论 (强烈推荐/推荐/观望/谨慎/不推荐)
           - "reason": 300字以内。
             结构建议：
             1. **形态定性**：(如"底部放量启动"或"高位缩量盘整")。
             2. **指标分析**：结合均线、MACD、KDJ状态解释为什么看涨/看跌。
             3. **操作建议**：给出明日以及中长线的操作指南。基于"压力位距"和"支撑位距"给出具体的参考点位。
        """

    def _extract_json(self, text: str) -> Optional[Any]:
        """
        从 LLM 返回的杂乱文本中提取 JSON
        增强兼容性：处理 Markdown 标记、前后废话等
        """
        try:
            # 1. 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        try:
            # 2. 清理 Markdown 标记
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        try:
            # 3. 正则提取最外层的列表或字典
            # 寻找第一个 [ 或 {
            match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
            if match:
                clean_text = match.group(1)
                return json.loads(clean_text)
        except Exception:
            pass

        return None

    def _call_batch(self, stock_data_list: List[Dict], max_retries: int = 3) -> List[Dict]:
        """
        发送单批次请求 (带重试机制)
        """
        if not stock_data_list: return []

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(stock_data_list, ensure_ascii=False)}
            ],
            "temperature": 0.3,
            # 移除 response_format，增强对不同模型厂商的兼容性
            # "response_format": {"type": "json_object"}
        }

        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }

        for attempt in range(max_retries):
            try:
                # 增加超时时间，大模型处理批量数据较慢
                response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=90)

                if response.status_code == 200:
                    try:
                        resp_json = response.json()
                        # 兼容 OpenAI 格式和部分非标准格式
                        if 'choices' in resp_json:
                            content = resp_json['choices'][0]['message']['content']
                        elif 'data' in resp_json:  # 某些第三方中转
                            content = resp_json['data']['choices'][0]['message']['content']
                        else:
                            print(f"❌ 无法识别的 API 响应格式: {resp_json.keys()}")
                            continue

                        # 提取 JSON
                        res = self._extract_json(content)
                        if res is None:
                            print(f"❌ JSON 解析失败 (Attempt {attempt + 1})")
                            continue

                        final_list = []
                        # 兼容不同格式返回 (列表 或 字典包裹列表)
                        if isinstance(res, list):
                            final_list = res
                        elif isinstance(res, dict):
                            # 尝试寻找字典里的列表字段
                            for k, v in res.items():
                                if isinstance(v, list):
                                    final_list = v
                                    break
                            # 如果字典本身就是单个结果（虽不符合 prompt 但可能发生）
                            if not final_list and 'code' in res:
                                final_list = [res]

                        # 验证数据有效性
                        if final_list:
                            # 简单检查必要字段
                            first_item = final_list[0]
                            if 'suggestion' in first_item and 'code' in first_item:
                                return final_list
                            else:
                                print(f"⚠️ 返回数据缺少必要字段: {first_item.keys()}")
                        else:
                            print("⚠️ 解析后得到空列表")

                    except Exception as e:
                        print(f"❌ 处理响应数据出错: {e}")
                        continue

                else:
                    print(f"❌ API 请求失败 [Status {response.status_code}]: {response.text[:200]}")
                    # 4xx 错误通常无需重试 (除了 429 Rate Limit)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        break

                time.sleep(1)  # 避免触发频率限制

            except Exception as e:
                print(f"❌ 网络请求异常 (Attempt {attempt + 1}): {e}")
                time.sleep(1)

        return []  # 所有重试失败，返回空列表

    def analyze_stocks(self, df_stocks: pd.DataFrame, batch_size: int = None, max_threads: int = None) -> pd.DataFrame:
        """
        执行 AI 分析的主入口
        :param df_stocks: 包含技术指标的 DataFrame
        :param batch_size: 批处理大小 (默认使用 config.py 配置)
        :param max_threads: 并发线程数 (默认使用 config.py 配置)
        :return: 包含 AI 建议的 DataFrame
        """
        if df_stocks.empty:
            return df_stocks

        # 使用默认配置如果未传入参数
        if batch_size is None: batch_size = AI_BATCH_SIZE
        if max_threads is None: max_threads = AI_MAX_THREADS

        # 筛选发送给 LLM 的关键字段，减少 Token 消耗
        cols_to_send = [
            '代码', '名称', '买入价',
            '均线形态', '年线状态',
            'MACD状态', 'KDJ状态', 'RSI',
            '量能状态', '量比',
            '压力位距', '支撑位距',  # 发送百分比给 LLM
            '近5日走势', '策略匹配'
        ]

        valid_cols = [c for c in cols_to_send if c in df_stocks.columns]
        # 转换为字典列表
        records = df_stocks[valid_cols].to_dict(orient='records')

        print(f"🤖 准备分析 {len(records)} 只股票 (Batch: {batch_size}, Threads: {max_threads})...")

        # 切分批次
        batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
        ai_results = {}

        # 并发请求
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_batch = {executor.submit(self._call_batch, b): b for b in batches}

            for future in tqdm(as_completed(future_to_batch), total=len(batches), desc="AI 分析中"):
                try:
                    batch_res = future.result()
                    if not batch_res:
                        # 某批次失败，不影响其他批次
                        continue

                    for item in batch_res:
                        if item.get('code'):
                            ai_results[item['code']] = {
                                'AI建议': item.get('suggestion', '无建议'),
                                'AI点评': item.get('reason', 'AI解析失败')
                            }
                except Exception as e:
                    print(f"💥 批次处理异常: {e}")

        # 将结果合并回 DataFrame
        df_result = df_stocks.copy()

        # 初始化列
        if 'AI建议' not in df_result.columns: df_result['AI建议'] = ''
        if 'AI点评' not in df_result.columns: df_result['AI点评'] = ''

        # 填充结果
        for idx, row in df_result.iterrows():
            code = row['代码']
            if code in ai_results:
                df_result.at[idx, 'AI建议'] = ai_results[code]['AI建议']
                df_result.at[idx, 'AI点评'] = ai_results[code]['AI点评']

        return df_result
