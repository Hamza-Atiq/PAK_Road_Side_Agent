"""One-time script: create admin user if one doesn't exist yet."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.enums import UserRole
from app.services.security import hash_password

async def main():
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.phone == "+15550000001"))
        if existing:
            print(f"Admin already exists: {existing.id}")
            return
        admin = User(
            phone="+15550000001",
            name="System Admin",
            email="admin@roadside.test",
            role=UserRole.admin.value,
            password_hash=hash_password("admin123"),
            is_active=True,
            is_phone_verified=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Admin created: {admin.id}")

asyncio.run(main())
