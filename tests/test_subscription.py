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
def test_push_received_by_callback(page):
    print("⏳ Ждём POST-запрос на callbacks/")

    def is_callback_post_request(request):
        return request.url.startswith("https://callbacks-api.staging.push-sender.com/api/v1/subscribers/") \
            and request.url.endswith("/callbacks/") and request.method == "POST"

    with page.expect_request(is_callback_post_request, timeout=60000) as request_info:
        # Эмулируем активность, чтобы триггерить доставку пуша
        for _ in range(10):
            page.mouse.move(200, 100)
            page.wait_for_timeout(1000)

    request = request_info.value

    try:
        request_data = request.post_data_json
    except Exception as e:
        pytest.fail(f"Ошибка при получении тела запроса: {e}")

    assert request_data, "❌ Колбэк-пост не был отправлен"
    print(f"✅ Уловили POST на callbacks/: {request_data}")

# Тест 4

def test_service_worker_sent_callback():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Получаем список всех таргетов
        cdp = context.new_cdp_session(page)
        cdp.send("Target.setDiscoverTargets", {"discover": True})
        targets = cdp.send("Target.getTargets")["targetInfos"]

        # Ищем service worker
        sw_target = next((t for t in targets if t["type"] == "service_worker"), None)
        assert sw_target, "❌ Service Worker не найден"

        # Подключаемся к воркеру по его targetId
        attach_result = cdp.send("Target.attachToTarget", {
            "targetId": sw_target["targetId"],
            "flatten": True
        })
        session_id = attach_result["sessionId"]

        # Отправляем команды CDP через attached сессию
        # Включаем Network
        cdp.send("Network.enable", {}, session_id=session_id)

        # Слушаем события сетевых запросов
        found = False

        def handle_event(params):
            nonlocal found
            url = params["request"]["url"]
            method = params["request"]["method"]
            if (
                url.startswith("https://callbacks-api.staging.push-sender.com/api/v1/subscribers/")
                and url.endswith("/callbacks/")
                and method == "POST"
            ):
                print("✅ Найден POST от Service Worker:", url)
                found = True

        cdp.on("Network.requestWillBeSent", handle_event)

        # Действие, которое вызывает push или отправку callback
        print("📦 Ждём 60 сек, чтобы воркер сделал сетевой запрос...")
        page.wait_for_timeout(120000)

        assert found, "❌ Service Worker не отправил callback-запрос"



# Тест 5: Эмулируем блок на подписку и проверяем что ушел постбек
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