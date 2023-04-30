from nextcord.ext import commands

def setup(bot: commands.Bot):
    bot.add_cog(SummaryCog(bot))

class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False