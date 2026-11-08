"""Fix telnumber column size for deployment."""
from database import engine
from sqlalchemy import text
import asyncio

async def fix():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users ALTER COLUMN telnumber TYPE VARCHAR(512)"))
        print("users.telnumber -> VARCHAR(512)")

asyncio.run(fix())
