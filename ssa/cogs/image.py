import logging

import nextcord
import openai
import requests
from nextcord.ext import commands

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(ImageCog(bot))


class ImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def pic(self, ctx, *, arg):

        try:
            response = openai.Image.create(prompt=arg, n=10, size="1024x1024")
            for url in response["data"]:
                image_url = url["url"]  # returns string
                response = requests.get(image_url)
                if response.status_code == 200:
                    with open("../data/image.jpg", "wb") as f:
                        f.write(response.content)

                with open("../data/image.jpg", "rb") as f:
                    picture = nextcord.File(f)
                    await ctx.send(file=picture)

        except openai.error.OpenAIError as e:
            await ctx.send(f"image generation: {e}.")
            logger.error(e)
            logger.error(e.http_status)
            logger.error(e.error)
