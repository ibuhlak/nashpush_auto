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
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--enable-features=PushMessaging"
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

    def handle_response(response):
        nonlocal subscriber_request
        if response.url == "https://webpush.staging.push-sender.com/api/v1/subscribers/":
            subscriber_request = response
            try:
                json_response = response.json()
                response_data.update(json_response)
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа от подписчиков: {e}")

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
    assert subscriber_request is not None, "Не дождались subscribers request"
    assert response_data["uuid"], f"Поле 'uuid' пустое или отсутствует. Ответ: {response_data}"

    with open("data/test_data.py", "w") as f:
        f.write(f'uuid = "{response_data.get("uuid")}"\n')
    
# Тест 3: Проверяем, что пришло уведомление
def test_push_message(page):
    request_data = {}

    def handle_request(request):
        if request.url.endswith("callbacks/") and request.method == "POST":
            try:
                json_body = request.post_data_json
                request_data.update(json_body)
            except Exception as e:
                pytest.fail(f"Ошибка при парсинге JSON-ответа: {e}")
 
    page.context.on("request", handle_request)
    page.wait_for_timeout(600000)


    # minutes = 0
    # while request_data == {} and minutes < 20:
    #     page.mouse.move(200, 100)
    #     page.wait_for_timeout(60000)
    #     minutes += 1
    #     print(f"waiting for {minutes} minutes")
    #     page.mouse.move(100, 200)

    assert request_data, f"Request data is empty, request was not sent = {request_data}"
    print(f"тело реквеста: {request_data}")

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