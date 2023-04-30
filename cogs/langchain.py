import logging
import os

from langchain.chains.summarize import load_summarize_chain
from langchain.document_loaders import YoutubeLoader
from langchain.llms import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from nextcord.ext import commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(LangChainCog(bot))


async def exe_ss(ctx, arg):
    loader = YoutubeLoader.from_youtube_url(arg)
    # loader.add_video_info = True
    result = loader.load()  # Loads the video
    # await ctx.send(f"Found video from {result[0].metadata['author']} that is {result[0].metadata['length']} seconds long")  # busted
    llm = OpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
    chain = load_summarize_chain(llm, chain_type="stuff", verbose=False)
    await ctx.send(chain.run(result))


async def exe_ls(ctx, arg):
    loader = YoutubeLoader.from_youtube_url(arg)
    # loader.add_video_info = True
    result = loader.load()  # Loads the video
    # await ctx.send(f"Found video from {result[0].metadata['author']} that is {result[0].metadata['length']} seconds long")  # busted

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=0)
    texts = text_splitter.split_documents(result)

    llm = OpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
    chain = load_summarize_chain(llm, chain_type="map_reduce", verbose=False)

    await ctx.send(chain.run(texts[:4]))


class LangChainCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def ss(self, ctx, *, arg):
        # Summary for SHORT YouTube videos. Must be the video ID, not the whole URL. i.e. "g8LlwlCU0EA" not
        # "https://youtu.be/g8LlwlCU0EA"
        arg.replace("https://youtu.be/", "")
        arg.replace("https://www.youtube.com/watch?v=", "")
        # await working(commands)
        await exe_ss(ctx, arg)
        # await wait_for_orders(commands)

    @commands.command()
    async def ls(self, ctx, *, arg):
        # Summary for SHORT YouTube videos. Must be the video ID, not the whole URL. i.e. "g8LlwlCU0EA" not
        # "https://youtu.be/g8LlwlCU0EA"
        arg.replace("https://youtu.be/", "")
        arg.replace("https://www.youtube.com/watch?v=", "")
        # await working(commands)
        await exe_ls(ctx, arg)
        # await wait_for_orders(commands)