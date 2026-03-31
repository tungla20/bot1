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
    
    url = os.environ.get("ERP_BASE_URL", "https://staging-erp.twendeesoft.com") + "/api/hr/employees?page=1&limit=5&search=sprucele@gmail.com"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        print(resp.text)

asyncio.run(main())
