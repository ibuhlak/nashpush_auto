import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="session")
def page():
    """Запускаем браузер в обычном режиме (не инкогнито) с разрешениями"""
    playwright = sync_playwright().start()
    browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir="user_data",
        headless=False,
    
    )
    page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

    yield page

    playwright.stop()

def test_push_notification_unsubscription(page):
    page.goto("https://demo.staging.almightypush.com/Ihor_demo/", wait_until="networkidle")
    # page.wait_for_timeout(5000)
    permission = page.evaluate("Notification.permission")

    assert permission == "default", "Отписка от пушей не удалась!"
