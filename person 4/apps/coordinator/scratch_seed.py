import asyncio
import uuid
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from coordinator.database.models import User

async def seed():
    engine = create_async_engine('sqlite+aiosqlite:///./test_coordinator.db')
    async_session = async_sessionmaker(engine)
    user = User(id=uuid.uuid4(), email='test@example.com', display_name='Test User')
    async with async_session() as session:
        session.add(user)
        await session.commit()
        print(user.id)

asyncio.run(seed())
