# VoxCPM Integration Setup Guide

This guide explains how to set up and use the SecondShiftAugie Discord bot with VoxCPM text-to-speech integration.

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   cp .env.template .env
   # Edit .env with your Discord bot token and channel IDs
   ```

3. **Prepare Reference Files**
   - Place your reference audio file at `assets/model.wav`
   - Place the corresponding transcript at `assets/transcript.txt`

4. **Start the Bot**
   ```bash
   python run_bot.py
   ```

## Configuration

### Required Environment Variables

- `BOT_TOKEN`: Your Discord bot token
- `CHANNEL_ID`: Discord channel ID where the bot will send messages

### Optional Environment Variables

- `VOICE_CHANNEL_ID`: Default voice channel ID for the bot to join
- `SAVE_PATH`: Directory for temporary audio files (default: `./temp_audio`)
- `COMMAND_PREFIX`: Bot command prefix (default: `!`)

### VoxCPM Configuration

- `VOXCPM_MODEL_PATH`: Model path or Hugging Face model ID (default: `openbmb/VoxCPM-0.5B`)
- `VOXCPM_PROMPT_WAV`: Path to reference audio file (default: `assets/model.wav`)
- `VOXCPM_PROMPT_TEXT`: Path to reference text file (default: `assets/transcript.txt`)
- `VOXCPM_CFG_VALUE`: Guidance scale for generation (default: `2.0`)
- `VOXCPM_INFERENCE_STEPS`: Number of inference steps (default: `10`)
- `VOXCPM_NORMALIZE`: Enable text normalization (default: `true`)
- `VOXCPM_DENOISE`: Enable audio denoising (default: `true`)
- `VOXCPM_MAX_LENGTH`: Maximum text length (default: `4096`)

## Usage

### Commands

- `!join` - Join your current voice channel
- `!play` - Replay the last generated voice response
- `!leave` - Leave the current voice channel
- `!help` - Show help message with all commands
- `!status` - Show bot and TTS engine status

### Voice Responses

1. Join a voice channel in Discord
2. Use `!join` to have the bot join your channel
3. Mention the bot (@SecondShiftAugie) in chat
4. The bot will respond with both text and voice

## Reference Files

The bot requires two reference files to generate speech in a specific voice:

### Reference Audio (`assets/model.wav`)
- Should be a clear, high-quality recording
- Recommended length: 10-30 seconds
- Format: WAV, 16kHz sample rate preferred
- Should contain natural speech without background noise

### Reference Text (`assets/transcript.txt`)
- Must contain the exact transcript of the reference audio
- Should be plain text, UTF-8 encoded
- Punctuation should match the speech patterns in the audio

## Troubleshooting

### Bot Won't Start
1. Check that all required environment variables are set:
   ```bash
   python run_bot.py --check-config
   ```
2. Verify your Discord bot token is valid
3. Ensure the bot has proper permissions in your Discord server

### VoxCPM Not Working
1. Check that reference files exist and are readable
2. Verify VoxCPM dependencies are installed correctly
3. Check the bot logs for specific error messages
4. The bot will fall back to text-only mode if VoxCPM fails

### Audio Not Playing
1. Ensure the bot is in a voice channel (`!join`)
2. Check that you have proper voice permissions
3. Verify FFmpeg is installed for audio playback
4. Use `!status` to check the bot's voice connection status

### Performance Issues
- Reduce `VOXCPM_INFERENCE_STEPS` for faster generation
- Lower `VOXCPM_CFG_VALUE` if audio sounds strained
- Ensure adequate system resources (GPU recommended)

## Architecture

The new VoxCPM integration consists of several components:

- **VoxCPM Engine** (`src/tts/voxcpm_engine.py`): Core TTS functionality
- **Discord Manager** (`src/bot/discord_manager.py`): Discord bot and voice operations
- **Message Router** (`src/bot/message_router.py`): Routes messages and coordinates responses
- **Audio Manager** (`src/audio/audio_manager.py`): Manages audio files and playback
- **Command System** (`src/bot/commands.py`): Handles Discord commands
- **Main Application** (`src/main.py`): Coordinates all components

## Development

### Running in Development Mode
```bash
python run_bot.py --verbose
```

### Testing Configuration
```bash
python run_bot.py --check-config
```

### Logs
The bot creates a `bot.log` file with detailed logging information for debugging.

## Requirements

- Python 3.8+
- Discord.py/nextcord
- VoxCPM and dependencies
- FFmpeg (for audio playback)
- Adequate system resources (GPU recommended for VoxCPM)

## Support

If you encounter issues:

1. Check the bot logs (`bot.log`)
2. Verify your configuration with `--check-config`
3. Ensure all dependencies are properly installed
4. Check that reference files are valid and accessible