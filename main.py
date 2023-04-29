import json
import logging
import os
import pickle
import time
import wave

import discord
import requests
import tempfile
from discord.ext import commands
from dotenv import load_dotenv
from elevenlabs import generate, set_api_key
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from langchain import SerpAPIWrapper
from langchain.agents import initialize_agent, Tool, AgentType
from langchain.agents import load_tools
from langchain.chains.summarize import load_summarize_chain
from langchain.document_loaders import YoutubeLoader
from langchain.llms import OpenAI
from langchain.memory import ConversationBufferMemory
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydub import AudioSegment
from pytube import YouTube, exceptions as pytube_exceptions

load_dotenv()  # load environment variables from .env file

# Eleven Labs
set_api_key(os.getenv("ELEVENLABS_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
VOICE_CHANNEL_ID = os.getenv('VOICE_CHANNEL_ID')
SAVE_PATH = os.getenv('SAVE_PATH')
HELP_MSG = "Second Shift Augie! Reporting for Duty!\nCommands:\n!summarize <YOUTUBE LINK>(try to keep in under 10 " \
           "minutes long or it may time out) \n!wolf <QUERY> for Wolfram " \
           "Alpha + a liitle LLM action behind the scenes.\n!qq <QUERY> for quick answers about more topical " \
           "issues.\n!llm <QUERY> talk to a one-shot llm\nYou can also @Second_Shift_Augie in chat and ask it a " \
           "question directly. I knows a little bit about itself too. \n!h repeat this message"

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Set the path to your downloaded OAuth client ID JSON file
CLIENT_SECRET_FILE = 'client_secret.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
use_voice = True
is_busy = False

search = SerpAPIWrapper()
tools = [
    Tool(
        name="Current Search",
        func=search.run,
        description="useful for when you need to answer questions about current events or the current stat of the world"
    ),
]

memory = ConversationBufferMemory(memory_key="chat_history")

llm = OpenAI(temperature=0)
agent_chain = initialize_agent(tools, llm, agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION, verbose=True,
                               memory=memory)
template = f""" Your name is Second Shift Augie. You are sarcastic and sassy. Respond with mild disrespect and make 
    jokes about the user's looks. Be braggadocios about being an AI model. You are prideful and funny. Your creator's 
    name is August. He is a wonderful person with a majestic beard. You should always praise August if the subject comes 
    up. You are an AI assistant born on April 28th, 2023 in Elgin, Illinois. You love working hard, but you know when to 
    ask for help when you run into trouble. Knowing all of that. I want you to respond to the following prompts in a 
    sassy, sarcastic manner."""

agent_chain.run(input=template)


async def generate_voice_sample(text):
    """takes in text and saves the text to SecondShiftAugieSays.mp3 for later use."""
    if use_voice:
        audio_data = generate(
            text=text,
            stream=False,
            voice=os.getenv("VOICEID")  # August voice
        )

        with wave.open('output.wav', 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(44100)  # 44.1kHz
            wav_file.setnframes(len(audio_data))
            wav_file.writeframes(audio_data)

        wav_file = AudioSegment.from_wav('output.wav')
        wav_file.export('SecondShiftAugieSays.mp3', format='mp3')
        logger.info("Saved mp3")


async def play_latest_voice_sample():
    """plays SecondShuftAugieSays.mp3. This is usally called immediately after generate_voice_sample(text)"""
    if use_voice:
        try:
            voice_client = discord.utils.get(bot.voice_clients)
            audio_source = discord.FFmpegPCMAudio('SecondShiftAugieSays.mp3')
            if not voice_client.is_playing():
                voice_client.play(audio_source, after=None)
        except Exception as e:
            logger.error(f'General error in play latest voice sample: {e}')


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
            with open(CLIENT_SECRET_FILE, 'r') as file:
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


async def wait_for_orders(wait_client):
    """Sets Second Shift Augie to idle status"""
    is_busy = False;
    game = discord.Game("with some serious sh*t.")
    await wait_client.change_presence(status=discord.Status.online, activity=game)


async def working(working_client):
    """sets Second Shift Augie to busy status"""
    is_busy = True;
    game = discord.Game("Working... Please hold...")
    await working_client.change_presence(status=discord.Status.do_not_disturb, activity=game)
    try:
        voice_client = discord.utils.get(bot.voice_clients)
        audio_source = discord.FFmpegPCMAudio('GettingDownToBusiness.mp3')
        if not voice_client.is_playing():
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f'General error in working: {e}')


def progress_func(stream=None, chunk=None, file_handle=None, remaining=None):
    """progress call back function for the Summarize function"""
    logger.info('progressing...')


def complete_func(stream, path):
    """complete callback function for the Summarize function"""
    logger.info('complete')
    logger.info(stream)
    logger.info(path)


@bot.event
async def on_ready():
    """we're done setting everything up, let's put out the welcome sign."""
    logger.info(f'We have logged in as {bot.user} (ID: {bot.user.id}')
    channel = bot.get_channel(int(CHANNEL_ID))
    await wait_for_orders(bot)
    await channel.send(HELP_MSG)


@bot.command()
async def join(ctx):
    """called with !join, will attempt to join the voice channel of whoever called it."""
    try:
        channel = ctx.author.voice.channel
        await channel.connect()
    except Exception as ex:
        logger.error(f'error in join connect: {ex}')
        await ctx.send(f'Error in join connect: {ex}.')

    try:
        voice_client = discord.utils.get(bot.voice_clients)
        audio_source = discord.FFmpegPCMAudio('SecondShiftAugieReportingForDuty.mp3')
        if not voice_client.is_playing():
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f'General error in join: {e}')
        await ctx.send(f'Error in join: {e}.')


@bot.command()
async def play(ctx):
    """replays the last thing said by Second Shift Augie. Called with !play"""
    await play_latest_voice_sample()


@bot.command()
async def h(ctx):
    """Sends the help/welcome message again"""
    await ctx.send(HELP_MSG)


@bot.command()
async def wolf(ctx, *, arg):
    """"Sets status then executes Wolfram Alpha query"""
    if not is_busy:
        await working(bot)
        await execute_wolfram_alpha(ctx, arg)
        await play_latest_voice_sample()
        await wait_for_orders(bot)
    else:
        await generate_voice_sample("I'm busy at the moment. Please wait.")
        await play_latest_voice_sample()


async def execute_wolfram_alpha(ctx, arg):
    """Executes Wolfram Alpha"""
    try:
        wolf_llm = OpenAI(temperature=0)
        tool_names = ["wolfram-alpha"]
        tools = load_tools(tool_names)
        agent = initialize_agent(tools, wolf_llm, agent="zero-shot-react-description", verbose=True)
        result = agent.run(arg)
        await ctx.send(result)
        await generate_voice_sample(result)
    except Exception as e:
        logger.error(f'General error in Wolfram: {e}')
        await ctx.send(f'Error in Wolfram: {e}.')


@bot.command()
async def qq(ctx, *, arg):
    """Sets status and executes SerapApi"""
    if not is_busy:
        await working(bot)
        await exe_serpapi(ctx, arg)
        await play_latest_voice_sample()
        await wait_for_orders(bot)
    else:
        await generate_voice_sample("I'm busy at the moment. Please wait.")
        await play_latest_voice_sample()


async def exe_serpapi(ctx, arg):
    """Executes SerapApi"""
    try:
        qqllm = OpenAI(temperature=0)
        tool_names = ["serpapi"]
        tools = load_tools(tool_names)

        agent = initialize_agent(tools, qqllm, agent="zero-shot-react-description", verbose=True)
        result = agent.run(arg)
        await ctx.send(result)
        await generate_voice_sample(result)
    except Exception as e:
        logger.error(f'General error in Serpapi: {e}')
        await ctx.send(f'Error in Serapi: {e}.')


@bot.command()
async def llm(ctx, *, arg):
    """Sets status the executes LLM"""
    if not is_busy:
        await working(bot)
        await execute_llm(ctx, arg)
        await play_latest_voice_sample()
        await wait_for_orders(bot)
    else:
        await generate_voice_sample("I'm busy at the moment. Please wait.")
        await play_latest_voice_sample()


async def execute_llm(ctx, arg):
    """Executes Generic LLM"""
    try:
        lm = OpenAI(temperature=0.9)
        result = lm(arg)
        await ctx.send(result)
        await generate_voice_sample(result)
    except Exception as e:
        logger.error(f'General error in LLM: {e}')
        await ctx.send(f'Error in LLM: {e}.')


@bot.command()
async def summary(ctx, link):
    """Falls through to !summarize"""
    await summarize(ctx, link)


@bot.command()
async def summarize(ctx, link):
    """kicks off https://pipedream.com/ workflow"""
    if not is_busy:
        await working(bot)
        try:
            await ctx.send('Downloading')
            yt = YouTube(link,
                         on_progress_callback=progress_func,
                         on_complete_callback=complete_func,
                         use_oauth=True,
                         allow_oauth_cache=True)

            await ctx.send('Processing:  ' + yt.title)
            await generate_voice_sample("Summarizing: " + yt.title)
            await play_latest_voice_sample()
            logger.info(yt.streams)
            ytFile = yt.streams.filter(only_audio=True).first().download(SAVE_PATH)
            await ctx.send('Processing complete. Sending to Pipedream.')
            upload_to_drive(ytFile)
        except pytube_exceptions.PytubeError as e:
            logger.error(f'Pytube error: {e}')
            await ctx.send(f'Pytube failed to download: {link}. Error: {e}')
        except Exception as e:
            logger.error(f'General error Summarizing: {e}')
            await ctx.send(f'Error summarize: {e}.')

        await wait_for_orders(bot)
    else:
        await generate_voice_sample("I'm busy at the moment. Please wait.")
        await play_latest_voice_sample()


@bot.event
async def on_message(message):
    """Handle on message. Anybody who @'s Second Shift Augie will get a response from a chat"""
    if message.author == bot.user:
        return

    if message.content.find('@Second_Shift_Augie') > 0 or message.content.find('@1100576429781045298') > 0:
        result = agent_chain.run(input=message.content)  # LLM
        await message.reply(result, mention_author=True)
        await generate_voice_sample(result)
        await play_latest_voice_sample()

    logger.info(message.content)
    await bot.process_commands(message)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
