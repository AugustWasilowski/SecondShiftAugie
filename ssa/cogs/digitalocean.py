import json
import logging
import os
from datetime import datetime, timedelta

import requests
from nextcord.ext import commands

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup(bot: commands.Bot):
    bot.add_cog(DigitalOceanCog(bot))


async def exe_cpu(ctx):
    # Set up API authentication
    api_token = os.getenv("DIGITAL_OCEAN_API_KEY")
    headers = {'Authorization': f'Bearer {api_token}'}

    # Specify the droplet ID and metric type
    droplet_id = os.getenv("DIGITAL_OCEAN_DROPLET_ID")
    metric_type = 'cpu'

    # Make the API request
    # Calculate start and end timestamps
    end_time = datetime.now().timestamp()
    start_time = (datetime.now() - timedelta(hours=6)).timestamp()

    # Make API request with updated timestamps
    response = requests.get(
        f'https://api.digitalocean.com/v2/monitoring/metrics/droplet/cpu?host_id={droplet_id}&start={start_time:.0f}&end={end_time:.0f}',
        headers=headers)

    # Parse the response JSON
    data = json.loads(response.text) # TODO: this returns a bunch of matrix data and I don't know how to use it.

    # Print the metrics data
    logger.info(data)



class DigitalOceanCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def cpu(self, ctx):
        await exe_cpu(ctx)

