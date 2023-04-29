import logging

from discord.ext import commands
from langchain import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def execute_llm(ctx, arg):
    """Executes Generic LLM"""
    try:
        lm = OpenAI(temperature=0.9)
        result = lm(arg)
        await ctx.send(result)
    #        await generate_voice_sample(result)
    except Exception as e:
        logger.error(f'Error in LLM: {e}')
        await ctx.send(f'Error in LLM: {e}.')


class LLMCog(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def llm(self, ctx, *, arg):
        """Sets status the executes LLM"""
        if not self.is_busy:
            #       await working(bot)
            await execute_llm(ctx, arg)

    #        await play_latest_voice_sample()
    #        await wait_for_orders(bot)
    #    else:
    #        await generate_voice_sample("I'm busy at the moment. Please wait.")
    #        await play_latest_voice_sample()
