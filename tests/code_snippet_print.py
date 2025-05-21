from playwright.sync_api import sync_playwright

TARGET_URL = "https://manager.staging.push-sender.com/api/v1/code-snippet/"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def handle_response(response):
            if response.url.startswith(TARGET_URL):
                print(f"\n⬅️  RESPONSE: {response.status} {response.url}")
                try:
                    data = response.json()
                    print("\n📦 JSON body:")
                    for k, v in data.items():
                        print(f"{k}: {v}")
                except Exception as e:
                    print("⚠️  JSON parse error:", e)

        page.on("response", handle_response)

        print("🔍 Opening page...")
        page.goto("https://demo.staging.almightypush.com/Ihor_demo/", wait_until="networkidle")
        page.wait_for_timeout(8000)  # ждём на всякий случай

        browser.close()

if __name__ == "__main__":
    main()
