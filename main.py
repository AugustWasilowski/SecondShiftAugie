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
SAVE_PATH = os.getenv(
    "SAVE_PATH"
)  # where SSA saves audio and other temp files TODO: use tmpfile
HELP_MSG = (
    "Commands:\n!summarize <YOUTUBE LINK>(try to keep in under 10 "
    "minutes long or it may time out) \n!wolf <QUERY> for Wolfram "
    "Alpha + a liitle LLM action behind the scenes.\n!qq <QUERY> for quick answers about more topical "
    "issues.\n!llm <QUERY> talk to a one-shot llm\n!selfreflect Ask Second Shift Augie about its own code!\n"
    "You can also @Second_Shift_Augie in chat and ask it a question directly. I knows a little bit about"
    " itself too. \n!h repeat this message"
)

MOTD = (
    "Second Shift Augie! Reporting for Duty!"  # Announcement every time SSA boots up.
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
ssa = SSAWrapper()

try:
    arguments, values = getopt.getopt(argumentList, options, long_options)
    logger.info("checking each argument")
    for currentArgument, currentValue in arguments:
        if currentArgument in ("-s", "--Speak"):
            logger.info(
                "Setting Speach to True. Use !join to let Second Shift Augie join the VOICE_CHANNEL_ID"
            )
            ssa.use_voice = True

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
    await working(bot)  # set to busy while we set up.

    # Set the narrative for the SSAWrapper instance
    await ssa.set_narrative()

    # finalize on ready by setting status to ready and sending the MOTD
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send(MOTD)
    await wait_for_orders(bot)


@bot.command(name="reload")
async def reload(ctx):
    await reload_cogs()


@bot.command(name="helpmeaugie")
async def hello(interaction: nextcord.Interaction):
    await interaction.response.send_message(
        f"Hey {interaction.user.mention}\n{HELP_MSG}", ephemeral=True
    )


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
        if not voice_client.is_playing() and ssa.use_voice:
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


@bot.command()
async def summary(ctx, link):
    """Falls through to !summarize"""
    await summarize(ctx, link)


@bot.command()
async def summarize(ctx, link):
    """kicks off https://pipedream.com/ workflow"""
    await working(bot)
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
        if ssa.use_voice:
            await ssa.generate_voice_sample("Summarizing: " + yt.title, True, bot)

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

    await wait_for_orders(bot)


@bot.command()
async def transcribe(ctx, link):
    await working(bot)
    try:
        yt = YouTube(
            link,
            on_progress_callback=progress_func,
            on_complete_callback=complete_func,
            use_oauth=True,
            allow_oauth_cache=True,
        )
        await ctx.send("Processing:  " + yt.title)
        if ssa.use_voice:
            await ssa.generate_voice_sample("Transcribing: " + yt.title, True, bot)
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

    if (
        message.content.find("@Second_Shift_Augie") > 0
        or message.content.find("@1100576429781045298") > 0
    ):
        await working(bot)

        results = []
        for response in ssa.agent_chain.run(input=message.content):
            results.append(response)
        result = ''.join(results)

        await message.reply(result, mention_author=True)
        if ssa.use_voice:
            await ssa.generate_voice_sample(result, True, bot)
        await wait_for_orders(bot)

    await bot.process_commands(message)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
