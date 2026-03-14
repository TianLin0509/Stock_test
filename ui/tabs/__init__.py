"""Tab 模块导出"""

from ui.tabs.analysis import render_analysis_tab
from ui.tabs.compare import render_compare_tab
from ui.tabs.backtest import render_backtest_tab
from ui.tabs.moe_tab import render_moe_tab
from ui.tabs.mystic import render_mystic_tab
from ui.tabs.qa import render_qa_tab

__all__ = [
    "render_analysis_tab",
    "render_compare_tab",
    "render_backtest_tab",
    "render_moe_tab",
    "render_mystic_tab",
    "render_qa_tab",
]
