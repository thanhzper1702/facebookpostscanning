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
            print(f"Navigating to {POST_URL}...")
            await page.goto(POST_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Let's inspect all articles and their HTML
            articles = await page.locator('div[role="article"]').all()
            print(f"Initial div[role='article'] count: {len(articles)}")

            # Let's see what buttons match 'Xem thêm bình luận' or 'bình luận' using Playwright locator
            more_btns = await page.locator('text=/Xem thêm.*bình luận|Xem.*bình luận trước|Xem tất cả.*bình luận/i').all()
            print(f"Playwright locators for more comments: {len(more_btns)}")
            for idx, b in enumerate(more_btns):
                try:
                    txt = await b.inner_text()
                    vis = await b.is_visible()
                    box = await b.bounding_box()
                    print(f"  Btn {idx}: text={txt!r}, visible={vis}, box={box}")
                except Exception as e:
                    print(f"  Btn {idx}: error {e}")

            # Also check if there's any dropdown / sorting button:
            # Let's dump all text around the reaction/comment stats
            stat_text = await page.evaluate("""() => {
                const results = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    const val = node.nodeValue.trim();
                    if (val.includes('bình luận') || val.includes('Phù hợp') || val.includes('Tất cả')) {
                        const p = node.parentElement;
                        results.push({ text: val, tag: p.tagName, role: p.getAttribute('role'), class: p.className });
                    }
                }
                return results;
            }""")
            print("\nText nodes mentioning comments / sort:")
            for s in stat_text[:15]:
                print(" ", s)

            # Test clicking the first Playwright more_btn!
            if more_btns:
                print("\nClicking first Playwright more_btn with real mouse click...")
                await more_btns[0].scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                await more_btns[0].click(timeout=3000)
                await asyncio.sleep(3)

                articles_after = await page.locator('div[role="article"]').all()
                print(f"Articles count after Playwright click: {len(articles_after)}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
