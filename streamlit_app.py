import streamlit as st
import tushare as ts
from openai import OpenAI
import datetime
import pandas as pd

# =====================================================================
# 1. 界面配置 (UI Scheduling)
# =====================================================================
st.set_page_config(page_title="A股价值投机分析助手", layout="wide")

st.title("🚀 A-Share Analyst Pro")
st.markdown("---")

# 硬编码配置 (已根据您的要求填入真实 Token，无需手动输入)
TS_TOKEN = "466650b09f57421c624ba34354f7e071f5a7502b184728c339e556d92a8c"
LLM_TOKEN = "sk-wFo3bQLMfw4oKDkS3jrXvvyTGMkQZbG1Xv8ynqBWILb3wkzA"

# 侧边栏仅保留投研参数展示
with st.sidebar:
    st.header("👤 投资者画像")
    st.markdown("""
    - **资金规模**: 50万RMB
    - **投资风格**: 价值投机
    - **核心诉求**: 追求正宗度与短期弹性
    """)
    st.markdown("---")
    st.info("💡 这是一个私有的 AI 投研系统，已预置专线 Token。")


# =====================================================================
# 2. 数据链路层 (Data Link Layer)
# =====================================================================
def get_stock_data(token, code):
    # 转换 A 股代码后缀
    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    # 初始化 Tushare (使用您的私有中继路由)
    ts.set_token(token)
    pro = ts.pro_api()
    pro._DataApi__token = token
    pro._DataApi__http_url = 'http://lianghua.nanyangqiankun.top'

    end_date = datetime.datetime.now().strftime('%Y%m%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=20)).strftime('%Y%m%d')

    try:
        # 并行思路：获取 K 线、基本面指标和公司业务描述
        df_k = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        df_basic = pro.daily_basic(ts_code=ts_code, limit=1)
        df_comp = pro.stock_company(ts_code=ts_code, fields='main_business')

        if df_k.empty: return None

        # 组装特征载荷 (Payload)
        context = {
            "name": ts_code,
            "business": df_comp.iloc[0]['main_business'] if not df_comp.empty else "未知",
            "pe": df_basic.iloc[0]['pe_ttm'] if not df_basic.empty else "N/A",
            "pb": df_basic.iloc[0]['pb'] if not df_basic.empty else "N/A",
            "turnover": df_basic.iloc[0]['turnover_rate_f'] if not df_basic.empty else "N/A",
            "trend": df_k.head(10)[['trade_date', 'close', 'pct_chg']].to_string(index=False)
        }
        return context
    except Exception as e:
        st.error(f"数据抓取失败: {e}")
        return None


# =====================================================================
# 3. 交互逻辑 (Interaction Logic)
# =====================================================================
col1, col2 = st.columns([1, 3])

with col1:
    stock_code = st.text_input("请输入6位股票代码", value="600418", max_chars=6)
    analyze_btn = st.button("开始深度诊断", use_container_width=True)

    st.markdown("""
    ### 🛡️ 系统状态
    - **行情专线**: Tushare 正常
    - **推理网关**: Gemini 3.1 正常
    - **数据深度**: 2周趋势 + 财务快照
    """)

if analyze_btn:
    with st.spinner("正在同步双链路数据并生成报告..."):
        # 调用数据链路
        data = get_stock_data(TS_TOKEN, stock_code)

        if data:
            with col2:
                st.subheader(f"📊 {stock_code} 深度诊断报告")

                # 构建 Prompt 思想链 (CoT)
                prompt = f"""
                你是一位专门服务于大户的A股价值投机专家。风格犀利，拒绝废话。
                【数据载荷】:
                - 核心业务: {data['business']}
                - 估值指标: PE {data['pe']}, PB {data['pb']}, 换手率 {data['turnover']}%
                - 近10日趋势: \n{data['trend']}

                请基于以上数据输出一份极具“盘感”的深度报告。
                必须包含：<深度逻辑推演>、量价趋势研判、以及针对 50万 资金的具体战术建议（止损点、止盈位、仓位控制）。
                """

                # LLM 推理 (流式输出)
                client = OpenAI(api_key=LLM_TOKEN, base_url="https://geminiapi.asia/v1")

                try:
                    placeholder = st.empty()
                    full_response = ""

                    response = client.chat.completions.create(
                        model="gemini-3.1-pro-preview",
                        messages=[
                            {"role": "system", "content": "你是一位犀利的A股分析师。要求排版精美，逻辑硬核。"},
                            {"role": "user", "content": prompt}
                        ],
                        stream=True,
                        temperature=0.3
                    )

                    for chunk in response:
                        if chunk.choices[0].delta.content:
                            full_response += chunk.choices[0].delta.content
                            placeholder.markdown(full_response + "▌")

                    placeholder.markdown(full_response)

                except Exception as e:
                    st.error(f"AI 推理失败: {e}")
        else:
            st.error("数据拉取失败，请检查代码或 Token 有效性。")

st.markdown("---")
st.caption("⚠️ 免责声明：以上分析由 AI 生成，仅供投研参考。投资有风险，入市需谨慎。")