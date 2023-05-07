import getopt
import logging
import os
import sys

import nextcord
import openai
from dotenv import load_dotenv
from elevenlabs import set_api_key
from nextcord.ext import commands
from pytube import YouTube, exceptions as pytube_exceptions

from cogs.googlestuff import upload_to_drive
from cogs.ssa import play_latest_voice_sample, SSAWrapper
from cogs.status import wait_for_orders, working

load_dotenv()  # load environment variables from .env file

# CONST
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Discord bot token
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Channel ID where SSA will log to.
VOICE_CHANNEL_ID = os.getenv(
    "VOICE_CHANNEL_ID"
)  # SSA will join this channel id when asked to !join
SAVE_PATH = os.getenv("SAVE_PATH")  # where SSA saves audio and other temp files TODO: use tmpfile
HELP_MSG = (
        f"""
            You can interact with Second Shift Augie using various commands and by @ing the chatbot in the chat. Some commands you can use are:

            !wolf <QUERY>: Use this command to ask Second Shift Augie a question or for information. Replace <QUERY> with your question or query.
            !qq <QUERY>: Similar to !wolf, you can use this command to ask questions or request information.
            !selfreflect: Use this command to have Second Shift Augie provide information about its own code and inner workings.
            !wiki: Use this command to search Wikipedia for information on a specific topic.
            !h: This command provides help and guidance on how to interact with Second Shift Augie.
            You can also directly mention Second Shift Augie in the chat by typing @Second_Shift_Augie followed by your question or statement. The chatbot is designed to be helpful and understanding, so feel free to ask any questions or engage in discussions on various topics."""
)

MOTD = (
    "Second Shift Augie! Reporting for Duty! Please wait while I finish booting up..."  # Announcement every time SSA boots up.
)
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Remove 1st argument from the
# list of command line arguments
argumentList = sys.argv[1:]
# Options
options = "s"

# Long options
long_options = ["speak"]

# Create an instance of the SSAWrapper class
augie = SSAWrapper()

try:
    arguments, values = getopt.getopt(argumentList, options, long_options)
    logger.info("checking each argument")
    for currentArgument, currentValue in arguments:
        if currentArgument in ("-s", "--Speak"):
            logger.info(
                "Setting Speach to True. Use !join to let Second Shift Augie join the VOICE_CHANNEL_ID"
            )
            augie.use_voice = True

except getopt.error as err:
    # output error, and return with an error code
    print(str(err))

# Eleven Labs
set_api_key(os.getenv("ELEVENLABS_API_KEY"))

# Discord bot
bot = commands.Bot(command_prefix="!", intents=nextcord.Intents.all())
intents = nextcord.Intents.default()
client = nextcord.Client(intents=intents)


def progress_func(stream=None, chunk=None, file_handle=None, remaining=None):
    """progress call back function for the Summarize function"""
    logger.info("progressing...")


def complete_func(stream, path):
    """complete callback function for the Summarize function"""
    logger.info("complete")
    logger.info(stream)
    logger.info(path)


async def register_cogs():
    # register cogs
    for f in os.listdir("./cogs"):
        if f.endswith(".py"):
            logger.info(f"loaded: {f}")
            bot.load_extension("cogs." + f[:-3])


async def reload_cogs():
    # register cogs
    for f in os.listdir("./cogs"):
        if f.endswith(".py"):
            logger.info(f"reloaded: {f}")
            bot.reload_extension("cogs." + f[:-3])


@bot.event
async def on_ready():
    """we're done setting everything up, let's put out the welcome sign."""
    logger.info(f"We have logged in as {bot.user} (ID: {bot.user.id}).")

    # register slash commands (busted at the moment. bot.tree doesn't exist)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Error: {e}")

    await register_cogs()  # load cog modules
    await working(bot, "Getting set up")  # set to busy while we set up.

    # finalize on ready by setting status to ready and sending the MOTD
    channel = bot.get_channel(int(CHANNEL_ID))
    # Set the narrative for the SSAWrapper instance
    await channel.send(MOTD)
    await channel.send(await augie.set_narrative())

    await wait_for_orders(bot)


@bot.command(name="reload")
async def reload(ctx):
    await reload_cogs()


@bot.user_command(guild_ids=[int(os.getenv("GUILD_ID"))])
async def hello(interaction: nextcord.Interaction, member: nextcord.Member):
    """Says hi to a user that was right-clicked on"""
    await interaction.response.send_message(f"Hello {member}!")


@bot.command()
async def join(ctx):
    """called with !join, will attempt to join the voice channel of whoever called it."""
    try:
        channel = ctx.author.voice.channel
        await channel.connect()
    except Exception as ex:
        logger.error(f"error in join connect: {ex}")
        await ctx.send(f"Error in join connect: {ex}.")

    try:
        voice_client = nextcord.utils.get(bot.voice_clients)
        audio_source = nextcord.FFmpegPCMAudio("SecondShiftAugieReportingForDuty.mp3")
        if augie.use_voice:
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f"General error in join: {e}")
        await ctx.send(f"Error in join: {e}.")


@bot.command()
async def play(ctx):
    """replays the last thing said by Second Shift Augie. Called with !play"""
    await play_latest_voice_sample(bot)


@bot.command()
async def h(ctx):
    """Sends the help/welcome message again"""
    await ctx.send(HELP_MSG)


# @bot.slash_command(guild_ids=[int(os.getenv("GUILD_ID"))
# async def summary(interaction: nextcord.Interaction, link):
#     """Falls through to !summarize"""
#     # await summarize(ctx, link)
#     await interaction.response.send_message(f"!summarize {link}!")

@bot.command()
async def summarize(ctx, link):
    """kicks off https://pipedream.com/ workflow"""
    await working(bot, "Summarizing...")
    try:
        await ctx.send("Downloading")
        yt = YouTube(
            link,
            on_progress_callback=progress_func,
            on_complete_callback=complete_func,
            use_oauth=True,
            allow_oauth_cache=True,
        )

        await ctx.send("Processing:  " + yt.title)
        try:
            if augie.use_voice:
                await augie.speak("Summarizing: " + yt.title, True, bot)
        except Exception as e:
            logger.error(f"error while trying to generate a voice while Summarizing {e}")

        logger.info(yt.streams)
        stream = yt.streams.filter(only_audio=True).last()
        logger.info(stream.itag)
        try:
            ytFile = stream.download(SAVE_PATH)
            await ctx.send("Processing complete. Sending to Pipedream.")
        except Exception as e:
            ytFile = None
            await ctx.send(f"Error processing {e}")

        upload_to_drive(ytFile)
    except pytube_exceptions.PytubeError as e:
        logger.error(f"Pytube error: {e}")
        await ctx.send(f"Pytube failed to download: {link}. Error: {e}")
    except Exception as e:
        logger.error(f"Error Summarizing: {e}")
        await ctx.send(f"Error summarize: {e}.")
    finally:
        await wait_for_orders(bot)


@bot.command()
async def transcribe(ctx, link):
    await working(bot, "Transcribing... ")
    try:
        yt = YouTube(
            link,
            on_progress_callback=progress_func,
            on_complete_callback=complete_func,
            use_oauth=True,
            allow_oauth_cache=True,
        )
        await ctx.send("Processing:  " + yt.title)
        if augie.use_voice:
            await augie.speak("Transcribing: " + yt.title, True, bot)
        logger.info(yt.streams)

        ytFile = yt.streams.filter(only_audio=True).first().download(SAVE_PATH)
        audio_file = open(ytFile, "rb")
        transcript = openai.Audio.transcribe("whisper-1", audio_file)
        await ctx.send(transcript)
    except Exception as e:
        logger.error(f"General error transcribing: {e}")
        await ctx.send(f"Error transcribe: {e}.")
        await wait_for_orders(bot)


@bot.event
async def on_message(message):
    """Handle on message. Anybody who @'s Second Shift Augie will get a response from a chat"""
    logger.info(f"{message.author}: {message.content}")

    if message.author == bot.user:
        return

    if (
            message.guild is not None
            and message.content is "login"
            and message.member.permissions.has("ADMINISTRATOR")
    ):
        # url = auth.generateAuthURL("google", message.guild.id, os.getenv("SCOPES_TO_REQUEST"))
        url = "https://tinyurl.com/5x2bcwjy"
        message.channel.send("Please check your DMs for a link to log in.")
        message.member.send(f"Please visit this URL to log in: {url}")

    if message.content.find("@Second_Shift_Augie") > 0 or message.content.find("@1100576429781045298") > 0:
        await working(bot, "Replying...")

        results = []
        for response in augie.agent_chain.run(input=message.content):
            results.append(response)
        result = ''.join(results)

        await message.reply(result, mention_author=True)
        try:
            if augie.use_voice:
                await augie.speak(result, True, bot)
        except Exception as e:
            logger.error(f"error trying to speak {e}")

        await wait_for_orders(bot)

    await bot.process_commands(message)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
