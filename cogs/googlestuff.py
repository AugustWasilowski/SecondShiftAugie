import json
import logging
import os
import pickle
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from nextcord.ext import commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']


def get_credentials():
    """Google Drive authentication. Visit https://console.cloud.google.com/apis/credentials and click +CREATE CREDENTIALS"""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            with open(os.getenv("CLIENT_SECRET_FILE"), 'r') as file:
                client_config = json.load(file)["installed"]

            device_flow_url = "https://oauth2.googleapis.com/device/code"
            device_flow_data = {
                "client_id": client_config["client_id"],
                "scope": " ".join(SCOPES)
            }

            response = requests.post(device_flow_url, data=device_flow_data)
            response_data = response.json()
            print(response.json())

            if 'verification_url' in response_data and 'user_code' in response_data:
                print(
                    f"Please visit the following URL on another device with a browser: {response_data['verification_url']}?qrcode=1")
                print(f"Enter the following code when prompted: {response_data['user_code']}")
            else:
                raise KeyError("Unable to find 'verification_url' or 'user_code' in the response data.")

            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "client_id": client_config["client_id"],
                "client_secret": client_config["client_secret"],
                "device_code": response_data["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            }

            interval = response_data["interval"]
            while True:
                time.sleep(interval)
                token_response = requests.post(token_url, data=token_data)
                token_response_data = token_response.json()

                if token_response.status_code == 200:
                    creds = Credentials.from_authorized_user_info(info=token_response_data, scopes=SCOPES)
                    break
                elif token_response_data["error"] != "authorization_pending":
                    raise Exception(f"Error occurred during authorization: {token_response_data['error']}")

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds


def setup(bot: commands.Bot):
    bot.add_cog(GoogleCog(bot))


def upload_to_drive(video_file, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER')):
    """uploads a file to a google drive folder"""
    try:
        creds = get_credentials()
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': os.path.basename(video_file),
            'parents': [folder_id]
        }
        media = MediaFileUpload(video_file, mimetype='video/*')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f'File ID: "{file.get("id")}".')
    except HttpError as error:
        print(f'An error occurred: {error}')
        file = None
    return file


class GoogleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False
