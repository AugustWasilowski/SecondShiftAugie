import discord
from discord.ext import commands
from langchain import OpenAI
from langchain.agents import load_tools, initialize_agent


class WolframAlphaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def wolf(self, ctx, *, arg):
        """"Sets status then executes Wolfram Alpha query"""
        if not self.is_busy:
            # await self.working(self.bot)
            await self.execute_wolfram_alpha(ctx, arg)
            # await self.play_latest_voice_sample()
            # await self.wait_for_orders(self.bot)
        # else:
            # await self.generate_voice_sample("I'm busy at the moment. Please wait.")
            # await self.play_latest_voice_sample()

    async def execute_wolfram_alpha(self, ctx, arg):
        """Executes Wolfram Alpha"""
        try:
            wolf_llm = OpenAI(temperature=0)
            tool_names = ["wolfram-alpha"]
            tools = load_tools(tool_names)
            agent = initialize_agent(tools, wolf_llm, agent="zero-shot-react-description", verbose=True)
            result = agent.run(arg)
            await ctx.send(result)
            # await self.generate_voice_sample(result)
        except Exception as e:
            # logger.error(f'General error in Wolfram: {e}')
            await ctx.send(f'Error in Wolfram: {e}.')





