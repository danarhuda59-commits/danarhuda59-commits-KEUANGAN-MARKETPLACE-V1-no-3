"""Buat 1 akun admin (owner) baru. Kredensial dari env ADMIN_EMAIL / ADMIN_PASSWORD, tidak pernah hardcode.

Pakai: cd backend && python scripts/create_admin.py   (baca .env otomatis)
"""
import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter, EmailStr  # noqa: E402


async def main():
    email = (os.environ.get("ADMIN_EMAIL") or "").lower().strip()
    pw = os.environ.get("ADMIN_PASSWORD") or ""
    name = os.environ.get("ADMIN_NAME") or "Pemilik Usaha"
    business = os.environ.get("ADMIN_BUSINESS_NAME") or "Usaha Saya"
    if not email or not pw:
        sys.exit("ADMIN_EMAIL dan ADMIN_PASSWORD wajib diisi di environment")
    if len(pw) < 6:
        sys.exit("ADMIN_PASSWORD minimal 6 karakter")
    TypeAdapter(EmailStr).validate_python(email)

    from core import db, client
    from routers.auth import create_user_with_business

    if await db.users.find_one({"email": email}):
        sys.exit(f"User {email} sudah ada, tidak ada perubahan")
    user = await create_user_with_business(name, email, pw, business)
    print(f"Admin dibuat: {user['email']} (role={user['role']}, business_id={user['business_id']})")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
