import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from api.db.models import ToolModel
async def main():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async_session = sessionmaker(engine)
    async with async_session() as session:
        result = await session.execute(select(ToolModel))
        tools = result.scalars().all()
        for t in tools:
            print(f"Name: {t.name}, Category: {t.category}, Def: {t.definition}")
asyncio.run(main())
