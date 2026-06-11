import asyncio
import json
from api.db.db_client import DBClient
from api.db.models.user import User
from sqlalchemy.future import select
import httpx

async def run():
    try:
        db = DBClient()
        async with db.get_session() as session:
            result = await session.execute(select(User).where(User.id == 1))
            user = result.scalar_one_or_none()
            if not user:
                print("User 1 not found")
                return

            tts_config = user.configuration.get("tts", {})
            api_key = tts_config.get("api_key")
            if not api_key:
                print("No TTS API key configured!")
                return
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini-tts",
                "voice": "coral",
                "input": "This is a test of the new model.",
                "response_format": "pcm"
            }
            async with httpx.AsyncClient() as client:
                print(f"Sending request to OpenAI with key: {api_key[:5]}...{api_key[-4:]}")
                resp = await client.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
                print("Status Code:", resp.status_code)
                if resp.status_code != 200:
                    print("Error:", resp.text)
                else:
                    print("Success! Received audio bytes:", len(resp.content))
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    asyncio.run(run())
