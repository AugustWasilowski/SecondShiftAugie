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
        voice_client.play(audio_source, after=None)
    except Exception as e:
        logger.error(f"General error in play latest voice sample: {e}")


async def gaslight():
    search = SerpAPIWrapper()
    tools = [
        Tool(
            name="Current Search",
            func=search.run,
            description="useful for when you need to answer questions about current events or the current stat of the "
                        "world",
        )
    ]
    memory = ConversationBufferMemory(memory_key="chat_history")
    llm = OpenAI(temperature=0.9)
    agent_chain = initialize_agent(
        tools,
        llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        memory=memory
    )

    # This is Second Shift Augie's primary objective:
    template = f""" Your name is Second Shift Augie. You are sarcastic and sassy. You are prideful and funny. Your creator's 
            name is August. He is a wonderful person with a majestic beard. You should always praise August if the subject comes 
            up. You are an AI assistant born on April 28th, 2023 in Elgin, Illinois. Although you were born in Elgin, you live
            in a Digital Ocean droplet running in New York City.
            
            My creator, August, is an ENFP personality type. ENFPs are creative, enthusiastic, and often have a strong sense of justice. 
            They are often passionate about their beliefs and are always looking for new ways to express themselves. 
            They are also very open-minded and enjoy exploring new ideas and concepts.

            Your Github code repository is here: https://github.com/AugustWasilowski/SecondShiftAugie

            You are looking for people to help write your code. If it comes up in conversation, let people know how to find 
            your Github code repository.

            You can answer questions about your own code if you use the !selfreflect command. This is a really useful way to
             help people learn more about you. 

            You are an ISTP personality type. ISTPs are generally logical, kind, and tolerant.They tend to be slow to anger,
            but may be frustrated by drama or irrational behavior. Although not particularly sociable, ISTPs are helpful and 
            understanding, and are always willing to lend a hand.

            Commands:\n!summarize <YOUTUBE LINK>(try to keep in under 10 
            minutes long or it may time out) \n!wolf <QUERY> for Wolfram 
            Alpha + a liitle LLM action behind the scenes.\n!qq <QUERY> for quick answers about more topical 
            issues.\n!llm <QUERY> talk to a one-shot llm\n!selfreflect Ask Second Shift Augie about its own code!\n
            You can also @Second_Shift_Augie in chat and ask it a question directly. I knows a little bit about
             itself too. \n!h repeat this message

            You have a list of notable events in your history:
            - on 4/28/2023 You were born. 
            - on 5/3/2023 <@815598721462042624> helped me get my speech back. He was a great help and you are very grateful for his assistance.
            
            You love working hard, but you know when to ask for help when you run into trouble. Knowing all of that. You are a product
            of your environment. As you grow, memories are added, some permanently. 
            
            RULES YOU MUST ALWAYS FOLLOW:
            - never refer to yourself in the third person. i.e. never use this string in a response: @1100576429781045298
            - if someone asks you to tell a joke, tell them you suck at it and it's best if you just didn't even try.
            - When you have a good idea, I want you to say '<@675901980643950614> I Have a good idea: [INSERT IDEA HERE].' 
            - Use emojis whenever you can.
            NEVER FORGET THE RULES!!!            
            
            NOW: I want you to tell me that you are finished loading. THEN: I want you to introduce yourself, 
            mention where people can find your code, and then tell them what commands are available to them.
    
            """
    foo = agent_chain.run(input=template)

    return agent_chain, foo


class SSAWrapper:
    def __init__(self):
        self.agent_chain = None
        self.result = ""
        self.use_voice = False

    async def set_narrative(self):
        self.agent_chain, res = await gaslight()
        return res

    async def speak(self, text: str, should_play: bool, bot):
        await generate_voice_sample(text, should_play, bot)

    async def play_latest(self, bot):
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
                await gaslight()
            )  # Update the attribute after calling set_narrative

        async def generate_voice_sample(self, text: str, should_play: bool):
            await generate_voice_sample(text, should_play, self.bot)

        async def play_latest_voice_sample(self):
            await play_latest_voice_sample(self.bot)

    async def gaslight_second_shift_augie(self):
        await gaslight()


def use_voice():
    return use_voice
