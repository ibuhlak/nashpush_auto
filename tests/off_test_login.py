from page_models.login_page import LoginPage
from playwright.sync_api import Page


def test_valid_login(page: Page):
    login_page = LoginPage(page)
    login_page.open_url()
    login_page.login(login_page.env_config.VALID_EMAIL, login_page.env_config.VALID_PASSWORD)

    page.wait_for_load_state("networkidle")
    
    assert page.url == f"{login_page.env_config.BASE_URL}user-bases"
    

