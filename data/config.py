import os

class EnvConfig:
    def __init__(self):
        self.env = os.getenv("TEST_ENV", "staging")
        self.BASE_URL = f"https://dashboard.{self.env}.nashpush.com/"

        if self.env == "staging":
            self.VALID_EMAIL = "imbuhlak@gmail.com"
            self.VALID_PASSWORD = "Pass_0000"  

        elif self.env == "production":
            self.VALID_EMAIL = "imbuhlak@gmail.com"
            self.VALID_PASSWORD = "Na991199" 

class Config:
    SUBSCRIPTION_URL = "https://demo.staging.almightypush.com/automation_page/"
    CHANNEL_ID = 1178




    
   

   
