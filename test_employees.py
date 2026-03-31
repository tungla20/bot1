import asyncio
import os
import sqlite3
import httpx
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = sqlite3.connect("bear_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT access_token FROM user_sessions LIMIT 1")
    row = cursor.fetchone()
    if not row:
        print("No sessions.")
        return
    token = row[0]
    url = os.environ.get("ERP_BASE_URL", "https://staging-erp.twendeesoft.com") + "/api/users?page=1&limit=1000"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        
        import os
        from pprint import pprint
        print("TRYING TO DEACTIVATE USER ID via /api/users/{id}...")
        user_id = data[0]["id"]
        status_url = os.environ.get("ERP_BASE_URL", "https://staging-erp.twendeesoft.com") + f"/api/users/{user_id}"
        put_resp = await client.patch(status_url, headers={"Authorization": f"Bearer {token}"}, json={"status": "INACTIVE"})
        print("Status Code:", put_resp.status_code)
        print("Response:", put_resp.text)

asyncio.run(main())
