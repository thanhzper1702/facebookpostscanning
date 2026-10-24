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

            # Let's inspect the HTML around the reaction bar & action bar
            # Look at elements between y=1000 and y=1400
            html_snippet = await page.evaluate("""() => {
                const el = document.querySelector('div[role="button"][aria-label*="Chia sẻ"]');
                if (!el) return 'Not found';
                // Find parent container containing the action bar and counters
                let parent = el;
                for (let i = 0; i < 6; i++) {
                    if (parent.parentElement) parent = parent.parentElement;
                }
                return {
                    text: parent.innerText,
                    html: parent.innerHTML.substring(0, 3000)
                };
            }""")
            print("Parent text:")
            print(html_snippet.get("text") if isinstance(html_snippet, dict) else html_snippet)

            # Let's see if there are any links (a tag) with /shares or sharer or similar
            share_links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a, span[role="button"], div[role="button"]')).filter(a => {
                    const t = (a.innerText || '').toLowerCase();
                    const h = (a.getAttribute('href') || '').toLowerCase();
                    return t.includes('chia sẻ') || t.includes('share') || h.includes('share');
                }).map(a => ({
                    tag: a.tagName,
                    role: a.getAttribute('role'),
                    href: a.getAttribute('href'),
                    aria: a.getAttribute('aria-label'),
                    text: (a.innerText || '').replace(/\\n/g, ' ')
                }));
            }""")
            print("\nAll share elements/links:")
            for s in share_links:
                print(s)

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
