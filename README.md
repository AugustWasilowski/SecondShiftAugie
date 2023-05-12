# Second Shift Augie Bot README

Second Shift Augie is a sassy and sarcastic AI assistant that helps answer questions and summarize YouTube videos. It 
uses the `discord.py` library for interacting with the Discord API and has several different features, including 
text-to-speech functionality.

## Features

- Summarize YouTube videos
- Answer questions using Wolfram Alpha
- Provide quick answers about current events using SerpAPI
- Interact with a one-shot language model (LLM)
- Act as a chatbot with memory.  

## Commands

- `!join`: Make the bot join the user's voice channel.
- `!play`: Play the latest voice sample.
- `!h`: Display a help message with the list of commands.
- `!wolf <QUERY>`: Answer questions using Wolfram Alpha.
- `!qq <QUERY>`: Provide quick answers about current events using SerpAPI.
- `!llm <QUERY>`: Interact with a one-shot LLM.
- `!ss <YOUTUBE VIDEO ID>`: Summarizes a SHORT YouTube video.
- `!ls <YOUTUBE VIDEO ID>`: Summarized a LONG YouTube Video
- `!pic <QUERY>`: Calls DALL-E for image generation.
- `!summarize <YOUTUBE LINK>`: Summarize the given YouTube video.
- 
## Usage

1. Install the package as described below.
2. Run the bot by running `breathe`
3. Invite the bot to your Discord server and interact with it using the available commands.

## How it works

The bot primarily relies on the `langchain` package to process and answer questions using various services like Wolfram Alpha, SerpAPI, and one-shot LLMs. It also uses the `elevenlabs` package to generate text-to-speech audio. The bot is designed to maintain a conversation buffer memory to keep track of previous interactions.

For summarizing YouTube videos, the bot uses the `pytube` library to download the video and uploads it to a Google Drive folder. Pipedream is then used to do the summarization. 

## Dependencies
Dependencies are managed utilizing setuptools. Versioning is handled via 
[setuptools-git-versioning](https://setuptools-git-versioning.readthedocs.io/en/stable/install.html).

Installing the package installs all the dependencies. Beautiful.

### Linux Requirements
If you want to enable voice support you'll need to install the following packages:

- [libffi](https://github.com/libffi/libffi)
- [libnacl](https://github.com/saltstack/libnacl)
- [python3-dev](https://packages.debian.org/python3-dev)

Debian based OS' can run:
```bash
apt install libffi-dev libnacl-dev python3-dev
```

## Setup
1. Install python 3.11.1 or higher
2. Create a virtual environment using whatever thing you want. If you're going 
   to use PyCharm, then open PyCharm and let it do it for you. If you aren't, 
   then you'll need to open a terminal (bash/powershell/etc) and run:

```bash
mkdir .venvs && cd .venvs
python -m venv ssa
./ssa/Scripts/activate
```
3. If you did this via shell, using that same shell with the virtualenv active 
   navigate to the directory where this readme exists and install this in 
   development mode, by running:

```bash
pip install --editable .
```
To install this for running on a server, run this instead:

```bash
pip install .
```

Magical.

4. Copy the .env.template to .env and fill in the variables as required.
5. Place your Google OAuth `client_secret.json` file in the same directory as the script.

@TODO - Come back to this. All secrets and what not should just go into a directory that's ignored like env. 

## Dependency Management
Python packages can be specified within the `pyproject.toml` file. Under the 
`[project]` table header, you will find the `dependencies` array, which can 
define python packages the same way that you would elsewhere.