import os
import shutil
import pytest
from data.config import Config
from playwright.sync_api import sync_playwright

USER_DATA_DIR = "user_data"

@pytest.fixture(scope="session")
def page():
    """Одна фикстура на сессию: браузер + страница"""
    playwright = sync_playwright().start()
    browser_context = playwright.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )
    page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

    yield page

    browser_context.clear_cookies()
    browser_context.clear_permissions()
    browser_context.close()
    playwright.stop()

    if os.path.exists(USER_DATA_DIR):
        shutil.rmtree(USER_DATA_DIR)


def test_blocked_page(page):
    request_data = {}

    page.add_init_script("""
    Object.defineProperty(Notification, 'permission', {
        get: () => 'denied'
    });
    """)
   
    def handle_request(request):
        if request.url == "https://gateway.staging.push-sender.com/api/v1/channels/events/":
            try:
                json_body = request.post_data_json
                request_data.update(json_body)
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа: {e}")
    page.on("request", handle_request)
    page.goto(Config.SUBSCRIPTION_URL, wait_until="networkidle")

    assert request_data, "Request data is empty, request was not sent"
    assert request_data.get("event") == "permission_blocked", "Expected event 'permission_blocked' not found in request data"

    