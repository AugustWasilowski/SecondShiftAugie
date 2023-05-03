import logging
import os
import textwrap

from langchain.chains import RetrievalQA
from langchain.chains.summarize import load_summarize_chain
from langchain.chat_models.openai import ChatOpenAI
from langchain.document_loaders import TextLoader
from langchain.document_loaders import YoutubeLoader
from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from nextcord.ext import commands
from pytube import YouTube

from cogs.ssa import generate_voice_sample
from cogs.status import working, wait_for_orders

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def setup(bot: commands.Bot):
    bot.add_cog(LangChainCog(bot))


async def exe_selfreflect(ctx, arg):
    llm = ChatOpenAI(model='gpt-3.5-turbo', openai_api_key=os.getenv("OPENAI_API_KEY"))
    embeddings = OpenAIEmbeddings(disallowed_special=(), openai_api_key=os.getenv("OPENAI_API_KEY"))

    root_dir = './cogs/'
    docs = []

    for dirpath, dirnames, filenames in os.walk(root_dir):

        # Go through each file
        for file in filenames:
            if file.endswith(".py"):  # Check if file has .py extension
                try:
                    # Load up the file as a doc and split
                    loader = TextLoader(os.path.join(dirpath, file), encoding='utf-8')
                    docs.extend(loader.load_and_split())
                except Exception as e:
                    logger.error(f"error loading docs {e}")

    logger.info(f"You have {len(docs)} documents\n")
    docsearch = FAISS.from_documents(docs, embeddings)
    # Get our retriever ready
    qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=docsearch.as_retriever())

    output = qa.run(arg)
    generate_voice_sample(output, True)
    output_chunks = textwrap.wrap(output, width=2000)

    # send each chunk separately using ctx.send()
    for chunk in output_chunks:
        await ctx.send(chunk)

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
    chain = load_summarize_chain(llm, chain_type="map_reduce", verbose=True)
    result = chain.run(texts[:4])
    generate_voice_sample(result, True)
    await ctx.send(result)


class LangChainCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def ss(self, ctx, *, arg):
        # Summary for SHORT YouTube videos. Must be the video ID, not the whole URL. i.e. "g8LlwlCU0EA" not
        # "https://youtu.be/g8LlwlCU0EA"
        yt = YouTube(arg)
        await exe_ss(ctx, yt.video_id)

    @commands.command()
    async def ls(self, ctx, *, arg):
        # Summary for SHORT YouTube videos. Must be the video ID, not the whole URL. i.e. "g8LlwlCU0EA" not
        # "https://youtu.be/g8LlwlCU0EA"
        yt = YouTube(arg)
        await exe_ls(ctx, yt.video_id)

    @commands.command()
    async def selfreflect(self, ctx, *, arg):
        await working(self.bot)
        await exe_selfreflect(ctx, arg)
        await wait_for_orders(self.bot)
