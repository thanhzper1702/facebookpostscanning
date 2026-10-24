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

            # Let's inspect the span with txt='31'
            span_info = await page.evaluate("""() => {
                const spans = Array.from(document.querySelectorAll('span')).filter(s => s.innerText.trim() === '31');
                return spans.map(s => {
                    const rect = s.getBoundingClientRect();
                    return {
                        html: s.outerHTML,
                        parentTag: s.parentElement ? s.parentElement.tagName : null,
                        parentRole: s.parentElement ? s.parentElement.getAttribute('role') : null,
                        parentAria: s.parentElement ? s.parentElement.getAttribute('aria-label') : null,
                        parentHtml: s.parentElement ? s.parentElement.outerHTML.substring(0, 300) : null,
                        x: rect.x,
                        y: rect.y
                    };
                });
            }""")
            print("Span '31' info:")
            for s in span_info:
                print(s)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
