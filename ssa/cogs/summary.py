import logging
import os

import nextcord  # add this
import openai
from langchain import OpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from nextcord.ext import commands
from pytube import YouTube

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(SummaryCog(bot)) # please put this on bottom lol


def progress_func(chunk=None, file_handle=None, remaining=None):
    """progress call back function for the Summarize function"""
    logger.info("progressing...")


def complete_func(self, path):
    """complete callback function for the Summarize function"""
    logger.info("complete")
    logger.info(self)
    logger.info(path)


async def download_yt_file(link):
    yt = YouTube(
        link,
        on_progress_callback=progress_func,
        on_complete_callback=complete_func,
        use_oauth=True,
        allow_oauth_cache=True,
    )
    logger.info("Processing:  " + yt.title)
    stream = yt.streams.filter(only_audio=True).last()
    try:
        ytFile = stream.download(os.getenv("SAVE_PATH"))
        logger.info(f"Processing complete. saving to path {ytFile}")
    except Exception as e:
        ytFile = None
        logger.info(f"Error processing {e}")
    return ytFile


class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False
                            # this is the name     # this is the description
    @nextcord.slash_command(name="summary", description="Summarize a video") # remove commands.commands and add nextcord.slash_command
    async def get_summary(self, interaction: nextcord.Interaction, link): # remove ctx and add interaction: nextcord.Interaction
        ytFile = await download_yt_file(link)

# IN THE WHOLE FILE FIX CTX TO INTERACTION, ANY CTX.AUTHOR TO INTERACTION.USER, AND CTX.SEND TO INTERACTION.REPLY (OR INTERACTION.SEND) DEPENDING ON THE CONTEXT
# DONT USE ALL CAPS, JUST FOR SHOWING YOU WHAT TO CHANGE

        audio_file = open(ytFile, "rb") #
        transcript = openai.Audio.transcribe("whisper-1", audio_file)
        logger.info(transcript)
        prompt = f"Write a Title for the transcript that is under 15 words. " \
                 f"Then write: '--Summary--' " \
                 f"Write 'Summary' as a Heading " \
                 f"1. Write a summary of the provided transcript. " \
                 f"Then  write: '--Additional Info--'. " \
                 f"Then return a list of the main points in the provided transcript. " \
                 f"Then return a list of action items. " \
                 f"Then return a list of follow up questions. " \
                 f"Then return a list of potential arguments against the transcript." \
                 f"For each list, return a Heading 2 before writing the list items. " \
                 f"Limit each list item to 200 words, and return no more than 20  points per list. " \
                 f"Transcript: "

        llm = OpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
        num_tokens = llm.get_num_tokens(transcript)
        await interaction.send(f"Number of Tokens in transcript: {num_tokens}")
        logger.info(f"Number of Tokens in transcript: {num_tokens}")
        text_splitter = RecursiveCharacterTextSplitter(separators=["\n\n", "\n"], chunk_size=10000, chunk_overlap=500)
        docs = text_splitter.create_documents([prompt, transcript])
        summary_chain = load_summarize_chain(llm=llm, chain_type='map_reduce', verbose=True)
        output = summary_chain.run(docs)

        await interaction.send(output)

        return output


def setup(bot: commands.Bot):
    bot.add_cog(SummaryCog(bot))