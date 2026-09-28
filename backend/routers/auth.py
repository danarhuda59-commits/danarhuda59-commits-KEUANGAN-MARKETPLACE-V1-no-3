from fastapi import APIRouter, Depends, Response, Request, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from core import db, new_id, now_iso, hash_password, verify_password, create_token, decode_token, current_user, user_from_token, audit

router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_UNITS = [("kg", "Kilogram"), ("gram", "Gram"), ("liter", "Liter"), ("ml", "Mililiter"), ("pcs", "Pieces"),
                 ("pack", "Pack"), ("dus", "Dus"), ("botol", "Botol"), ("lembar", "Lembar"), ("porsi", "Porsi"), ("cup", "Cup")]
DEFAULT_CONVERSIONS = [("kg", "gram", 1000), ("liter", "ml", 1000)]
DEFAULT_CATEGORIES = [("material", "Bahan Utama"), ("material", "Bumbu & Rempah"), ("material", "Kemasan"), ("material", "Bahan Pelengkap"),
                      ("product", "Makanan"), ("product", "Minuman"), ("product", "Frozen Food"), ("product", "Snack")]
CHANNELS = ["Offline", "Website", "WhatsApp", "Shopee", "TikTok Shop", "Tokopedia", "Marketplace lainnya"]


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    business_name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


async def seed_business_defaults(bid):
    ts = now_iso()
    if not await db.units.find_one({"business_id": bid}):
        await db.units.insert_many([{"id": new_id(), "business_id": bid, "code": c, "name": n, "created_at": ts} for c, n in DEFAULT_UNITS])
        await db.unit_conversions.insert_many([{"id": new_id(), "business_id": bid, "from_unit": f, "to_unit": t, "factor": v, "created_at": ts} for f, t, v in DEFAULT_CONVERSIONS])
    if not await db.categories.find_one({"business_id": bid}):
        await db.categories.insert_many([{"id": new_id(), "business_id": bid, "type": t, "name": n, "created_at": ts} for t, n in DEFAULT_CATEGORIES])
    if not await db.channels.find_one({"business_id": bid}):
        await db.channels.insert_many([{"id": new_id(), "business_id": bid, "name": c, "is_active": True, "created_at": ts} for c in CHANNELS])
    if not await db.cash_accounts.find_one({"business_id": bid}):
        await db.cash_accounts.insert_one({"id": new_id(), "business_id": bid, "name": "Kas Utama", "type": "cash", "opening_balance": 0, "is_default": True, "created_at": ts})


async def create_user_with_business(name, email, password, business_name, role="owner"):
    bid = new_id()
    ts = now_iso()
    await db.businesses.insert_one({"id": bid, "name": business_name, "owner_email": email, "address": "", "phone": "", "logo_url": "", "target_margin": 30, "created_at": ts})
    user = {"id": new_id(), "business_id": bid, "name": name, "email": email, "role": role, "created_at": ts}
    await db.users.insert_one({**user, "password_hash": hash_password(password)})
    await seed_business_defaults(bid)
    return user


def set_cookies(response: Response, user_id):
    access, refresh = create_token(user_id, "access", 24), create_token(user_id, "refresh", 24 * 7)
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=86400, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return access


@router.post("/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower().strip()
    if len(body.password) < 6:
        raise HTTPException(400, "Password minimal 6 karakter")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email sudah terdaftar")
    user = await create_user_with_business(body.name.strip(), email, body.password, body.business_name.strip() or "Usaha Saya")
    token = set_cookies(response, user["id"])
    return {"user": user, "token": token}


@router.post("/login")
async def login(body: LoginIn, response: Response, request: Request):
    email = body.email.lower().strip()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    from datetime import datetime, timezone, timedelta
    if att and att.get("count", 0) >= 5 and att.get("last") and datetime.fromisoformat(att["last"]) > datetime.now(timezone.utc) - timedelta(minutes=15):
        raise HTTPException(429, "Terlalu banyak percobaan login. Coba lagi dalam 15 menit")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        raise HTTPException(401, "Email atau password salah")
    await db.login_attempts.delete_many({"identifier": ident})
    user.pop("_id", None)
    user.pop("password_hash", None)
    token = set_cookies(response, user["id"])
    return {"user": user, "token": token}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "Tidak ada refresh token")
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Token salah")
    access = set_cookies(response, payload["sub"])
    return {"token": access}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(current_user)):
    biz = await db.businesses.find_one({"id": user["business_id"]}, {"_id": 0})
    return {"user": user, "business": biz}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user=Depends(current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(body.old_password, full["password_hash"]):
        raise HTTPException(400, "Password lama salah")
    if len(body.new_password) < 6:
        raise HTTPException(400, "Password baru minimal 6 karakter")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await audit(user["business_id"], user, "change_password", "user", user["id"])
    return {"ok": True}
