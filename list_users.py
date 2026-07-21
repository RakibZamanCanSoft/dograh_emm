
import asyncio
from api.db import db_client
from api.db.models import UserModel
from sqlalchemy import select

async def main():
    async with db_client.async_session() as session:
        result = await session.execute(select(UserModel.email, UserModel.id))
        users = result.fetchall()
        print('Users in DB:')
        for u in users:
            print(f'Email: {u[0]}, ID: {u[1]}')

asyncio.run(main())

