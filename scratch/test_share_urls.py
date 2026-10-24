import asyncio
from playwright.async_api import async_playwright

FB_SESSION_DIR = r"d:\postercontest\fb_session"
FBID = "122315804252064502"

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=FB_SESSION_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-notifications"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            urls_to_test = [
                f"https://www.facebook.com/shares/view?id={FBID}",
                f"https://m.facebook.com/browse/shares?id={FBID}",
                f"https://mbasic.facebook.com/browse/shares?id={FBID}",
            ]
            for u in urls_to_test:
                print(f"\n--- Testing URL: {u} ---")
                try:
                    resp = await page.goto(u, wait_until="domcontentloaded", timeout=15000)
                    print(f"Status: {resp.status if resp else 'None'}")
                    await asyncio.sleep(2)
                    title = await page.title()
                    url_now = page.url
                    print(f"Final URL: {url_now}")
                    print(f"Title: {title}")
                    body_text = (await page.inner_text("body"))[:300].replace('\n', ' ')
                    print(f"Body snippet: {body_text}")
                except Exception as e:
                    print(f"Error: {e}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
