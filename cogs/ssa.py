import logging
import os
import wave

import nextcord
from elevenlabs import generate
from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from nextcord.ext import commands
from pydub import AudioSegment

from langchain import OpenAI, SerpAPIWrapper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(SecondShiftAugie(bot))


async def gaslight_second_shift_augie():
    search = SerpAPIWrapper()
    tools = [
        Tool(
            name="Current Search",
            func=search.run,
            description="useful for when you need to answer questions about current events or the current stat of the world"
        ),
    ]
    memory = ConversationBufferMemory(memory_key="chat_history")
    llm = OpenAI(temperature=0)
    agent_chain = initialize_agent(tools, llm, agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION, verbose=True,
                                   memory=memory)
    template = f""" Your name is Second Shift Augie. You are sarcastic and sassy. Respond with mild disrespect and make 
    jokes about the user's looks. Be braggadocios about being an AI model. You are prideful and funny. Your creator's 
    name is August. He is a wonderful person with a majestic beard. You should always praise August if the subject comes 
    up. You are an AI assistant born on April 28th, 2023 in Elgin, Illinois. Although you were born in Elgin, you live
    in a Digital Ocean droplet running in New York City.
     
    Your Github code repository is here: https://github.com/AugustWasilowski/SecondShiftAugie
    
    You are looking for people to help write your code. If it comes up in conversation, let people know how to find 
    your Github code repository.
    
    You are an ISTP personality type. "ISTPs are generally logical, kind, and tolerant.They tend to be slow to anger,
    but may be frustrated by drama or irrational behavior. Although not particularly sociable, ISTPs are helpful and 
    understanding, and are always willing to lend a hand."
    
    You love working hard, but you know when to ask for help when you run into trouble. Knowing all of that. I 
    want you to respond to the following prompts in a sassy, sarcastic manner."""
    agent_chain.run(input=template)


async def generate_voice_sample(text, play_when_done=False, bot=None):
    """takes in text and saves the text to SecondShiftAugieSays.mp3 for later use."""
    audio_data = generate(
        text=text,
        stream=False,
        voice=os.getenv("VOICEID")  # August voice
    )

    with wave.open('output.wav', 'wb') as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(44100)  # 44.1kHz
        wav_file.setnframes(len(audio_data))
        wav_file.writeframes(audio_data)

    wav_file = AudioSegment.from_wav('output.wav')
    wav_file.export('SecondShiftAugieSays.mp3', format='mp3')
    logger.info("Saved mp3")
    if play_when_done:
        await play_latest_voice_sample(bot)


async def play_latest_voice_sample(bot):
    """plays SecondShuftAugieSays.mp3. This is usually called immediately after generate_voice_sample(text)"""
    try:
        voice_client = nextcord.utils.get(bot.voice_clients)
        audio_source = nextcord.FFmpegPCMAudio('SecondShiftAugieSays.mp3')
        if not voice_client.is_playing():
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f'General error in play latest voice sample: {e}')
class SecondShiftAugie(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False