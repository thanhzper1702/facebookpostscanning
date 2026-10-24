import asyncio
import sys
import os
sys.path.insert(0, r"d:\postercontest")
from scraper import FacebookScraper

POST_URL = "https://www.facebook.com/permalink.php?story_fbid=122315804252064502&id=149883148199221"

async def report(stage, pct, msg, counts):
    print(f"[{pct}%] {stage}: {msg}")

async def main():
    scraper = FacebookScraper()
    res = await scraper.scrape_post(POST_URL, progress_cb=report)
    print("\n--- SCRAPE FINISHED ---")
    print("Status:", res.get("status"))
    print("Reactions total detected:", res.get("reactions_total"))
    print("Reactions breakdown:", res.get("reactions_breakdown"))
    rx = res.get("reactions", [])
    cm = res.get("comments", [])
    sh = res.get("shares", [])
    print(f"Total Reactions extracted: {len(rx)}")
    print(f"Total Comments extracted: {len(cm)}")
    print(f"Total Shares extracted: {len(sh)}")

if __name__ == "__main__":
    asyncio.run(main())
