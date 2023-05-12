import json
import logging
import sys

import websockets
from nextcord.ext import commands

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def on_message(ws, message):
    logger.info(message)


def on_error(ws, error):
    logger.error(error)


def on_close(ws, close_status_code, close_msg):
    logger.info("### closed ###")


def on_open(ws):
    logger.info("Opened connection")


async def print_response_stream(ctx, prompt):
    async for response in run(prompt):
        print(response, end='')
        sys.stdout.flush()  # If we don't flush, we won't see tokens in realtime.


class WebSocketWrapper(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.is_busy = False

    @commands.command()
    async def ws(self, ctx, *arg):
        # asyncio.run(print_response_stream(args))
        await print_response_stream(ctx, run(arg))


def setup(bot: commands.Bot):
    bot.add_cog(WebSocketWrapper(bot))


async def run(context):
    # Note: the selected defaults change from time to time.
    request = {
        'prompt': context,
        'max_new_tokens': 250,
        'do_sample': True,
        'temperature': 1.3,
        'top_p': 0.1,
        'typical_p': 1,
        'repetition_penalty': 1.18,
        'top_k': 40,
        'min_length': 0,
        'no_repeat_ngram_size': 0,
        'num_beams': 1,
        'penalty_alpha': 0,
        'length_penalty': 1,
        'early_stopping': False,
        'seed': -1,
        'add_bos_token': True,
        'truncation_length': 2048,
        'ban_eos_token': False,
        'skip_special_tokens': True,
        'stopping_strings': []
    }
    HOST = 'localhost:5005'
    URI = f'ws://{HOST}/api/v1/stream'
    async with websockets.connect(URI, ping_interval=None) as websocket:
        await websocket.send(json.dumps(request))

        yield context  # Remove this if you just want to see the reply

        while True:
            incoming_data = await websocket.recv()
            incoming_data = json.loads(incoming_data)

            match incoming_data['event']:
                case 'text_stream':
                    yield incoming_data['text']
                case 'stream_end':
                    return
