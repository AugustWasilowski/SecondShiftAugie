import spotipy
from nextcord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials


class SpotifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        auth_manager = SpotifyClientCredentials()
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    @commands.command()
    async def playlists(self, ctx, username: str):
        playlists = self.sp.user_playlists(username)
        while playlists:
            for i, playlist in enumerate(playlists['items']):
                await ctx.send("%4d %s %s" % (i + 1 + playlists['offset'], playlist['uri'], playlist['name']))
            if playlists['next']:
                playlists = self.sp.next(playlists)
            else:
                playlists = None


def setup(bot: commands.Bot):
    bot.add_cog(SpotifyCog(bot))
