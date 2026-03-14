"""全局 CSS 样式 — 浅色可爱风 + 移动端响应式"""

import streamlit as st


def inject_css():
    """注入全局 CSS 样式"""
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700&display=swap');

:root {
  --bg:        #f6f8ff;
  --bg-card:   #ffffff;
  --bg-soft:   #eef2ff;
  --border:    #dde3ff;
  --up:        #22c55e;
  --down:      #ef4444;
  --blue:      #6366f1;
  --blue-lt:   #eef2ff;
  --pink:      #ec4899;
  --pink-lt:   #fdf2f8;
  --teal:      #06b6d4;
  --orange:    #f97316;
  --orange-lt: #fff7ed;
  --purple:    #a855f7;
  --purple-lt: #faf5ff;
  --text:      #1e1b4b;
  --text-mid:  #6b7280;
  --text-lo:   #9ca3af;
  --shadow:    0 2px 16px rgba(99,102,241,0.08);
  --shadow-md: 0 4px 24px rgba(99,102,241,0.12);
  --radius:    16px;
  --radius-sm: 10px;
}

/* 禁用 Streamlit rerun 时旧内容的半透明残影效果 */
[data-stale="true"] { opacity: 1 !important; }

html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  font-family: 'Noto Sans SC', 'PingFang SC', sans-serif;
  color: var(--text);
}
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text-mid) !important; }
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong { color: var(--blue) !important; }

/* App header */
.app-header {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
  border-radius: var(--radius);
  padding: 1.6rem 2rem;
  margin-bottom: 1.2rem;
  position: relative; overflow: hidden;
  box-shadow: 0 8px 32px rgba(99,102,241,0.25);
}
.app-header::before {
  content: '📊 📈 💹 📉 🏦';
  position: absolute; top: 12px; right: 8px;
  font-size: 1.4rem; opacity: 0.13;
  white-space: nowrap; letter-spacing: 0.6em;
}
.app-header h1 {
  font-family: 'Nunito', sans-serif;
  font-size: 1.9rem; font-weight: 800;
  color: #fff; margin: 0;
  text-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.app-header p {
  color: rgba(255,255,255,0.82);
  font-size: 0.86rem; margin: 0.35rem 0 0;
  font-weight: 500;
}

/* Model status badge */
.model-badge {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--bg-soft);
  border: 1.5px solid var(--border);
  border-radius: 50px;
  padding: 4px 14px;
  font-size: 0.82rem; font-weight: 600;
  color: var(--blue);
  margin-bottom: 1rem;
}
.model-badge.ok   { background: #f0fdf4; border-color: #86efac; color: #16a34a; }
.model-badge.warn { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
.model-badge.err  { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }

/* Status banner */
.status-banner {
  border-radius: var(--radius-sm);
  padding: 0.75rem 1.1rem;
  margin: 0.5rem 0;
  font-size: 0.86rem;
  line-height: 1.6;
  display: flex; align-items: flex-start; gap: 10px;
}
.status-banner.info    { background: var(--blue-lt);   border: 1px solid #c7d2fe; color: #3730a3; }
.status-banner.warn    { background: #fff7ed;           border: 1px solid #fed7aa; color: #92400e; }
.status-banner.error   { background: #fef2f2;           border: 1px solid #fca5a5; color: #991b1b; }
.status-banner.success { background: #f0fdf4;           border: 1px solid #86efac; color: #14532d; }

/* Cards */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.4rem 1.6rem;
  margin: 0.7rem 0;
  box-shadow: var(--shadow);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg-card) !important;
  border-radius: 50px !important;
  padding: 4px !important;
  border: 1px solid var(--border) !important;
  gap: 2px !important;
  box-shadow: var(--shadow) !important;
  width: fit-content !important;
}
.stTabs [data-baseweb="tab"] {
  border-radius: 50px !important;
  font-family: 'Nunito', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.85rem !important;
  color: var(--text-mid) !important;
  padding: 6px 20px !important;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  color: #fff !important;
  box-shadow: 0 2px 10px rgba(99,102,241,0.3) !important;
}

/* MoE role cards */
.role-card {
  border-radius: var(--radius); padding: 1.3rem 1.5rem;
  margin: 0.9rem 0; border: 1px solid; position: relative;
}
.role-badge {
  font-family: 'Nunito', sans-serif; font-size: 0.8rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 12px; border-radius: 50px;
  display: inline-block; margin-bottom: 0.8rem;
}
.role-content { font-size: 0.9rem; line-height: 1.8; white-space: pre-wrap; color: var(--text); }

.r-trader  { background: #fff5f5; border-color: #fca5a5; }
.r-trader  .role-badge { background: #fee2e2; color: #dc2626; }
.r-inst    { background: #f0fdf4; border-color: #86efac; }
.r-inst    .role-badge { background: #dcfce7; color: #16a34a; }
.r-quant   { background: var(--blue-lt); border-color: #c7d2fe; }
.r-quant   .role-badge { background: #e0e7ff; color: var(--blue); }
.r-retail  { background: var(--orange-lt); border-color: #fed7aa; }
.r-retail  .role-badge { background: #ffedd5; color: var(--orange); }
.r-vspec   { background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border-color: #fcd34d; }
.r-vspec   .role-badge { background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; box-shadow: 0 2px 8px rgba(245,158,11,0.3); }
.r-ceo {
  background: linear-gradient(135deg, var(--purple-lt) 0%, var(--pink-lt) 100%);
  border-color: #d8b4fe;
  box-shadow: 0 4px 24px rgba(168,85,247,0.12);
}
.r-ceo .role-badge {
  background: linear-gradient(135deg, var(--purple), var(--pink));
  color: #fff; box-shadow: 0 2px 8px rgba(168,85,247,0.3);
}

/* Analysis wrap */
.analysis-wrap {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.6rem 1.8rem;
  box-shadow: var(--shadow); line-height: 1.8; font-size: 0.92rem;
}

/* Buttons */
.stButton button {
  border-radius: 50px !important;
  font-family: 'Nunito', sans-serif !important;
  font-weight: 700 !important; font-size: 0.88rem !important;
  padding: 0.5rem 1.4rem !important;
}
.stButton button[kind="primary"] {
  background: linear-gradient(135deg, var(--blue), var(--purple)) !important;
  border: none !important; color: #fff !important;
  box-shadow: 0 4px 14px rgba(99,102,241,0.3) !important;
}
.stButton button[kind="primary"]:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4) !important;
}

/* Input */
.stTextInput input {
  border-radius: 50px !important;
  border: 2px solid var(--border) !important;
  background: var(--bg-card) !important;
  padding: 0.55rem 1.2rem !important;
  font-size: 0.95rem !important;
}
.stTextInput input:focus {
  border-color: var(--blue) !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
}

/* Select box */
.stSelectbox [data-baseweb="select"] > div {
  border-radius: var(--radius-sm) !important;
  border-color: var(--border) !important;
  background: var(--bg-card) !important;
}

/* Metrics */
[data-testid="metric-container"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  padding: 0.9rem 1rem !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.72rem !important; color: var(--text-lo) !important;
  font-weight: 600 !important; letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Nunito', sans-serif !important;
  font-size: 1.15rem !important; font-weight: 800 !important;
  color: var(--text) !important;
}
/* Disclaimer */
.disclaimer {
  background: #fff7ed; border: 1px solid #fed7aa;
  border-radius: var(--radius-sm); padding: 0.7rem 1rem;
  font-size: 0.78rem; color: #c2410c; margin-top: 0.8rem; line-height: 1.6;
}
hr { border-color: var(--border) !important; margin: 1rem 0 !important; }

/* Token badge */
.token-badge {
  position: fixed; top: 12px; right: 20px; z-index: 9999;
  background: rgba(99, 102, 241, 0.9); color: white;
  padding: 4px 14px; border-radius: 20px;
  font-size: 0.78em; font-weight: 600;
  backdrop-filter: blur(8px); box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

/* ═══════════════════════════════════════════════════════════════
   📱 MOBILE RESPONSIVE — 768px 以下生效
   ═══════════════════════════════════════════════════════════════ */

@media (max-width: 768px) {

  /* ── 全局：更紧凑的间距 ── */
  .block-container {
    padding: 0.5rem 0.8rem !important;
  }

  /* ── 全局文本：防止长串溢出 ── */
  .stMarkdown, .stMarkdown p, .stMarkdown li,
  .role-content, .analysis-wrap,
  [data-testid="stMarkdownContainer"] {
    overflow-wrap: break-word !important;
    word-break: break-word !important;
    hyphens: auto;
  }

  /* ── st.container(border=True) 内边距缩小 ── */
  [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
    padding: 0.6rem 0.7rem !important;
  }

  /* ── Header：缩小字号和内边距 ── */
  .app-header {
    padding: 1rem 1.2rem;
    border-radius: 12px;
    margin-bottom: 0.8rem;
  }
  .app-header h1 {
    font-size: 1.3rem;
  }
  .app-header p {
    font-size: 0.76rem;
  }
  .app-header::before {
    display: none;  /* 隐藏装饰 emoji */
  }

  /* ── 搜索栏 & 按钮：单行内输入框更大、按钮更好按 ── */
  .stTextInput input {
    font-size: 1rem !important;
    padding: 0.6rem 1rem !important;
    border-radius: 12px !important;
  }
  .stButton button {
    font-size: 0.82rem !important;
    padding: 0.55rem 0.8rem !important;
    border-radius: 12px !important;
    min-height: 44px !important;   /* iOS 推荐最小触控尺寸 */
  }

  /* ── 指标卡片 ── */
  [data-testid="metric-container"] {
    padding: 0.55rem 0.65rem !important;
    border-radius: 8px !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.62rem !important;
    letter-spacing: 0 !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 0.92rem !important;
  }

  /* ── Tabs：可滚动，不挤压 ── */
  .stTabs [data-baseweb="tab-list"] {
    border-radius: 12px !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    width: 100% !important;
    flex-wrap: nowrap !important;
  }
  .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none;
  }
  .stTabs [data-baseweb="tab"] {
    font-size: 0.75rem !important;
    padding: 5px 12px !important;
    white-space: nowrap !important;
    flex-shrink: 0 !important;
  }

  /* ── 角色卡片：更紧凑 ── */
  .role-card {
    padding: 0.9rem 1rem;
    border-radius: 12px;
    margin: 0.6rem 0;
  }
  .role-badge {
    font-size: 0.72rem;
    padding: 2px 10px;
  }
  .role-content {
    font-size: 0.82rem;
    line-height: 1.65;
  }

  /* ── 状态横幅 ── */
  .status-banner {
    font-size: 0.78rem;
    padding: 0.6rem 0.85rem;
    border-radius: 8px;
    flex-direction: column;
    gap: 4px;
  }

  /* ── Model badge ── */
  .model-badge {
    font-size: 0.74rem;
    padding: 3px 10px;
  }

  /* ── 分析内容中的表格：横向可滚动 ── */
  .stMarkdown table,
  [data-testid="stContainer"] table,
  [data-testid="stMarkdownContainer"] table {
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    white-space: nowrap;
    font-size: 0.76rem;
    max-width: 100%;
  }
  .stMarkdown table th,
  .stMarkdown table td,
  [data-testid="stMarkdownContainer"] th,
  [data-testid="stMarkdownContainer"] td {
    padding: 4px 8px !important;
    font-size: 0.76rem !important;
  }

  /* ── 免责声明 ── */
  .disclaimer {
    font-size: 0.72rem;
    padding: 0.55rem 0.8rem;
  }

  /* ── Plotly 图表：降低高度 ── */
  [data-testid="stPlotlyChart"] > div {
    max-height: 360px !important;
  }
  .js-plotly-plot .plotly .main-svg {
    max-height: 360px !important;
  }

  /* ── 进度条文字缩短 ── */
  [data-testid="stProgressBarLabel"] {
    font-size: 0.76rem !important;
  }

  /* ── 分析标题缩小 ── */
  h4 {
    font-size: 1rem !important;
  }

  /* ── 列布局自适应：窄屏自动堆叠 ── */
  [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 0.3rem !important;
  }
  [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
    width: 100% !important;
  }

  /* 操作按钮行：保持单行横排，类似子标签 */
  [data-testid="stHorizontalBlock"]:has(.stButton) {
    flex-wrap: nowrap !important;
    gap: 0.15rem !important;
  }
  [data-testid="stHorizontalBlock"]:has(.stButton) > div[data-testid="column"] {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    width: auto !important;
  }
  /* 按钮：紧凑风格，与上级标签区分 */
  [data-testid="stHorizontalBlock"]:has(.stButton) .stButton button {
    font-size: 0.75rem !important;
    padding: 0.3rem 0.4rem !important;
    min-height: 34px !important;
    border-radius: 20px !important;
    white-space: nowrap !important;
  }
  [data-testid="stHorizontalBlock"]:has(.stButton) .stButton button:not([kind="primary"]) {
    background: var(--bg-card) !important;
    border: 1.5px solid var(--border) !important;
    color: var(--text-mid) !important;
    box-shadow: none !important;
  }

  /* 指标卡片：每行2个 */
  [data-testid="stHorizontalBlock"]:has([data-testid="metric-container"]) > div[data-testid="column"] {
    flex: 1 1 46% !important;
    min-width: 46% !important;
  }

  /* 侧边栏宽度限制 */
  [data-testid="stSidebar"] > div:first-child {
    width: 85vw !important;
    max-width: 300px !important;
  }

  /* Token badge 移到右下角 */
  .token-badge {
    top: auto; bottom: 10px; right: 10px;
    font-size: 0.68em; padding: 3px 10px; opacity: 0.85;
  }
}

/* ═══════════════════════════════════════════════════════════════
   📱 极窄屏幕（≤480px，小屏手机竖屏）
   ═══════════════════════════════════════════════════════════════ */
@media (max-width: 480px) {
  .app-header h1 {
    font-size: 1.1rem;
  }
  .app-header p {
    font-size: 0.68rem;
  }
  .app-header {
    padding: 0.75rem 0.9rem;
  }
  .block-container {
    padding: 0.3rem 0.5rem !important;
  }
  .stTabs [data-baseweb="tab"] {
    font-size: 0.68rem !important;
    padding: 4px 8px !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 0.8rem !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.56rem !important;
  }
  .role-card {
    padding: 0.65rem 0.7rem;
  }
  .role-content {
    font-size: 0.76rem;
    line-height: 1.55;
  }
  .role-badge {
    font-size: 0.66rem;
  }
  /* 表格字号进一步缩小 */
  .stMarkdown table th,
  .stMarkdown table td,
  [data-testid="stMarkdownContainer"] th,
  [data-testid="stMarkdownContainer"] td {
    font-size: 0.7rem !important;
    padding: 3px 6px !important;
  }
  /* Plotly 图表更矮 */
  [data-testid="stPlotlyChart"] > div {
    max-height: 300px !important;
  }
  h4 {
    font-size: 0.92rem !important;
  }

  /* 极窄屏：指标完全单列 */
  [data-testid="stHorizontalBlock"]:has([data-testid="metric-container"]) > div[data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }
  /* 按钮更紧凑但保持横排 */
  [data-testid="stHorizontalBlock"]:has(.stButton) .stButton button {
    font-size: 0.68rem !important;
    padding: 0.25rem 0.3rem !important;
    min-height: 30px !important;
  }
}
</style>
""", unsafe_allow_html=True)
