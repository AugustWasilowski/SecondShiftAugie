import logging

import nextcord
from nextcord.ext import commands

from cogs.ssa import use_voice

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def working(bot, task="Working... Please hold..."):
    """sets Second Shift Augie to busy status"""
    game = nextcord.Game(task)
    await bot.change_presence(status=nextcord.Status.do_not_disturb, activity=game)
    try:
        voice_client = nextcord.utils.get(bot.voice_clients)
        audio_source = nextcord.FFmpegPCMAudio("GettingDownToBusiness.mp3")
        if not voice_client.is_playing() and use_voice:
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f"General error in working: {e}")


async def wait_for_orders(wait_client):
    """Sets Second Shift Augie to idle status"""
    game = nextcord.Game("with some serious sh*t.")
    await wait_client.change_presence(status=nextcord.Status.online, activity=game)


def setup(bot: commands.Bot):
    bot.add_cog(StatusCog(bot))


async def on_message_from_cog(message):
    print(message)


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False
