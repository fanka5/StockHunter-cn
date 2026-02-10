import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json
import time
import datetime
from pathlib import Path
import logging

# 引入模块
from src.downloader import StockDownloader
from src.data_analyzer import TechnicalAnalyzer
from src.llm_agent import LLMAgent
from config import DATA_DIR, OUTPUT_DIR, WATCHLIST_FILE, AI_MAX_THREADS, AI_BATCH_SIZE

# 0. 屏蔽警告
logging.getLogger('streamlit.runtime.scriptrunner_utils.script_run_context').setLevel(logging.ERROR)
logging.getLogger('streamlit.runtime.scriptrunner.script_runner').setLevel(logging.ERROR)


# ===========================
# 2. 核心辅助函数 (这些定义必须放在全局)
# ===========================
def get_data_status():
    if not os.path.exists(str(DATA_DIR)): return 0, "无数据"
    files = list(Path(DATA_DIR).glob("*.csv"))
    if not files: return 0, "无数据"
    last_mod = max(f.stat().st_mtime for f in files)
    dt_obj = datetime.datetime.fromtimestamp(last_mod)
    return len(files), dt_obj.strftime("%Y-%m-%d %H:%M")


def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        return []
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except:
        return []


def save_watchlist(lst):
    with open(WATCHLIST_FILE, 'w') as f: json.dump(lst, f)


def find_stock_info(input_str):
    """简易的本地搜索"""
    if not os.path.exists(str(DATA_DIR)): return None, None
    input_str = input_str.strip()

    for f in os.listdir(str(DATA_DIR)):
        if not f.endswith(".csv"): continue
        try:
            raw_name = f.replace('.csv', '')
            parts = raw_name.split('_')
            full_code = parts[0]
            name = parts[1]
            short_code = full_code.split('.')[1] if '.' in full_code else full_code
            if input_str == short_code or input_str == name:
                return full_code, name
        except:
            continue
    return None, None


def get_stock_name_map():
    mapping = {}
    if os.path.exists(str(DATA_DIR)):
        for f in os.listdir(str(DATA_DIR)):
            if f.endswith(".csv"):
                try:
                    parts = f.replace('.csv', '').split('_')
                    mapping[parts[0]] = parts[1]
                except:
                    pass
    return mapping


def get_all_result_files():
    if not os.path.exists(OUTPUT_DIR): return []
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
    return files


def load_stock_data(code):
    if not os.path.exists(str(DATA_DIR)): return None, None
    target_file = None
    for f in os.listdir(str(DATA_DIR)):
        if f.startswith(code + "_"):
            target_file = f
            break
    if not target_file: return None, None

    # explicit string cast to avoid path warnings
    df = pd.read_csv(str(os.path.join(DATA_DIR, target_file)))

    df.drop_duplicates(subset=['date'], keep='last', inplace=True)
    df.sort_values('date', inplace=True)

    df['date'] = pd.to_datetime(df['date'])
    df['MA5'] = ta.sma(df['close'], length=5)
    df['MA20'] = ta.sma(df['close'], length=20)
    stock_name = target_file.split('_')[1].replace('.csv', '')
    return df, stock_name


def plot_k_line(df, code, name, mark_date=None):
    """绘制交互式 K 线图"""
    if mark_date:
        mark_dt = pd.to_datetime(mark_date)
        mask = (df['date'] >= mark_dt - pd.Timedelta(days=180))
        df_plot = df.loc[mask].copy()
    else:
        df_plot = df.tail(250).reset_index(drop=True)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=(f"{name} ({code})", ""),
        row_width=[0.2, 0.8]
    )

    fig.add_trace(go.Candlestick(
        x=df_plot['date'],
        open=df_plot['open'],
        high=df_plot['high'],
        low=df_plot['low'],
        close=df_plot['close'],
        name='K线',
        increasing=dict(line=dict(color='#e53935'), fillcolor='#e53935'),
        decreasing=dict(line=dict(color='#43a047'), fillcolor='#43a047')
    ), row=1, col=1)

    if 'MA5' in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['MA5'], mode='lines', name='MA5',
                                 line=dict(color='black', width=1), opacity=0.7), row=1, col=1)
    if 'MA20' in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['MA20'], mode='lines', name='MA20',
                                 line=dict(color='blue', width=1.5), opacity=0.8), row=1, col=1)

    if mark_date:
        mark_dt_obj = pd.to_datetime(mark_date)
        x_timestamp = mark_dt_obj.timestamp() * 1000
        fig.add_vline(x=x_timestamp, line_width=2, line_dash="dash", line_color="#1565c0", annotation_text="分析日")

    colors_vol = ['#e53935' if row['open'] < row['close'] else '#43a047' for index, row in df_plot.iterrows()]
    fig.add_trace(go.Bar(
        x=df_plot['date'],
        y=df_plot['volume'],
        marker_color=colors_vol,
        name='成交量'
    ), row=2, col=1)

    fig.update_layout(
        height=550,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor='rgba(250,250,250,1)',
        xaxis_rangeslider_visible=False,
        dragmode='pan',
        hovermode='x unified',
        legend=dict(orientation="h", y=1.01, x=0.01, bgcolor='rgba(255,255,255,0.5)'),
    )

    dt_all = pd.date_range(start=df_plot['date'].iloc[0], end=df_plot['date'].iloc[-1])
    dt_obs = [d.strftime("%Y-%m-%d") for d in df_plot['date']]
    dt_breaks = [d.strftime("%Y-%m-%d") for d in dt_all if d.strftime("%Y-%m-%d") not in dt_obs]

    fig.update_xaxes(
        rangebreaks=[dict(values=dt_breaks)],
        showspikes=True, spikethickness=1, spikecolor="gray", spikemode="across",
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1月", step="month", stepmode="backward"),
                dict(count=3, label="3月", step="month", stepmode="backward"),
                dict(count=6, label="6月", step="month", stepmode="backward"),
                dict(step="all", label="全部")
            ]),
            bgcolor="#f0f0f0",
            font=dict(size=11)
        )
    )
    fig.update_yaxes(showspikes=True, spikethickness=1, spikecolor="gray", spikemode="across")

    return fig


# ===========================
# 主程序逻辑 (封装到 main 函数中)
# ===========================
def main():
    # 1. 页面配置 (必须在 Streamlit 命令最前面)
    st.set_page_config(layout="wide", page_title="StockHunter AI", page_icon="🏹")
    pd.options.mode.chained_assignment = None

    # ===========================
    # 3. 侧边栏逻辑
    # ===========================
    with st.sidebar:
        st.title("🏹 StockHunter")

        # --- 1. 自选股管理 ---
        with st.expander("❤️ 自选股管理", expanded=True):
            watchlist = load_watchlist()
            name_map = get_stock_name_map()
            with st.form(key='add_stock_form', clear_on_submit=True):
                c1, c2 = st.columns([3, 1])
                new_input = c1.text_input("代码/简称", placeholder="001282/飞龙", label_visibility="collapsed")
                submitted = c2.form_submit_button("➕")
                if submitted and new_input:
                    full_code, found_name = find_stock_info(new_input)
                    if full_code:
                        if full_code not in watchlist:
                            watchlist.append(full_code)
                            save_watchlist(watchlist)
                            st.toast(f"已添加: {found_name}")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("已在列表中")
                    else:
                        st.error("未找到本地数据，请先同步")

            if watchlist:
                st.caption(f"共 {len(watchlist)} 只")
                for full_code in watchlist:
                    short_code = full_code.split('.')[1] if '.' in full_code else full_code
                    d_name = name_map.get(full_code, "未知")
                    col_txt, col_del = st.columns([4, 1])
                    col_txt.text(f"{short_code} {d_name}")
                    if col_del.button("×", key=f"del_sidebar_{full_code}"):
                        watchlist.remove(full_code)
                        save_watchlist(watchlist)
                        st.rerun()
            else:
                st.caption("暂无自选股")

        st.divider()

        # --- 2. 数据同步 ---
        with st.expander("💾 数据同步", expanded=True):
            count, last_update = get_data_status()
            st.caption(f"状态: {count} 只 | {last_update}")

            dl_scope = st.radio(
                "下载范围",
                ["watchlist", "all"],
                index=0,
                format_func=lambda x: "⚡ 仅自选股 (极速)" if x == "watchlist" else "🔄 全市场 (全量)"
            )

            if st.button("📥 开始同步数据", type="secondary", width='stretch'):
                target_codes = None
                if dl_scope == "watchlist":
                    if not watchlist:
                        st.error("自选股列表为空！")
                        st.stop()
                    target_codes = watchlist
                    msg = "正在同步自选股..."
                else:
                    msg = "正在同步全市场数据 (耗时较长)..."

                with st.status(msg, expanded=True) as status:
                    # 注意：StockDownloader 会启动多进程，如果没有 main 保护，会在此处无限递归
                    downloader = StockDownloader()
                    downloader.run(target_codes=target_codes)
                    status.update(label="同步完成！", state="complete")
                time.sleep(1)
                st.rerun()

        st.divider()

        # --- 3. 分析参数设置 ---
        with st.expander("⚙️ 分析参数设置", expanded=True):
            analysis_mode = st.selectbox("分析模式", ["current", "backtest"],
                                         format_func=lambda x: "📈 最新行情" if x == "current" else "⏮️ 历史回测")
            backtest_date_str = None
            if analysis_mode == "backtest":
                default_bt = datetime.date.today() - datetime.timedelta(days=40)
                bt_date_input = st.date_input("回测基准日", default_bt)
                backtest_date_str = bt_date_input.strftime("%Y-%m-%d")

            analysis_scope = st.radio("分析范围", ["watchlist_only", "all"], index=0,
                                      format_func=lambda x: "仅自选股" if x == "watchlist_only" else "全市场+自选")

            st.caption("🤖 LLM 设置")
            max_ai_stocks = st.number_input("AI分析最大数量 (非自选)", min_value=1, max_value=100, value=8)

            st.divider()
            btn_start = st.button("🚀 开始分析", type="primary", width='stretch')

    # ===========================
    # 4. 主界面逻辑 (分析流程)
    # ===========================

    if btn_start:
        status_text = st.empty()
        progress_bar = st.progress(0)

        try:
            status_text.write("⏳ 正在进行技术指标计算...")
            analyzer = TechnicalAnalyzer(mode=analysis_mode, scope=analysis_scope, backtest_date=backtest_date_str)
            df_tech = analyzer.run_analysis()

            if df_tech.empty:
                st.error("❌ 未筛选到符合条件的股票 (可能是本地无数据，请先同步)")
                st.stop()

            progress_bar.progress(30)

            date_suffix = backtest_date_str.replace('-',
                                                    '') if analysis_mode == "backtest" else datetime.datetime.now().strftime(
                "%Y%m%d")
            mode_prefix = "backtest" if analysis_mode == "backtest" else "analysis"
            res_file = OUTPUT_DIR / f"{mode_prefix}_result_{date_suffix}.csv"

            if analysis_mode == "current" and res_file.exists():
                try:
                    df_old = pd.read_csv(str(res_file), dtype={'代码': str})
                    if 'AI建议' in df_old.columns:
                        df_old['AI建议'] = df_old['AI建议'].fillna('')
                        df_old['AI点评'] = df_old['AI点评'].fillna('')
                        valid_cache = df_old[df_old['AI建议'].str.strip() != '']
                        cache_map = valid_cache.set_index('代码')[['AI建议', 'AI点评']].to_dict('index')

                        cached_count = 0
                        for idx, row in df_tech.iterrows():
                            code = str(row['代码'])
                            if code in cache_map:
                                df_tech.at[idx, 'AI建议'] = cache_map[code]['AI建议']
                                df_tech.at[idx, 'AI点评'] = cache_map[code]['AI点评']
                                cached_count += 1

                        if cached_count > 0:
                            status_text.write(f"♻️ 已复用 {cached_count} 条今日已分析结果，不再重复请求...")
                except Exception as e:
                    print(f"⚠️ 加载缓存失败: {e}")

            df_vip = df_tech[df_tech['is_watchlist'] == True].copy()
            df_others = df_tech[df_tech['is_watchlist'] == False].copy()

            if not df_others.empty:
                df_others = df_others.sort_values(by='RSI').head(max_ai_stocks)

            df_final = pd.concat([df_vip, df_others]).drop_duplicates(subset=['代码'])
            df_to_process = df_final[df_final['AI建议'] == ''] if 'AI建议' in df_final.columns else df_final

            progress_bar.progress(50)

            if not df_to_process.empty:
                status_text.write(f"🤖 正在 AI 分析 {len(df_to_process)} 只股票...")
                agent = LLMAgent()
                df_processed = agent.analyze_stocks(df_to_process, batch_size=AI_BATCH_SIZE, max_threads=AI_MAX_THREADS)
                df_final = df_final[~df_final['代码'].isin(df_processed['代码'])]
                df_final = pd.concat([df_final, df_processed])

            progress_bar.progress(90)

            sort_cols = ['AI建议', 'is_watchlist']
            asc_order = [False, False]
            if analysis_mode == "backtest":
                sort_cols.insert(0, 'T+30收益(%)')
                asc_order.insert(0, False)

            df_final = df_final.sort_values(by=sort_cols, ascending=asc_order, key=lambda x: x.astype(str))
            df_final.to_csv(res_file, index=False, encoding='utf-8-sig')

            progress_bar.progress(100)
            status_text.success("✅ 分析完成！")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"运行出错: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ===========================
    # 5. 结果展示
    # ===========================
    st.header("📂 分析报告视图")
    all_files = get_all_result_files()

    if not all_files:
        st.info("暂无分析报告，请点击左侧按钮开始运行。")
        st.stop()

    selected_file = st.selectbox("选择历史报告", all_files, label_visibility="collapsed")

    # 【修复关键点】防止空值导致的崩溃
    if not selected_file:
        st.stop()

    file_path = os.path.join(OUTPUT_DIR, selected_file)

    try:
        df_result = pd.read_csv(str(file_path))
        if '代码' not in df_result.columns:
            st.error("文件格式错误：缺少'代码'列")
            st.stop()
    except Exception as e:
        st.error(f"无法读取文件: {e}")
        st.stop()

    is_backtest_file = "backtest" in selected_file or "T+30收益(%)" in df_result.columns
    has_ai = "AI建议" in df_result.columns
    watchlist = load_watchlist()
    df_result['is_watchlist'] = df_result['代码'].apply(lambda x: x in watchlist)

    if is_backtest_file and 'T+30收益(%)' in df_result.columns:
        st.markdown("### 📊 回测效能概览")
        c1, c2, c3, c4 = st.columns(4)
        avg_ret = df_result['T+30收益(%)'].mean()
        win_rate = len(df_result[df_result['T+30收益(%)'] > 0]) / len(df_result) * 100
        c1.metric("分析样本", f"{len(df_result)} 只")
        c2.metric("T+30 胜率", f"{win_rate:.1f}%")
        c3.metric("T+30 平均收益", f"{avg_ret:.2f}%", delta_color="inverse")
        c4.metric("最大潜力", f"{df_result['后市最高涨幅(%)'].max():.2f}%")
        st.divider()

    col_list, col_detail = st.columns([1.6, 2])

    display_cols = ['代码', '名称']
    if has_ai: display_cols.append('AI建议')
    if is_backtest_file:
        for m in ['T+5收益(%)', 'T+10收益(%)', 'T+30收益(%)']:
            if m in df_result.columns: display_cols.append(m)
    else:
        if 'RSI' in df_result.columns: display_cols.append('RSI')
        if '量比' in df_result.columns: display_cols.append('量比')

    col_config = {
        "T+5收益(%)": st.column_config.NumberColumn(format="%.2f%%"),
        "T+10收益(%)": st.column_config.NumberColumn(format="%.2f%%"),
        "T+30收益(%)": st.column_config.NumberColumn(format="%.2f%%"),
        "RSI": st.column_config.NumberColumn(format="%.1f"),
        "量比": st.column_config.NumberColumn(format="%.2f"),
    }

    selected_row = None

    with col_list:
        st.subheader("📋 股票列表")
        df_fav = df_result[df_result['is_watchlist']]
        df_oth = df_result[~df_result['is_watchlist']]

        tabs = []
        tab_names = []
        if not df_fav.empty or not df_oth.empty:
            tab_names.append(f"❤️ 自选 ({len(df_fav)})")
            tab_names.append(f"🚀 推荐 ({len(df_oth)})")
            tabs = st.tabs(tab_names)

            with tabs[0]:
                if not df_fav.empty:
                    e1 = st.dataframe(df_fav[display_cols], height=500, hide_index=True, on_select="rerun",
                                      selection_mode="single-row", key="t1", column_config=col_config, width="stretch")
                    if e1.selection.rows: selected_row = df_fav.iloc[e1.selection.rows[0]]
                else:
                    st.info("无自选数据")

            with tabs[1]:
                if not df_oth.empty:
                    e2 = st.dataframe(df_oth[display_cols], height=500, hide_index=True, on_select="rerun",
                                      selection_mode="single-row", key="t2", column_config=col_config, width="stretch")
                    if e2.selection.rows and selected_row is None: selected_row = df_oth.iloc[e2.selection.rows[0]]
                else:
                    st.info("无推荐数据")
        else:
            st.warning("结果集为空")

        if selected_row is None:
            if not df_fav.empty:
                selected_row = df_fav.iloc[0]
            elif not df_oth.empty:
                selected_row = df_oth.iloc[0]

    with col_detail:
        if selected_row is not None:
            code = selected_row['代码']
            name = selected_row['名称']

            c_t, c_b = st.columns([5, 1])
            c_t.markdown(f"## {name} <small style='color:gray'>{code}</small>", unsafe_allow_html=True)
            is_fav = code in watchlist
            if c_b.button("💔" if is_fav else "❤️", key=f"fav_btn_{code}"):
                if is_fav:
                    watchlist.remove(code)
                else:
                    watchlist.append(code)
                save_watchlist(watchlist)
                st.rerun()

            df_stock, _ = load_stock_data(code)
            if df_stock is not None:
                m_date = selected_row.get('回测日期') if is_backtest_file else None
                fig = plot_k_line(df_stock, code, name, m_date)
                st.plotly_chart(fig, width='stretch', config={'scrollZoom': True})
            else:
                st.warning("本地暂无该股票K线数据")

            if '均线形态' in selected_row.index:
                st.markdown("##### 🔍 技术面透视")
                ma_s = selected_row.get('均线形态', '--')
                macd_s = selected_row.get('MACD状态', '--')
                press_p = selected_row.get('压力位', '--')
                supp_p = selected_row.get('支撑位', '--')

                st.markdown(f"""
                <style>
                    .tech-box {{
                        display: flex; 
                        justify-content: space-between; 
                        background-color: #f0f2f6; 
                        padding: 10px; 
                        border-radius: 5px;
                        font-size: 14px;
                    }}
                    .tech-item {{ text-align: center; }}
                    .tech-label {{ color: #666; font-size: 12px; }}
                    .tech-val {{ font-weight: bold; color: #333; }}
                </style>
                <div class="tech-box">
                    <div class="tech-item"><div class="tech-label">均线</div><div class="tech-val">{ma_s}</div></div>
                    <div class="tech-item"><div class="tech-label">MACD</div><div class="tech-val">{macd_s}</div></div>
                    <div class="tech-item"><div class="tech-label">压力位</div><div class="tech-val">{press_p}</div></div>
                    <div class="tech-item"><div class="tech-label">支撑位</div><div class="tech-val">{supp_p}</div></div>
                </div>
                """, unsafe_allow_html=True)

            if has_ai and pd.notna(selected_row.get('AI建议')) and selected_row.get('AI建议') != '':
                st.divider()
                sugg = selected_row['AI建议']
                reason = selected_row.get('AI点评', '暂无详细点评')

                color_map = {"强烈推荐": "green", "推荐": "green", "谨慎": "orange", "观望": "gray", "不推荐": "red"}
                s_color = "blue"
                for k, v in color_map.items():
                    if k in str(sugg): s_color = v

                st.markdown(f"#### 🤖 AI 观点: :{s_color}[{sugg}]")
                with st.expander("查看详细逻辑", expanded=True):
                    st.write(reason)

                if is_backtest_file:
                    st.caption("📅 历史验证数据:")
                    c_5, c_10, c_30 = st.columns(3)
                    r5 = selected_row.get('T+5收益(%)', 0)
                    r10 = selected_row.get('T+10收益(%)', 0)
                    r30 = selected_row.get('T+30收益(%)', 0)

                    c_5.metric("T+5", f"{r5}%", delta=f"{r5}%")
                    c_10.metric("T+10", f"{r10}%", delta=f"{r10}%")
                    c_30.metric("T+30", f"{r30}%", delta=f"{r30}%")

            if pd.notna(selected_row.get('策略匹配')):
                st.info(f"📌 筛选理由: {selected_row.get('策略匹配', '--')}")

        else:
            st.write("👈 请从左侧列表选择一只股票查看详情")


# ===========================
# 🚀 启动入口 (关键修正：解决 Windows 多进程问题)
# ===========================
if __name__ == "__main__":
    main()
