"""Hapus data uji: user/bisnis TEST & admin lama, plus semua transaksi berprefix TEST_ di bisnis admin. Idempotent."""
import os, asyncio, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

TX_COLLECTIONS = ["suppliers", "raw_materials", "material_price_history", "products", "recipes", "recipe_items", "production_orders", "production_items",
                  "inventory_transactions", "purchases", "sales", "expenses", "cash_transactions", "bep_calculations", "hpp_calculations", "audit_logs", "counters",
                  "sales_fees", "packaging_items", "packaging_costs", "sales_orders", "marketplace_imports", "marketplace_settlements", "login_attempts"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin_email = os.environ["ADMIN_EMAIL"]
    removed = {}
    stale = await db.users.find({"email": {"$ne": admin_email}}, {"_id": 0, "business_id": 1, "email": 1}).to_list(100)
    stale_bids = {u["business_id"] for u in stale}
    if stale_bids:
        for c in await db.list_collection_names():
            r = await db[c].delete_many({"business_id": {"$in": list(stale_bids)}})
            if r.deleted_count:
                removed[c] = removed.get(c, 0) + r.deleted_count
        r = await db.businesses.delete_many({"id": {"$in": list(stale_bids)}})
        removed["businesses"] = r.deleted_count
        r = await db.users.delete_many({"email": {"$ne": admin_email}})
        removed["users"] = r.deleted_count
    admin = await db.users.find_one({"email": admin_email}, {"_id": 0, "business_id": 1})
    if admin:
        bid = admin["business_id"]
        for c in TX_COLLECTIONS:
            r = await db[c].delete_many({"business_id": bid})
            if r.deleted_count:
                removed[c] = removed.get(c, 0) + r.deleted_count
        await db.cash_accounts.delete_many({"business_id": bid, "is_default": {"$ne": True}})
        await db.cash_accounts.update_many({"business_id": bid}, {"$set": {"opening_balance": 0}})
    print("removed:", removed)

asyncio.run(main())
