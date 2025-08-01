import requests
import os
from msal import ConfidentialClientApplication

def get_access_token():
    authority = "https://login.microsoftonline.com/common"
    app = ConfidentialClientApplication(
        os.getenv("MS365_CLIENT_ID"),
        authority=authority,
        client_credential=os.getenv("MS365_CLIENT_SECRET")
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result["access_token"]

def send_email(subject, body):
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    email_data = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "toRecipients": [
                {"emailAddress": {"address": "manager1@outlook.com"}},
                {"emailAddress": {"address": "manager2@outlook.com"}},
                {"emailAddress": {"address": "manager3@outlook.com"}},
                {"emailAddress": {"address": "manager4@outlook.com"}}
            ]
        }
    }
    requests.post("https://graph.microsoft.com/v1.0/users/me/sendMail", headers=headers, json=email_data)
