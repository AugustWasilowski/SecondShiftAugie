# Second Shift Augie Bot README

Second Shift Augie is a sassy and sarcastic AI assistant that helps answer questions and summarize YouTube videos. It uses the `discord.py` library for interacting with the Discord API and has several different features, including text-to-speech functionality.

## Features

- Summarize YouTube videos
- Answer questions using Wolfram Alpha
- Provide quick answers about current events using SerpAPI
- Interact with a one-shot language model (LLM)

## Dependencies

- `discord.py`
- `dotenv`
- `requests`
- `google-auth`
- `google-api-python-client`
- `pytube`
- `pydub`
- `langchain`
- `elevenlabs`

## Setup

1. Install the required Python packages.
2. Create a `.env` file in the same directory as the script and add the following environment variables:

```
BOT_TOKEN=<your_bot_token>
CHANNEL_ID=<your_channel_id>
VOICE_CHANNEL_ID=<your_voice_channel_id>
SAVE_PATH=<path_to_save_downloaded_videos>
ELEVENLABS_API_KEY=<your_elevenlabs_api_key>
VOICEID=<your_voice_id>
GOOGLE_DRIVE_FOLDER=<your_google_drive_folder_id>
OPENAI_API_KEY=<your_openai_api_key>
WOLFRAM_ALPHA_APPID=<your_wolfram_alpha_appid>
SERPAPI_API_KEY=<your_serpapi_key>
```

3. Place your Google OAuth `client_secret.json` file in the same directory as the script.

## Commands

- `!join`: Make the bot join the user's voice channel.
- `!play`: Play the latest voice sample.
- `!h`: Display a help message with the list of commands.
- `!wolf <QUERY>`: Answer questions using Wolfram Alpha.
- `!qq <QUERY>`: Provide quick answers about current events using SerpAPI.
- `!llm <QUERY>`: Interact with a one-shot LLM.
- `!summarize <YOUTUBE LINK>`: Summarize the given YouTube video.

## Usage

1. Run the bot with `python main.py`.
2. Invite the bot to your Discord server and interact with it using the available commands.

## How it works

The bot primarily relies on the `langchain` package to process and answer questions using various services like Wolfram Alpha, SerpAPI, and one-shot LLMs. It also uses the `elevenlabs` package to generate text-to-speech audio. The bot is designed to maintain a conversation buffer memory to keep track of previous interactions.

For summarizing YouTube videos, the bot uses the `pytube` library to download the video and uploads it to a Google Drive folder. Pipedream is then used to do the summarization. 