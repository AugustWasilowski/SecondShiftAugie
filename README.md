# SecondShiftAugie Discord Bot

AI-powered Discord bot with intelligent conversations and voice responses using VoxCPM TTS and Ollama AI.

## Features

- **AI Conversations**: Intelligent responses using Ollama with Qwen2.5 model
- **Voice Synthesis**: High-quality text-to-speech using VoxCPM
- **Slash Commands**: Modern Discord command interface
- **Voice Channel Integration**: Automatic audio playback in voice channels
- **Graceful Degradation**: Continues working even when AI services are unavailable

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

## Commands

The bot uses modern Discord slash commands:

- `/join` - Join your current voice channel
- `/play` - Replay the last generated voice response
- `/leave` - Leave the current voice channel
- `/help` - Show available commands and usage information
- `/health` - Show detailed bot and system health status

## Usage

1. Join a voice channel in Discord
2. Use `/join` to have the bot join your channel
3. Mention the bot (@SecondShiftAugie) in chat
4. The bot will respond with both text and AI-generated voice

## Configuration

### Required Environment Variables

- `BOT_TOKEN`: Your Discord bot token
- `CHANNEL_ID`: Discord channel ID where the bot will send messages

### Optional Environment Variables

- `VOICE_CHANNEL_ID`: Default voice channel ID for the bot to join
- `SAVE_PATH`: Directory for temporary audio files (default: `./temp_audio`)

### VoxCPM Configuration

- `VOXCPM_MODEL_PATH`: Model path or Hugging Face model ID (default: `openbmb/VoxCPM-0.5B`)
- `VOXCPM_PROMPT_WAV`: Path to reference audio file (default: `assets/model.wav`)
- `VOXCPM_PROMPT_TEXT`: Path to reference text file (default: `assets/transcript.txt`)

### Ollama AI Configuration

- `OLLAMA_BASE_URL`: Ollama API endpoint (default: `http://localhost:11434`)
- `OLLAMA_MODEL`: AI model to use (default: `qwen2.5:1.7b`)
- `SYSTEM_PROMPT_FILE`: System prompt configuration file (default: `ollama_system_prompt.json`)
