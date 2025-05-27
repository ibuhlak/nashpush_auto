import os
import re
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
            "--no-sandbox"
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

# Тест 1: Проверяем code-snippet на channel_id
def test_code_snippet_request(page):
    response_data = {}

    def handle_response(response):
        if response.url == "https://manager.staging.push-sender.com/api/v1/code-snippet/":
            try:
                json_body = response.json()
                response_data.update(json_body)
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа: {e}")

    page.on("response", handle_response)
    page.goto(Config.SUBSCRIPTION_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)

    assert "channel_id" in response_data, "Ответ code-snippet не содержит поле channel_id"
    assert response_data["channel_id"] == Config.CHANNEL_ID, f"channel_id должен быть {Config.CHANNEL_ID}, но пришло: {response_data.get('channel_id')}"

# Тест 2: Проверяем что выдано разрешение на пуши, что браузер совершил подписку и что юзеру выдан uuid
def test_push_notification_subscription(page):
    
    subscriber_request = None
    response_data = {}
    found_messages = False

    def handle_response(response):
        nonlocal subscriber_request
        if response.url == "https://webpush.staging.push-sender.com/api/v1/subscribers/":
            subscriber_request = response
            try:
                json_response = response.json()
                response_data.update(json_response)
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа от подписчиков: {e}")

    def handle_console(msg):
        nonlocal found_messages
        if "subscribed" in msg.text:
            found_messages = True

    page.on("console", handle_console)
    page.on("response", handle_response) 
    page.goto(Config.SUBSCRIPTION_URL, wait_until="networkidle")

    permission = page.evaluate("Notification.permission")
    assert permission == "granted", f"Разрешения на подписку нет!! permission = {permission}"

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

    page.wait_for_timeout(5000)  # Даем больше времени для обработки запроса

    # Проверяем, был ли отправлен запрос на подписку
    assert found_messages, "Не найдено сообщений в консоли с текстом 'subscribed'. Возможно, подписка не была успешно выполнена."
    assert subscriber_request is not None, "Не дождались subscribers request"
    assert response_data["uuid"], f"Поле 'uuid' пустое или отсутствует. Ответ: {response_data}"

    with open("data/test_data.py", "w") as f:
        f.write(f'uuid = "{response_data.get("uuid")}"\n')
    
# Тест 3: Проверяем, что пришло уведомление
def test_push_message(page):
    timestamp_found = {"value": None}

    def handle_console(msg):
        text = msg.text.strip()
        # Проверим, что строка состоит только из 13 цифр (мс timestamp)
        if re.match(r"^\d{13}$", text):
            timestamp_found["value"] = text
            print(f"✅ Получено уведомление в {text}")

    page.context.on("console", handle_console)

    for _ in range(300):  # ждём максимум 5 минуты
        if timestamp_found["value"]:
            break
        page.mouse.move(150, 150)
        page.wait_for_timeout(1000)

    assert timestamp_found["value"], "❌ Уведомление не пришло — timestamp не зафиксирован"

# Тест 4: Эмулируем блок на подписку и проверяем что ушел постбек
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