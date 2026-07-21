
import asyncio
from api.db import db_client
from api.utils.auth import hash_password
from api.db.models import UserModel
from sqlalchemy import update

async def main():
    new_hash = hash_password('password123')
    async with db_client.async_session() as session:
        await session.execute(update(UserModel).where(UserModel.email == 'manager@test.com').values(password_hash=new_hash))
        await session.execute(update(UserModel).where(UserModel.email == 'test@example.com').values(password_hash=new_hash))
        await session.commit()
    print('Password reset successfully')

asyncio.run(main())

