import logging
import os
import pprint

import google.generativeai as palm
from nextcord.ext import commands

palm.configure(api_key=os.getenv("PALM_KEY"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup(bot):
    bot.add_cog(PalmCog(bot))


class PalmCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def list(self, ctx):
        models = [m for m in palm.list_models() if 'generateText' in m.supported_generation_methods]
        for m in models:
            await ctx.send(pprint.pformat(m))

    @commands.command()
    async def palm(self, ctx, *, prompt):
        models = [m for m in palm.list_models() if 'generateText' in m.supported_generation_methods]
        model = models[0].name
        async with ctx.typing():
            completion = palm.generate_text(
                model=model,
                prompt=prompt,
                # The maximum length of the response
                max_output_tokens=1024,
            )

            if completion.result and len(completion.result) > 0:
                await ctx.send(completion.result)
            else:
                await ctx.send("Error")
