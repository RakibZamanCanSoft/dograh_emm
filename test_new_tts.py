import asyncio
import os
import httpx

async def test_openai():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY first")
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
        resp = await client.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
        print("Status:", resp.status_code)
        if resp.status_code != 200:
            print("Error:", resp.text)
        else:
            print("Success! Got bytes:", len(resp.content))

if __name__ == "__main__":
    asyncio.run(test_openai())
