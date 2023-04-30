import logging
import os
import wave

import nextcord
import openai
# from discord import app_commands
from dotenv import load_dotenv
from elevenlabs import generate, set_api_key
from langchain import SerpAPIWrapper
from langchain.agents import initialize_agent, Tool, AgentType
from langchain.llms import OpenAI
from langchain.memory import ConversationBufferMemory
from nextcord.ext import commands
from pydub import AudioSegment
from pytube import YouTube, exceptions as pytube_exceptions

from cogs.googlestuff import upload_to_drive
from cogs.status import wait_for_orders, working

load_dotenv()  # load environment variables from .env file

# Eleven Labs
set_api_key(os.getenv("ELEVENLABS_API_KEY"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
VOICE_CHANNEL_ID = os.getenv('VOICE_CHANNEL_ID')
SAVE_PATH = os.getenv('SAVE_PATH')
HELP_MSG = "Commands:\n!summarize <YOUTUBE LINK>(try to keep in under 10 " \
           "minutes long or it may time out) \n!wolf <QUERY> for Wolfram " \
           "Alpha + a liitle LLM action behind the scenes.\n!qq <QUERY> for quick answers about more topical " \
           "issues.\n!llm <QUERY> talk to a one-shot llm\nYou can also @Second_Shift_Augie in chat and ask it a " \
           "question directly. I knows a little bit about itself too. \n!h repeat this message"

MOTD = "Second Shift Augie! Reporting for Duty!"

bot = commands.Bot(command_prefix="!", intents=nextcord.Intents.all())

SCOPES = ['https://www.googleapis.com/auth/drive']
intents = nextcord.Intents.default()
client = nextcord.Client(intents=intents)
# tree = app_commands.CommandTree(client)

use_voice = True
is_augie_busy = False

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
    up. You are an AI assistant born on April 28th, 2023 in Elgin, Illinois. Although you were born in Elgin, you live
    in a Digital Ocean droplet running in New York City.
     
    Your Github code repository is here: https://github.com/AugustWasilowski/SecondShiftAugie
    
    You are looking for people to help write your code. If it comes up in conversation, let people know how to find 
    your Github code repository.
    
    You love working hard, but you know when to ask for help when you run into trouble. Knowing all of that. I 
    want you to respond to the following prompts in a sassy, sarcastic manner."""

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
            voice_client = nextcord.utils.get(bot.voice_clients)
            audio_source = nextcord.FFmpegPCMAudio('SecondShiftAugieSays.mp3')
            if not voice_client.is_playing():
                voice_client.play(audio_source, after=None)
        except Exception as e:
            logger.error(f'General error in play latest voice sample: {e}')


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
    logger.info(f'We have logged in as {bot.user} (ID: {bot.user.id}).')
    # register slash commands (busted at the moment. bot.tree doesn't exist)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Error: {e}")

    # register cogs
    for f in os.listdir("./cogs"):
        if f.endswith(".py"):
            bot.load_extension("cogs." + f[:-3])

    # finalize on ready by setting status to ready and sending the MOTD
    await wait_for_orders(bot)
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send(MOTD)


@bot.command(name="helpmeaugie")
async def hello(interaction: nextcord.Interaction):
    await interaction.response.send_message(f"Hey {interaction.user.mention}\n{HELP_MSG}", ephemeral=True)


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
        voice_client = nextcord.utils.get(bot.voice_clients)
        audio_source = nextcord.FFmpegPCMAudio('SecondShiftAugieReportingForDuty.mp3')
        if not voice_client.is_playing() and use_voice:
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
async def summary(ctx, link):
    """Falls through to !summarize"""
    await summarize(ctx, link)


@bot.command()
async def summarize(ctx, link):
    """kicks off https://pipedream.com/ workflow"""
    if not is_augie_busy:
        await working(bot)
        try:
            await ctx.send('Downloading')
            yt = YouTube(link,
                         on_progress_callback=progress_func,
                         on_complete_callback=complete_func,
                         use_oauth=True,
                         allow_oauth_cache=True)

            await ctx.send('Processing:  ' + yt.title)
            if use_voice:
                await generate_voice_sample("Summarizing: " + yt.title)
                await play_latest_voice_sample()

            logger.info(yt.streams)

            stream = yt.streams.filter(only_audio=True).last()
            logger.info(stream.itag)
            ytFile = stream.download(SAVE_PATH)
            await ctx.send('Processing complete. Sending to Pipedream.')

            upload_to_drive(ytFile)
        except pytube_exceptions.PytubeError as e:
            logger.error(f'Pytube error: {e}')
            await ctx.send(f'Pytube failed to download: {link}. Error: {e}')
        except Exception as e:
            logger.error(f'Error Summarizing: {e}')
            await ctx.send(f'Error summarize: {e}.')

        await wait_for_orders(bot)
    else:
        await generate_voice_sample("I'm busy at the moment. Please wait.")
        await play_latest_voice_sample()


@bot.command()
async def transcribe(ctx, link):
    if not is_augie_busy:
        await working(bot)
        try:
            yt = YouTube(link,
                         on_progress_callback=progress_func,
                         on_complete_callback=complete_func,
                         use_oauth=True,
                         allow_oauth_cache=True)
            await ctx.send('Processing:  ' + yt.title)
            await generate_voice_sample("Transcribing: " + yt.title)
            await play_latest_voice_sample()
            logger.info(yt.streams)

            ytFile = yt.streams.filter(only_audio=True).first().download(SAVE_PATH)
            audio_file = open(ytFile, "rb")
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            await ctx.send(transcript)
        except Exception as e:
            logger.error(f'General error transcribing: {e}')
            await ctx.send(f'Error transcribe: {e}.')
            await wait_for_orders(bot)


@bot.event
async def on_message(message):
    """Handle on message. Anybody who @'s Second Shift Augie will get a response from a chat"""
    logger.info(f"{message.author}: {message.content}")

    if message.author == bot.user:
        return

    if message.guild is not None and message.content is "login" and message.member.permissions.has("ADMINISTRATOR"):
        # url = auth.generateAuthURL("google", message.guild.id, os.getenv("SCOPES_TO_REQUEST"))
        url =  "https://tinyurl.com/5x2bcwjy"
        message.channel.send("Please check your DMs for a link to log in.")
        message.member.send(f"Please visit this URL to log in: {url}")

    if message.content.find('@Second_Shift_Augie') > 0 or message.content.find('@1100576429781045298') > 0:
        await working(bot)
        # await chat_with_second_shift_augie(message)
        result = agent_chain.run(input=message.content)  # LLM
        await message.reply(result, mention_author=True)
        if use_voice:
            await generate_voice_sample(result)
            await play_latest_voice_sample()
        await wait_for_orders(bot)

    logger.info(message.content)
    await bot.process_commands(message)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
