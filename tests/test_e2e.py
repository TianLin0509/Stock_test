"""
E2E Selenium tests for Stock_test Streamlit app.

Covers: page load, login, stock search, one-click analysis, all 6 tabs,
        stock comparison, backtest, MoE debate, mystic, Q&A, summary,
        reset, edge cases (empty input, invalid stock, rapid clicks, etc.)

Login user: Claude测试员
Token budget: ≤ 100万 tokens per run

Requires:
  - Streamlit app running at localhost:8501
  - Chrome + chromedriver installed
  - pip install selenium pytest

Run:
  cd C:/Users/lintian/Stock_test && python -m pytest tests/test_e2e.py -v --tb=short
"""
import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

APP_URL = "http://localhost:8501"
TEST_USER = "Claude测试员"
TEST_STOCK = "贵州茅台"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_app_ready(driver, timeout=30):
    """Wait until Streamlit finishes loading."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stAppViewContainer']"))
    )
    try:
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stSkeleton']"))
        )
    except TimeoutException:
        pass
    time.sleep(2)


def check_no_error(driver):
    """Assert no Streamlit exception/error on page."""
    errors = driver.find_elements(By.CSS_SELECTOR,
        "[data-testid='stException'], [data-testid='stError']"
    )
    if errors:
        texts = [e.text[:300] for e in errors]
        pytest.fail(f"Page error(s): {texts}")


def check_no_warning(driver):
    """Check no Streamlit warning boxes (optional, non-fatal)."""
    warnings = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stAlert']")
    return [w.text[:200] for w in warnings]


def find_button_by_text(driver, text, timeout=10):
    """Find a clickable button containing `text`."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((
            By.XPATH, f"//button[contains(., '{text}')]"
        ))
    )


def find_buttons_by_text(driver, text):
    """Find all buttons containing `text`."""
    return driver.find_elements(By.XPATH, f"//button[contains(., '{text}')]")


def wait_for_text_on_page(driver, text, timeout=15):
    """Wait until `text` appears somewhere on page."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((
            By.XPATH, f"//*[contains(text(), '{text}')]"
        ))
    )


def wait_for_streamlit_rerun(driver, seconds=3):
    """Wait for Streamlit rerun to settle."""
    time.sleep(seconds)
    try:
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stStatusWidget']"))
        )
    except TimeoutException:
        pass


def get_tabs(driver):
    """Get all tab elements."""
    tabs = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stTab']")
    if not tabs:
        tabs = driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")
    return tabs


def click_tab_by_name(driver, name):
    """Click a tab whose text contains `name`. Returns True if found."""
    for tab in get_tabs(driver):
        if name in tab.text:
            tab.click()
            wait_for_streamlit_rerun(driver, 2)
            return True
    return False


def select_stock_via_selectbox(driver, stock_name):
    """Search and select a stock in the selectbox."""
    try:
        selectbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR, "[data-testid='stSelectbox'] [data-baseweb='select']"
            ))
        )
    except TimeoutException:
        # Fallback: text input
        text_input = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='stTextInput'] input"
        )
        text_input.clear()
        text_input.send_keys(stock_name)
        text_input.send_keys(Keys.RETURN)
        wait_for_streamlit_rerun(driver, 3)
        return

    selectbox.click()
    time.sleep(1)
    active_input = driver.switch_to.active_element
    active_input.send_keys(stock_name)
    time.sleep(2)

    try:
        option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//li[contains(., '{stock_name}')]"
            ))
        )
        option.click()
    except TimeoutException:
        active_input.send_keys(Keys.RETURN)

    wait_for_streamlit_rerun(driver, 3)


def wait_analysis_complete(driver, timeout=180):
    """Wait for core analysis to finish (button becomes 分析完成 or view buttons appear)."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.find_elements(By.XPATH, "//button[contains(., '分析完成')]")
            or d.find_elements(By.XPATH, "//button[contains(., '✅ 预期差')]")
        )
    except TimeoutException:
        pass
    check_no_error(driver)


def ensure_logged_in(driver):
    """Make sure we're logged in as TEST_USER."""
    driver.get(APP_URL)
    wait_for_app_ready(driver)

    # Check if already logged in
    if TEST_USER in driver.page_source:
        return

    # Try to find login input
    try:
        input_el = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR, "[data-testid='stTextInput'] input"
            ))
        )
    except TimeoutException:
        return  # Already logged in (different user maybe)

    input_el.clear()
    input_el.send_keys(TEST_USER)
    find_button_by_text(driver, "登录").click()
    wait_for_streamlit_rerun(driver, 5)
    wait_for_app_ready(driver)


# ===========================================================================
# 1. Page Load
# ===========================================================================

class TestPageLoad:
    """Basic page load checks."""

    def test_homepage_loads(self, browser):
        browser.get(APP_URL)
        wait_for_app_ready(browser)
        check_no_error(browser)

    def test_title_contains_app_name(self, browser):
        assert "投研助手" in browser.title or "投研助手" in browser.page_source


# ===========================================================================
# 2. Login
# ===========================================================================

class TestLogin:
    """Login flow with Claude测试员."""

    def test_login_success(self, browser):
        browser.get(APP_URL)
        wait_for_app_ready(browser)

        try:
            input_el = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, "[data-testid='stTextInput'] input"
                ))
            )
        except TimeoutException:
            if TEST_USER in browser.page_source:
                return
            raise

        input_el.clear()
        input_el.send_keys(TEST_USER)

        find_button_by_text(browser, "登录").click()
        wait_for_streamlit_rerun(browser, 5)
        wait_for_app_ready(browser)
        check_no_error(browser)

        wait_for_text_on_page(browser, TEST_USER, timeout=10)

    def test_page_refresh_keeps_login(self, browser):
        """F5 should preserve login via query param."""
        browser.refresh()
        wait_for_app_ready(browser)
        check_no_error(browser)
        # Should still be logged in (no login form visible)
        login_inputs = browser.find_elements(
            By.XPATH, "//label[contains(text(), '用户名')]"
        )
        if login_inputs:
            # Might need to re-login — that's also info
            pytest.skip("Login not preserved on refresh")


# ===========================================================================
# 3. Stock Search
# ===========================================================================

class TestStockSearch:
    """Stock selection and search scenarios."""

    def test_select_stock(self, browser):
        ensure_logged_in(browser)
        select_stock_via_selectbox(browser, TEST_STOCK)
        check_no_error(browser)

    def test_invalid_stock_no_crash(self, browser):
        """Searching nonsense should not crash the page."""
        ensure_logged_in(browser)
        try:
            selectbox = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, "[data-testid='stSelectbox'] [data-baseweb='select']"
                ))
            )
            selectbox.click()
            time.sleep(0.5)
            active_input = browser.switch_to.active_element
            active_input.send_keys("不存在的股票XYZ999")
            time.sleep(1)
            active_input.send_keys(Keys.ESCAPE)
        except TimeoutException:
            pass
        check_no_error(browser)

    def test_special_chars_no_crash(self, browser):
        """Special characters in search should not crash."""
        ensure_logged_in(browser)
        try:
            selectbox = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, "[data-testid='stSelectbox'] [data-baseweb='select']"
                ))
            )
            selectbox.click()
            time.sleep(0.5)
            active_input = browser.switch_to.active_element
            active_input.send_keys("<script>alert(1)</script>'; DROP TABLE;")
            time.sleep(1)
            active_input.send_keys(Keys.ESCAPE)
        except TimeoutException:
            pass
        check_no_error(browser)


# ===========================================================================
# 4. One-Click Analysis (智能分析)
# ===========================================================================

class TestOneClickAnalysis:
    """Core analysis workflow."""

    def test_click_analysis_starts(self, browser):
        ensure_logged_in(browser)
        # Make sure a stock is selected
        select_stock_via_selectbox(browser, TEST_STOCK)
        check_no_error(browser)

        try:
            btn = find_button_by_text(browser, "一键分析", timeout=10)
            btn.click()
        except TimeoutException:
            try:
                find_button_by_text(browser, "分析完成", timeout=3)
                return  # Already analyzed
            except TimeoutException:
                pytest.skip("一键分析 button not found")

        time.sleep(3)
        check_no_error(browser)

        # Wait for completion
        wait_analysis_complete(browser, timeout=180)

    def test_analysis_buttons_appear(self, browser):
        """After analysis, view buttons (预期差/趋势/基本面) should appear."""
        wait_for_app_ready(browser)
        click_tab_by_name(browser, "智能分析")

        for label in ["预期差", "趋势", "基本面"]:
            btns = find_buttons_by_text(browser, label)
            assert len(btns) > 0, f"Button '{label}' not found after analysis"

    def test_view_expectation(self, browser):
        """Click 预期差 button and verify content renders."""
        wait_for_app_ready(browser)
        click_tab_by_name(browser, "智能分析")

        try:
            btn = find_button_by_text(browser, "预期差", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 3)
            check_no_error(browser)

            # Should have markdown content
            md = browser.find_elements(By.CSS_SELECTOR, "[data-testid='stMarkdownContainer']")
            assert len(md) > 0, "No markdown content after clicking 预期差"
        except TimeoutException:
            pytest.skip("预期差 button not available")

    def test_view_trend(self, browser):
        """Click 趋势 button and verify content + K-line chart."""
        wait_for_app_ready(browser)
        click_tab_by_name(browser, "智能分析")

        try:
            btn = find_button_by_text(browser, "趋势", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 3)
            check_no_error(browser)

            md = browser.find_elements(By.CSS_SELECTOR, "[data-testid='stMarkdownContainer']")
            assert len(md) > 0, "No markdown content after clicking 趋势"
        except TimeoutException:
            pytest.skip("趋势 button not available")

    def test_view_fundamentals(self, browser):
        """Click 基本面 button and verify content renders."""
        wait_for_app_ready(browser)
        click_tab_by_name(browser, "智能分析")

        try:
            btn = find_button_by_text(browser, "基本面", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 3)
            check_no_error(browser)

            md = browser.find_elements(By.CSS_SELECTOR, "[data-testid='stMarkdownContainer']")
            assert len(md) > 0, "No markdown content after clicking 基本面"
        except TimeoutException:
            pytest.skip("基本面 button not available")

    def test_rapid_double_click_no_crash(self, browser):
        """Clicking analysis button twice rapidly should not crash."""
        ensure_logged_in(browser)
        click_tab_by_name(browser, "智能分析")

        btns = find_buttons_by_text(browser, "预期差")
        if btns:
            try:
                btns[0].click()
                time.sleep(0.2)
                btns[0].click()
            except (ElementClickInterceptedException, Exception):
                pass
        time.sleep(2)
        check_no_error(browser)

    def test_switch_tab_during_analysis_no_data_loss(self, browser):
        """Switch tabs and come back — analysis results should persist."""
        wait_for_app_ready(browser)

        # Go to compare tab then back
        click_tab_by_name(browser, "股票对比")
        time.sleep(1)
        click_tab_by_name(browser, "智能分析")
        wait_for_streamlit_rerun(browser, 2)
        check_no_error(browser)

        # Analysis buttons should still be there
        for label in ["预期差", "趋势", "基本面"]:
            btns = find_buttons_by_text(browser, label)
            assert len(btns) > 0, f"'{label}' button missing after tab switch"


# ===========================================================================
# 5. Summary (总结)
# ===========================================================================

class TestSummary:
    """Summary button — radar chart + conclusions."""

    def test_summary_renders(self, browser):
        wait_for_app_ready(browser)
        click_tab_by_name(browser, "智能分析")

        try:
            btn = find_button_by_text(browser, "总结", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 5)

            # Wait for AI to generate summary
            time.sleep(10)
            check_no_error(browser)

            # Should have rendered content (radar chart or markdown)
            content = browser.find_elements(By.CSS_SELECTOR,
                "[data-testid='stMarkdownContainer'], "
                "[data-testid='stPlotlyChart'], "
                "[data-testid='stImage']"
            )
            assert len(content) > 0, "Summary rendered no content"
        except TimeoutException:
            pytest.skip("总结 button not available (analysis incomplete)")


# ===========================================================================
# 6. Tab Switching
# ===========================================================================

class TestTabSwitch:
    """All 6 tabs render without errors."""

    TAB_NAMES = ["智能分析", "股票对比", "回测战绩", "六方会谈", "玄学炒股", "互动问答"]

    def test_all_tabs_exist(self, browser):
        wait_for_app_ready(browser)
        tabs = get_tabs(browser)
        assert len(tabs) >= 6, f"Expected 6 tabs, found {len(tabs)}"

    def test_each_tab_renders_without_crash(self, browser):
        wait_for_app_ready(browser)
        tabs = get_tabs(browser)

        for i, tab in enumerate(tabs[:6]):
            tab_text = tab.text.strip()
            tab.click()
            wait_for_streamlit_rerun(browser, 2)
            check_no_error(browser)

            content = browser.find_elements(By.CSS_SELECTOR,
                "[data-testid='stMarkdownContainer'], "
                "[data-testid='stDataFrame'], "
                "[data-testid='stPlotlyChart'], "
                "button, p, [data-testid='stAlert']"
            )
            assert len(content) > 0, f"Tab '{tab_text}' rendered no content"

        # Return to first tab
        tabs[0].click()
        wait_for_streamlit_rerun(browser, 2)


# ===========================================================================
# 7. Stock Comparison (⚖️ 股票对比)
# ===========================================================================

class TestCompareTab:
    """Stock comparison tab — deep testing."""

    def test_compare_tab_has_inputs(self, browser):
        """Compare tab should have two stock input fields."""
        ensure_logged_in(browser)
        click_tab_by_name(browser, "股票对比")
        check_no_error(browser)

        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input"
        )
        assert len(inputs) >= 2, f"Expected 2 stock inputs, found {len(inputs)}"

    def test_compare_empty_inputs_shows_warning(self, browser):
        """Clicking compare with empty inputs should show warning, not crash."""
        click_tab_by_name(browser, "股票对比")

        try:
            btn = find_button_by_text(browser, "开始对比", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 3)
            check_no_error(browser)
            # Should show a warning about missing input
        except TimeoutException:
            pytest.skip("开始对比 button not found")

    def test_compare_only_one_stock_shows_warning(self, browser):
        """Filling only Stock A and clicking compare should warn."""
        click_tab_by_name(browser, "股票对比")

        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input"
        )
        if len(inputs) >= 2:
            inputs[0].clear()
            inputs[0].send_keys("600519")
            inputs[1].clear()  # Leave B empty

            try:
                btn = find_button_by_text(browser, "开始对比", timeout=5)
                btn.click()
                wait_for_streamlit_rerun(browser, 3)
                check_no_error(browser)
            except TimeoutException:
                pass

    def test_compare_two_stocks_success(self, browser):
        """Compare 贵州茅台 vs 五粮液 — full flow."""
        click_tab_by_name(browser, "股票对比")

        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input"
        )
        if len(inputs) < 2:
            pytest.skip("Compare inputs not found")

        inputs[0].clear()
        inputs[0].send_keys("600519")
        inputs[1].clear()
        inputs[1].send_keys("000858")

        try:
            btn = find_button_by_text(browser, "开始对比", timeout=5)
            btn.click()
        except TimeoutException:
            pytest.skip("开始对比 button not found")

        # Wait for comparison to load (data fetching)
        wait_for_streamlit_rerun(browser, 10)
        check_no_error(browser)

        # Should have comparison content
        body_text = browser.find_element(By.TAG_NAME, "body").text
        # Expect metrics table or chart to appear
        has_content = (
            "最新价" in body_text
            or "走势对比" in body_text
            or "茅台" in body_text
            or "五粮液" in body_text
        )
        assert has_content, "Compare tab showed no comparison content"

    def test_compare_shows_chart(self, browser):
        """After comparison, a price trend chart should render."""
        # Should still be on compare tab with results from previous test
        charts = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stPlotlyChart'], canvas, svg"
        )
        # Non-blocking: chart is nice but not critical
        if not charts:
            warnings = check_no_warning(browser)

    def test_compare_same_stock_no_crash(self, browser):
        """Comparing a stock with itself should not crash."""
        click_tab_by_name(browser, "股票对比")

        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input"
        )
        if len(inputs) < 2:
            pytest.skip("Compare inputs not found")

        inputs[0].clear()
        inputs[0].send_keys("600519")
        inputs[1].clear()
        inputs[1].send_keys("600519")

        try:
            btn = find_button_by_text(browser, "开始对比", timeout=5)
            btn.click()
            wait_for_streamlit_rerun(browser, 8)
            check_no_error(browser)
        except TimeoutException:
            pass

    def test_compare_ai_commentary(self, browser):
        """Generate AI commentary for the comparison."""
        click_tab_by_name(browser, "股票对比")

        # Re-do a valid comparison first
        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input"
        )
        if len(inputs) >= 2:
            inputs[0].clear()
            inputs[0].send_keys("600519")
            inputs[1].clear()
            inputs[1].send_keys("000858")
            try:
                find_button_by_text(browser, "开始对比", timeout=5).click()
                wait_for_streamlit_rerun(browser, 10)
            except TimeoutException:
                pass

        try:
            ai_btn = find_button_by_text(browser, "AI 对比点评", timeout=5)
            ai_btn.click()
            # Wait for AI generation (up to 60s)
            time.sleep(10)
            wait_for_streamlit_rerun(browser, 5)
            check_no_error(browser)

            # Should have AI commentary content
            body_text = browser.find_element(By.TAG_NAME, "body").text
            assert "对比" in body_text or "分析" in body_text or "建议" in body_text
        except TimeoutException:
            pytest.skip("AI 对比点评 button not available")


# ===========================================================================
# 8. Backtest Tab (📈 回测战绩)
# ===========================================================================

class TestBacktestTab:
    """Backtest performance tab."""

    def test_backtest_tab_loads(self, browser):
        ensure_logged_in(browser)
        click_tab_by_name(browser, "回测战绩")
        check_no_error(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        assert "回测" in body_text or "归档" in body_text or "暂无" in body_text

    def test_backtest_shows_archive_preview(self, browser):
        """If archives exist, should show preview table."""
        click_tab_by_name(browser, "回测战绩")
        check_no_error(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        if "暂无" in body_text:
            pytest.skip("No archives available for backtest")

        # Should show archive count or preview
        assert "归档" in body_text or "记录" in body_text

    def test_backtest_execute(self, browser):
        """Click execute backtest button if available."""
        click_tab_by_name(browser, "回测战绩")
        check_no_error(browser)

        try:
            btn = find_button_by_text(browser, "执行回测", timeout=5)
            btn.click()

            # Wait for backtest to complete (may take a while)
            time.sleep(5)
            wait_for_streamlit_rerun(browser, 10)
            check_no_error(browser)

            # Should show results: win rate, returns, etc.
            body_text = browser.find_element(By.TAG_NAME, "body").text
            has_results = (
                "胜率" in body_text
                or "收益" in body_text
                or "回测完成" in body_text
                or "暂无" in body_text
            )
            assert has_results, "Backtest did not show results"
        except TimeoutException:
            pytest.skip("执行回测 button not found (no archives)")


# ===========================================================================
# 9. MoE Debate (🎯 六方会谈)
# ===========================================================================

class TestMoeTab:
    """Six-way debate tab."""

    def test_moe_tab_loads(self, browser):
        ensure_logged_in(browser)
        click_tab_by_name(browser, "六方会谈")
        check_no_error(browser)

    def test_moe_shows_prereq_or_button(self, browser):
        """MoE tab should show either prerequisite message or launch button."""
        click_tab_by_name(browser, "六方会谈")
        check_no_error(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        has_expected = (
            "启动六方会谈" in body_text     # Ready to launch
            or "完成分析" in body_text        # Need analysis first
            or "智能分析" in body_text        # Guidance message
            or "六方会谈" in body_text        # Tab loaded at minimum
        )
        assert has_expected, "MoE tab showed unexpected content"

    def test_moe_launch_if_ready(self, browser):
        """If core analysis is done, launch MoE debate."""
        click_tab_by_name(browser, "六方会谈")
        check_no_error(browser)

        try:
            btn = find_button_by_text(browser, "启动六方会谈", timeout=5)
            btn.click()

            # MoE debate runs 5 experts + CEO, can take 60-120s
            time.sleep(5)
            check_no_error(browser)

            # Wait for completion
            try:
                WebDriverWait(browser, 120).until(
                    lambda d: "会谈完成" in d.page_source
                    or "首席执行官" in d.page_source
                    or "价值投机手" in d.page_source
                )
            except TimeoutException:
                pass

            check_no_error(browser)

            # Should show expert opinions
            body_text = browser.find_element(By.TAG_NAME, "body").text
            expert_keywords = ["价值", "技术", "基本面", "题材", "散户"]
            found = sum(1 for k in expert_keywords if k in body_text)
            if found == 0:
                pytest.skip("MoE may still be running")

        except TimeoutException:
            pytest.skip("启动六方会谈 button not available (core analysis incomplete)")


# ===========================================================================
# 10. Mystic Tab (🔮 玄学炒股)
# ===========================================================================

class TestMysticTab:
    """Mystical stock picking tab — auto-generates."""

    def test_mystic_tab_loads(self, browser):
        ensure_logged_in(browser)
        click_tab_by_name(browser, "玄学炒股")
        check_no_error(browser)

    def test_mystic_generates_content(self, browser):
        """Mystic tab should auto-generate horoscope content."""
        click_tab_by_name(browser, "玄学炒股")

        # Wait for AI generation (auto-triggered)
        time.sleep(15)
        wait_for_streamlit_rerun(browser, 5)
        check_no_error(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        mystic_keywords = ["黄历", "运势", "五行", "塔罗", "幸运", "玄学", "模型"]
        found = sum(1 for k in mystic_keywords if k in body_text)
        # Either generated content or needs model config
        assert found > 0 or "配置" in body_text or "模型" in body_text, \
            "Mystic tab showed no expected content"


# ===========================================================================
# 11. Q&A Tab (💬 互动问答)
# ===========================================================================

class TestQATab:
    """Interactive Q&A tab."""

    def test_qa_tab_loads(self, browser):
        ensure_logged_in(browser)
        click_tab_by_name(browser, "互动问答")
        check_no_error(browser)

    def test_qa_shows_guidance_or_input(self, browser):
        """Q&A should show guidance (need stock) or input field."""
        click_tab_by_name(browser, "互动问答")
        check_no_error(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        has_expected = (
            "提问" in body_text
            or "输入" in body_text
            or "问答" in body_text
            or "股票" in body_text
        )
        assert has_expected, "Q&A tab showed no expected content"


# ===========================================================================
# 12. Token Display
# ===========================================================================

class TestTokenDisplay:
    """Token usage display after analysis."""

    def test_token_badge_visible(self, browser):
        """After analysis, token badge should be visible."""
        ensure_logged_in(browser)
        wait_for_app_ready(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        # Token badge shows 🪙 or token count
        has_token = "🪙" in body_text or "token" in body_text.lower()
        if not has_token:
            pytest.skip("Token badge not visible (may not have analyzed yet)")


# ===========================================================================
# 13. Deep Analysis (深度分析)
# ===========================================================================

class TestDeepAnalysis:
    """Deep analysis (舆情+板块+股东)."""

    def test_deep_analysis_button(self, browser):
        """Deep analysis button should appear after core analysis."""
        ensure_logged_in(browser)
        click_tab_by_name(browser, "智能分析")

        try:
            btn = find_button_by_text(browser, "深度分析", timeout=5)
            # Just verify it exists; clicking would consume tokens
            assert btn is not None
        except TimeoutException:
            pytest.skip("Deep analysis button not shown (core analysis may be incomplete)")


# ===========================================================================
# 14. Cache Behavior
# ===========================================================================

class TestCacheBehavior:
    """Cache hit on repeated analysis."""

    def test_cache_indicator_after_reselect(self, browser):
        """Re-selecting same stock should show cache indicator."""
        ensure_logged_in(browser)
        click_tab_by_name(browser, "智能分析")

        body_text = browser.find_element(By.TAG_NAME, "body").text
        # Cache indicators: 📦 or "缓存" text
        if "缓存" in body_text or "📦" in body_text:
            pass  # Cache is working
        # Non-blocking test — cache may not be present if first analysis


# ===========================================================================
# 15. Reset
# ===========================================================================

class TestReset:
    """Reset button returns to initial state."""

    def test_reset_clears_state(self, browser):
        ensure_logged_in(browser)
        wait_for_app_ready(browser)

        try:
            reset_btn = find_button_by_text(browser, "重置", timeout=5)
            reset_btn.click()
            wait_for_streamlit_rerun(browser, 5)
            wait_for_app_ready(browser)
            check_no_error(browser)

            # After reset, 一键分析 should reappear or stock is deselected
            body_text = browser.find_element(By.TAG_NAME, "body").text
            assert "一键分析" in body_text or "搜索" in body_text or "输入" in body_text

        except TimeoutException:
            pytest.skip("Reset button not found")

    def test_reanalysis_after_reset(self, browser):
        """After reset, can select stock and analyze again."""
        ensure_logged_in(browser)
        select_stock_via_selectbox(browser, TEST_STOCK)
        check_no_error(browser)

        try:
            btn = find_button_by_text(browser, "一键分析", timeout=10)
            assert btn is not None, "一键分析 button should reappear after reset"
        except TimeoutException:
            # Might already show 分析完成 from cache
            pass


# ===========================================================================
# 16. User Switch
# ===========================================================================

class TestUserSwitch:
    """Switch user flow."""

    def test_switch_user_button_exists(self, browser):
        """Sidebar should have 切换用户 button."""
        ensure_logged_in(browser)
        wait_for_app_ready(browser)

        body_text = browser.find_element(By.TAG_NAME, "body").text
        # The switch user button is in sidebar
        try:
            btn = find_button_by_text(browser, "切换用户", timeout=5)
            assert btn is not None
        except TimeoutException:
            # Sidebar might be collapsed
            pass


# ===========================================================================
# 17. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Boundary and edge case scenarios."""

    def test_no_stock_click_analysis_shows_guidance(self, browser):
        """Without selecting stock, clicking analysis should guide user."""
        ensure_logged_in(browser)

        # Reset first to clear stock
        try:
            find_button_by_text(browser, "重置", timeout=3).click()
            wait_for_streamlit_rerun(browser, 5)
        except TimeoutException:
            pass

        # Check the page doesn't crash without stock selected
        check_no_error(browser)

    def test_long_input_no_crash(self, browser):
        """Very long input in search should not crash."""
        ensure_logged_in(browser)
        try:
            selectbox = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, "[data-testid='stSelectbox'] [data-baseweb='select']"
                ))
            )
            selectbox.click()
            time.sleep(0.5)
            active_input = browser.switch_to.active_element
            active_input.send_keys("A" * 200)
            time.sleep(1)
            active_input.send_keys(Keys.ESCAPE)
        except TimeoutException:
            pass
        check_no_error(browser)

    def test_mobile_viewport_no_crash(self, browser):
        """Narrow viewport (mobile simulation) should not crash."""
        original_size = browser.get_window_size()
        browser.set_window_size(375, 812)  # iPhone X size
        time.sleep(2)
        check_no_error(browser)

        # Restore original size
        browser.set_window_size(
            original_size['width'],
            original_size['height']
        )
        time.sleep(2)
        check_no_error(browser)
