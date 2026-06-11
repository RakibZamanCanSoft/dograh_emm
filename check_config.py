import asyncio
import json
from api.core.db import AsyncSessionLocal
from api.models.user import User

async def run():
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, 1)
            print(json.dumps(user.configuration, indent=2))
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    asyncio.run(run())
