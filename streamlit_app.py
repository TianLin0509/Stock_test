import streamlit as st
import tushare as ts
from openai import OpenAI
import datetime
import pandas as pd

# =====================================================================
# 1. 配置中心
# =====================================================================
TS_TOKEN = "7e036faa8db4125082157932fb5135356c8919ac99b151a7e0449c10cb2d"
LLM_API_KEY = "sk-wFo3bQLMfw4oKDkS3jrXvvyTGMkQZbG1Xv8ynqBWILb3wkzA"
LLM_BASE_URL = "https://geminiapi.asia/v1"

st.set_page_config(page_title="A股价值投机助手", layout="wide")

# 精简版 UI 样式
st.markdown("""
    <style>
    .report-card { background-color: #f8fafc; padding: 1.5rem; border-radius: 0.5rem; border: 1px solid #e2e8f0; }
    h3 { color: #1e293b; border-left: 4px solid #2563eb; padding-left: 12px; }
    </style>
    """, unsafe_allow_html=True)


# =====================================================================
# 2. 数据引擎 (Tushare)
# =====================================================================
def fetch_stock_data(code, status):
    """获取个股多维特征"""
    symbol = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
    # 初始化接口
    pro = ts.pro_api(TS_TOKEN)
    pro._DataApi__token = TS_TOKEN  # 保证有这个代码，不然不可以获取
    pro._DataApi__http_url = 'http://lianghua.nanyangqiankun.top'  # 保证有这个代码，不然不可以获取
    # 若需使用特定代理/专线，请保留此行，否则可删除
    ts.set_token(TS_TOKEN)

    end_dt = datetime.datetime.now().strftime('%Y%m%d')
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=20)).strftime('%Y%m%d')

    try:
        status.write("📊 提取行情与基本面特征...")
        # 1. 量价序列
        df_k = pro.daily(ts_code=symbol, start_date=start_dt, end_date=end_dt)
        # 2. 基础指标 (PE/PB/换手)
        df_basic = pro.daily_basic(ts_code=symbol, limit=1)
        # 3. 业务正宗度
        df_comp = pro.stock_company(ts_code=symbol, fields='main_business')

        if df_k.empty: return None

        return {
            "name": symbol,
            "business": df_comp.iloc[0]['main_business'] if not df_comp.empty else "未知",
            "pe": df_basic.iloc[0]['pe_ttm'] if not df_basic.empty else "N/A",
            "turnover": df_basic.iloc[0]['turnover_rate_f'] if not df_basic.empty else "N/A",
            "trend": df_k.head(8)[['trade_date', 'close', 'pct_chg']].to_string(index=False)
        }
    except Exception as e:
        st.error(f"数据获取失败: {e}")
        return None


# =====================================================================
# 3. 页面布局与交互
# =====================================================================
st.title("🚀 呆瓜方后援会-专用股票分析平台")

with st.sidebar:
    st.header("👤 投资者画像")
    st.info("**资金**: 50万 | **风格**: 价值投机\n\n**诉求**: 追求正宗度与短期弹性")
    st.divider()
    st.caption("数据链路：Tushare 专线已连接")

col_in, col_out = st.columns([1, 2.5])

with col_in:
    stock_code = st.text_input("股票代码", value="600418", max_chars=6)
    run_analysis = st.button("开始深度诊断", use_container_width=True, type="primary")
    st.warning("💡 **分析师寄语**：拼的是筹码洞察，而非单纯财报。严格执行纪律。")

if run_analysis:
    with st.status("🧠 正在进行逻辑推演...", expanded=True) as status:
        data = fetch_stock_data(stock_code, status)

        if data:
            status.update(label="✅ 数据就绪，生成报告中...", state="running")
            with col_out:
                st.subheader(f"📊 {stock_code} 深度诊断")

                client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
                prompt = f"核心业务:{data['business']}\nPE:{data['pe']},换手:{data['turnover']}%\n近8日趋势:\n{data['trend']}\n\n作为A股专家，请给出深度逻辑推演、量价研判及50万资金的战术建议。"

                try:
                    placeholder = st.empty()
                    full_res = ""
                    stream = client.chat.completions.create(
                        model="gemini-3.1-pro-preview",
                        messages=[{"role": "system", "content": "犀利硬核的A股分析师，排版精美。"},
                                  {"role": "user", "content": prompt}],
                        stream=True, temperature=0.3
                    )
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            status.update(label="✅ 分析完成", state="complete", expanded=False)
                            full_res += chunk.choices[0].delta.content
                            placeholder.markdown(full_res + " ▌")
                    placeholder.markdown(full_res)
                except Exception as e:
                    st.error(f"推理异常: {e}")
        else:
            status.update(label="❌ 诊断中断", state="error")