"""Handles running the application from the command line.

"""
import os
import argparse

from dotenv import load_dotenv

import breathe


load_dotenv()  # load environment variables from .env file


class EnvDefault(argparse.Action):
    """Taken straight from https://stackoverflow.com/a/10551190
    Used to set environment variables using argparse
    """
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if not default and envvar:
            if envvar in os.environ:
                default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required,
                                         **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def run():
    """Runs the application after parsing the arguments that may have been
    passed in."""
    parser = argparse.ArgumentParser(description="Breathes life into Second Shift Augie (S.S.A.)",
                                     epilog="This has been brought to you by the letters A, W, S, and M.")
    parser.add_argument('--speak', '-s', action='store_true', default=True, dest='speak',
                        help='Give voice to your child? Default is True.')
    parser.add_argument('--bot-token', '-b', action=EnvDefault, envvar='BOT_TOKEN',
                        help='The Discord bot token (can be specified using the BOT_TOKEN environment variable).')
    parser.add_argument('--channel-id', '-c', action=EnvDefault, envvar='CHANNEL_ID',
                        help='The Discord channel id that S.S.A. will log into. Can also be specified using the '
                             'CHANNEL_ID environment variable).')
    parser.add_argument('--voice-channel-id', '-v', action=EnvDefault, envvar='VOICE_CHANNEL_ID',
                        help='The voice channel id for S.S.A. to join when asked to. Can also be specified using the '
                             'VOICE_CHANNEL_ID environment variable.')
    parser.add_argument('--save-path', action=EnvDefault, envvar='SAVE_PATH',
                        help='Where S.S.A. saves audio and other temporary files. If not specified, will default to '
                             'creating a secure temporary directory. Can also be specified using the BOT_TOKEN '
                             'environment variable.')
    parsed = parser.parse_args()
    breathe.life(parsed)
    # @todo - left off here - I don't love the idea of passing parsed here.
    #  Better to pass the arguments so that there's no additional parsing that needs to be done there.
    return


if __name__ == "__main__":
    run()
