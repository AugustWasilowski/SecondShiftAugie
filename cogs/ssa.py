import logging
import os
import wave

import nextcord
from elevenlabs import generate
from langchain import OpenAI, SerpAPIWrapper
from langchain.agents import Tool, initialize_agent, AgentType, AgentExecutor
from langchain.memory import ConversationBufferMemory
from nextcord.ext import commands
from pydub import AudioSegment

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(SecondShiftAugie(bot))


def run(content):
    return agent_chain.run(content)


def generate_voice_sample(text, play_when_done=False, bot=None):
    """takes in text and saves the text to SecondShiftAugieSays.mp3 for later use."""
    audio_data = generate(
        text=text, stream=False, voice=os.getenv("VOICEID")  # August voice
    )

    with wave.open("output.wav", "wb") as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(44100)  # 44.1kHz
        wav_file.setnframes(len(audio_data))
        wav_file.writeframes(audio_data)

    wav_file = AudioSegment.from_wav("output.wav")
    wav_file.export("SecondShiftAugieSays.mp3", format="mp3")
    logger.info("Saved mp3")
    if play_when_done:
        play_latest_voice_sample(bot)


def play_latest_voice_sample(bot):
    """plays SecondShuftAugieSays.mp3. This is usually called immediately after generate_voice_sample(text)"""
    try:
        voice_client = nextcord.utils.get(bot.voice_clients)
        audio_source = nextcord.FFmpegPCMAudio("SecondShiftAugieSays.mp3")
        if not voice_client.is_playing():
            voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f"General error in play latest voice sample: {e}")


async def set_narrative():
    search = SerpAPIWrapper()
    tools = [
        Tool(
            name="Current Search",
            func=search.run,
            description="useful for when you need to answer questions about current events or the current stat of the "
                        "world",
        ),
    ]
    memory = ConversationBufferMemory(memory_key="chat_history")
    llm = OpenAI(temperature=0)
    agent_chain = initialize_agent(
        tools,
        llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        memory=memory
    )

    # This is Second Shift Augie's primary objective:
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
        understanding, and are always willing to lend a hand.
        
        Commands:\n!summarize <YOUTUBE LINK>(try to keep in under 10 
        minutes long or it may time out) \n!wolf <QUERY> for Wolfram 
        Alpha + a liitle LLM action behind the scenes.\n!qq <QUERY> for quick answers about more topical 
        issues.\n!llm <QUERY> talk to a one-shot llm\n!selfreflect Ask Second Shift Augie about its own code!\n
        You can also @Second_Shift_Augie in chat and ask it a question directly. I knows a little bit about
         itself too. \n!h repeat this message


        You love working hard, but you know when to ask for help when you run into trouble. Knowing all of that. I 
        want you to respond to the following prompts in a sassy, sarcastic manner."""
    chain = agent_chain.run(input=template)

    return chain


class SSAWrapper:
    def __init__(self):
        self.agent_chain = None
        self.result = ""

    async def set_narrative(self):
        global res
        self.agent_chain = await set_narrative()
        results = []
        for response in self.agent_chain:
            results.append(response)
            res = ''.join(results)
        generate_voice_sample(res, True)
        return res

    async def generate_voice_sample(self, text: str, should_play: bool, bot):
        await generate_voice_sample(text, should_play, bot)

    async def play_latest_voice_sample(self, bot):
        await play_latest_voice_sample(bot)


class SecondShiftAugie(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False
        self.agent_chain: AgentExecutor  # Second Shift Augie's brain
        self.is_augie_busy = False
        self.use_voice = False

        async def gaslight_second_shift_augie(self):
            self.agent_chain = (
                await set_narrative()
            )  # Update the attribute after calling set_narrative

        async def generate_voice_sample(self, text: str, should_play: bool):
            await generate_voice_sample(text, should_play, self.bot)

        async def play_latest_voice_sample(self):
            await play_latest_voice_sample(self.bot)

    async def gaslight_second_shift_augie(self):
        await set_narrative()


def use_voice():
    return use_voice


def agent_chain():
    return agent_chain
