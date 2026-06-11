import asyncio
import json
import sys
from api.db.database import get_db
from api.db.models.user import User
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

async def run():
    try:
        async for session in get_db():
            result = await session.execute(select(User).where(User.id == 1))
            user = result.scalar_one_or_none()
            if user:
                print("USER CONFIG:")
                print(json.dumps(user.configuration, indent=2))
            else:
                print("User 1 not found")
            break
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(run())
