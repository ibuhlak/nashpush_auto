from data.config import EnvConfig
from playwright.sync_api import Page

class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.env_config = EnvConfig()
        self.login_page_url = f"{self.env_config.BASE_URL}auth/sign-in"
        self.login_field = page.get_by_role("textbox", name="Email Address")
        self.password_field = page.get_by_role("textbox", name="Password")
        self.login_button = page.get_by_role("button", name="Log in")

    def open_url(self):
        self.page.goto(self.login_page_url)
    
    def fill_login(self, email: str):
        self.login_field.fill(email)

    def fill_password(self, password: str):
        self.password_field.fill(password)

    def click_login_button(self):
        self.login_button.click() 

    def login(self, email: str, password: str):
        self.fill_login(email)
        self.fill_password(password)
        self.click_login_button()