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
    # Переменная для отслеживания запроса на подписку
    subscriber_request = None
    response_data = {}

    # Обработчик для ответа на подписку
    def handle_response(response):
        nonlocal subscriber_request
        if response.url == "https://webpush.staging.push-sender.com/api/v1/subscribers/":
            subscriber_request = response
            try:
                json_response = response.json()
                response_data.update(json_response)
                print(f"Получен ответ от запроса на подписку: {response_data}")  # Печать для отладки
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа от подписчиков: {e}")

    page.on("response", handle_response)  # Перехватываем ответы

    # Переход на страницу, которая вызывает подписку
    page.goto(Config.SUBSCRIPTION_URL, wait_until="networkidle")

    permission = page.evaluate("Notification.permission")
    assert permission == "granted", f"Подписка не удалась! permission = {permission}"

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

    page.wait_for_timeout(7000)  # Даем больше времени для обработки запроса

    # Проверяем, был ли отправлен запрос на подписку
    assert subscriber_request is not None, "Не дождались subscribers"

    # Проверяем, что в ответе есть поле 'uuid'
    assert "uuid" in response_data, f"Ответ от подписчиков не содержит поле 'uuid'. Ответ: {response_data}"
    assert response_data["uuid"], f"Поле 'uuid' пустое или отсутствует. Ответ: {response_data}"

    # Печатаем полученные данные для отладки
    print(f"Response Data: {response_data}")


