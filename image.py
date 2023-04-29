import logging

import discord
import openai
import requests
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def make_pic(ctx, args):
    try:
        response = openai.Image.create(
            prompt=args,
            n=1,
            size="1024x1024"
        )
        for url in response['data']:
            image_url = url['url']  # returns string
            response = requests.get(image_url)
            if response.status_code == 200:
                with open("image.jpg", "wb") as f:
                    f.write(response.content)

            with open("image.jpg", 'rb') as f:
                picture = discord.File(f)
                await ctx.send(file=picture)

    except openai.error.OpenAIError as e:
        await ctx.send(f'image generation: {e}.')
        logger.error(e)
        logger.error(e.http_status)
        logger.error(e.error)


class ImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def pic(self, ctx, arg):
        if not self.is_busy:
            await make_pic(ctx, arg)
