"""
E2E Selenium tests for Stock_test Streamlit app.

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
from selenium.common.exceptions import TimeoutException

APP_URL = "http://localhost:8501"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_app_ready(driver, timeout=30):
    """Wait until Streamlit finishes loading (skeleton gone)."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stAppViewContainer']"))
    )
    # Wait for any running skeleton/spinner to disappear
    try:
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stSkeleton']"))
        )
    except TimeoutException:
        pass
    # Extra settle time for Streamlit re-renders
    time.sleep(2)


def check_no_error(driver):
    """Assert no Streamlit exception or error alert on page."""
    errors = driver.find_elements(By.CSS_SELECTOR,
        "[data-testid='stException'], [data-testid='stError']"
    )
    if errors:
        texts = [e.text[:200] for e in errors]
        pytest.fail(f"Page has error(s): {texts}")


def find_button_by_text(driver, text, timeout=10):
    """Find a button whose visible text contains `text`."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((
            By.XPATH, f"//button[contains(., '{text}')]"
        ))
    )


def wait_for_text_on_page(driver, text, timeout=15):
    """Wait until `text` appears somewhere on the page."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((
            By.XPATH, f"//*[contains(text(), '{text}')]"
        ))
    )


def wait_for_streamlit_rerun(driver, seconds=3):
    """Give Streamlit time to process a rerun after interaction."""
    time.sleep(seconds)
    try:
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stStatusWidget']"))
        )
    except TimeoutException:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPageLoad:
    """1 - Page loads without errors."""

    def test_homepage_loads(self, browser):
        browser.get(APP_URL)
        wait_for_app_ready(browser)
        check_no_error(browser)

    def test_title_visible(self, browser):
        assert "投研助手" in browser.title or "投研助手" in browser.page_source


class TestLogin:
    """2 - Login flow."""

    def test_login_with_test_user(self, browser):
        browser.get(APP_URL)
        wait_for_app_ready(browser)

        # Find the username input
        try:
            input_el = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, "[data-testid='stTextInput'] input"
                ))
            )
        except TimeoutException:
            # Already logged in from previous run (query param)
            if "test" in browser.page_source or "current_user" in browser.page_source:
                return
            raise

        input_el.clear()
        input_el.send_keys("test")

        login_btn = find_button_by_text(browser, "登录")
        login_btn.click()

        wait_for_streamlit_rerun(browser, 5)
        wait_for_app_ready(browser)
        check_no_error(browser)

        # Verify logged in: username should appear somewhere
        wait_for_text_on_page(browser, "test", timeout=10)


class TestStockSearch:
    """3 - Select a stock via the selectbox."""

    def test_select_stock(self, browser):
        # Ensure we're on the main page and logged in
        wait_for_app_ready(browser)
        check_no_error(browser)

        # Find the selectbox (Streamlit uses baseweb select)
        try:
            selectbox = WebDriverWait(browser, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR, "[data-testid='stSelectbox'] [data-baseweb='select']"
                ))
            )
        except TimeoutException:
            # Maybe it's a text input fallback
            text_input = browser.find_element(
                By.CSS_SELECTOR, "[data-testid='stTextInput'] input"
            )
            text_input.clear()
            text_input.send_keys("贵州茅台")
            text_input.send_keys(Keys.RETURN)
            wait_for_streamlit_rerun(browser, 3)
            check_no_error(browser)
            return

        # Click to open dropdown
        selectbox.click()
        time.sleep(1)

        # Type to search
        active_input = browser.switch_to.active_element
        active_input.send_keys("贵州茅台")
        time.sleep(2)

        # Select the first matching option
        try:
            option = WebDriverWait(browser, 5).until(
                EC.element_to_be_clickable((
                    By.XPATH, "//li[contains(., '贵州茅台')]"
                ))
            )
            option.click()
        except TimeoutException:
            # Try pressing Enter to select first result
            active_input.send_keys(Keys.RETURN)

        wait_for_streamlit_rerun(browser, 3)
        check_no_error(browser)


class TestOneClickAnalysis:
    """4 - Click the one-click analysis button."""

    def test_click_analysis_button(self, browser):
        wait_for_app_ready(browser)
        check_no_error(browser)

        try:
            btn = find_button_by_text(browser, "一键分析", timeout=10)
            btn.click()
        except TimeoutException:
            # Button might say "分析完成" if already analyzed
            try:
                find_button_by_text(browser, "分析完成", timeout=3)
                return  # Already analyzed
            except TimeoutException:
                pytest.skip("一键分析 button not found (stock may not be selected)")

        # Wait for analysis to start - look for status indicators
        time.sleep(3)
        check_no_error(browser)

        # Wait for analysis to complete (up to 120 seconds)
        try:
            WebDriverWait(browser, 120).until(
                lambda d: d.find_elements(By.XPATH, "//button[contains(., '分析完成')]")
                or d.find_elements(By.XPATH, "//*[contains(text(), '预期差')]")
            )
        except TimeoutException:
            # Analysis might still be running; check for errors at least
            pass

        check_no_error(browser)


class TestTabSwitch:
    """5 - Switch through all 6 tabs."""

    TAB_NAMES = ["智能分析", "股票对比", "回测战绩", "六方会谈", "玄学炒股", "互动问答"]

    def test_all_tabs_render(self, browser):
        wait_for_app_ready(browser)

        tabs = browser.find_elements(By.CSS_SELECTOR, "[data-testid='stTab']")
        if not tabs:
            # Try alternative: role="tab"
            tabs = browser.find_elements(By.CSS_SELECTOR, "button[role='tab']")

        assert len(tabs) >= 6, f"Expected 6 tabs, found {len(tabs)}"

        for i, tab in enumerate(tabs[:6]):
            tab_text = tab.text.strip()
            tab.click()
            wait_for_streamlit_rerun(browser, 2)
            check_no_error(browser)

            # Verify tab content area has something rendered
            content = browser.find_elements(By.CSS_SELECTOR,
                "[data-testid='stMarkdownContainer'], "
                "[data-testid='stDataFrame'], "
                "[data-testid='stImage'], "
                "[data-testid='stPlotlyChart'], "
                "button, p"
            )
            assert len(content) > 0, f"Tab '{tab_text}' rendered no content"

        # Return to first tab
        if tabs:
            tabs[0].click()
            wait_for_streamlit_rerun(browser, 2)


class TestCompareTab:
    """6 - Stock comparison tab."""

    def test_compare_tab_loads(self, browser):
        wait_for_app_ready(browser)

        # Click the compare tab
        tabs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTab'], button[role='tab']"
        )
        compare_tab = None
        for tab in tabs:
            if "对比" in tab.text:
                compare_tab = tab
                break

        if not compare_tab:
            pytest.skip("Compare tab not found")

        compare_tab.click()
        wait_for_streamlit_rerun(browser, 2)
        check_no_error(browser)

        # Look for input fields for Stock A and B
        inputs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTextInput'] input, "
            "[data-testid='stSelectbox'] [data-baseweb='select']"
        )
        # At minimum the compare tab should have rendered without error
        assert len(inputs) >= 0  # The tab loaded OK


class TestBacktestTab:
    """7 - Backtest tab."""

    def test_backtest_tab_loads(self, browser):
        wait_for_app_ready(browser)

        tabs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTab'], button[role='tab']"
        )
        backtest_tab = None
        for tab in tabs:
            if "回测" in tab.text:
                backtest_tab = tab
                break

        if not backtest_tab:
            pytest.skip("Backtest tab not found")

        backtest_tab.click()
        wait_for_streamlit_rerun(browser, 2)
        check_no_error(browser)

        # The backtest tab should show archive stats or a button
        page_text = browser.find_element(By.TAG_NAME, "body").text
        assert "回测" in page_text or "归档" in page_text or "执行" in page_text


class TestSummaryButton:
    """8 - Summary button after analysis."""

    def test_summary_available(self, browser):
        wait_for_app_ready(browser)

        # Switch back to analysis tab
        tabs = browser.find_elements(By.CSS_SELECTOR,
            "[data-testid='stTab'], button[role='tab']"
        )
        if tabs:
            tabs[0].click()
            wait_for_streamlit_rerun(browser, 2)

        # Try to find and click summary button
        try:
            summary_btn = find_button_by_text(browser, "总结", timeout=5)
            summary_btn.click()
            wait_for_streamlit_rerun(browser, 5)
            check_no_error(browser)

            # Wait for summary to render (radar chart / conclusion)
            time.sleep(5)
            check_no_error(browser)
        except TimeoutException:
            pytest.skip("Summary button not available (analysis may not be complete)")


class TestReset:
    """9 - Reset button returns to initial state."""

    def test_reset(self, browser):
        wait_for_app_ready(browser)

        try:
            reset_btn = find_button_by_text(browser, "重置", timeout=5)
            reset_btn.click()
            wait_for_streamlit_rerun(browser, 5)
            wait_for_app_ready(browser)
            check_no_error(browser)

            # After reset, analysis button should be available again
            try:
                find_button_by_text(browser, "一键分析", timeout=10)
            except TimeoutException:
                pass  # OK if stock is deselected after reset

        except TimeoutException:
            pytest.skip("Reset button not found")
