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
        headless=False,
        args=[
            "--disable-features=PermissionsPrompt",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )
    browser_context.grant_permissions(["notifications"])
    page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

    yield page

    browser_context.clear_cookies()
    browser_context.clear_permissions()
    browser_context.close()
    playwright.stop()

    if os.path.exists(USER_DATA_DIR):
        shutil.rmtree(USER_DATA_DIR)


def test_push_notification_subscription(page):

    page.goto(Config.SUBSCRIPTION_URL, wait_until="networkidle")
    
    permission = page.evaluate("Notification.permission")

    # проверяем что разрешение на пуши выдано
    assert permission == "granted", f"Подписка не удалась! permission = {permission}"

    # Ждем, пока браузер подпишется на пуши и проверяем, что подписка успешна
    is_subscribed = page.evaluate("""
        () => new Promise((resolve, reject) => {
            const interval = setInterval(() => {
                navigator.serviceWorker.getRegistration()
                    .then(reg => reg?.pushManager.getSubscription())
                    .then(sub => {
                        if (sub) {
                            clearInterval(interval);
                            resolve(true);
                        }
                    }).catch(reject);
            }, 500);
        })
    """)
    assert is_subscribed, "Подписка не удалась! is_subscribed = False"

    page.wait_for_timeout(5000) #ждем пока улетят все реквесты