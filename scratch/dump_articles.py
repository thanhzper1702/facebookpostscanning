import asyncio
from playwright.async_api import async_playwright

FB_SESSION_DIR = r"d:\postercontest\fb_session"
POST_URL = "https://www.facebook.com/permalink.php?story_fbid=122315804252064502&id=149883148199221"

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
            print("Navigating to post...")
            await page.goto(POST_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Let's inspect the entire comment area!
            # Find the main post container
            data = await page.evaluate("""() => {
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                return articles.map((a, i) => {
                    const r = a.getBoundingClientRect();
                    return {
                        i: i,
                        aria: a.getAttribute('aria-label') || '',
                        text: (a.innerText || '').substring(0, 100).replace(/\\n/g, ' '),
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height)
                    };
                });
            }""")
            print(f"Total articles: {len(data)}")
            for d in data:
                print(d)

            # Let's see what is beneath the last comment:
            # Let's scroll down step by step and see what loads!
            print("\nScrolling down 10 times and checking new articles...")
            for s in range(10):
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(1.5)
                c = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
                print(f"Scroll step {s}: articles count = {c}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
