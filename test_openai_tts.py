import asyncio
import os
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI()
    try:
        response = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input="Hello world",
            response_format="pcm"
        )
        print('SUCCESS:', len(response.content), 'bytes')
    except Exception as e:
        print('ERROR:', str(e))

asyncio.run(main())
