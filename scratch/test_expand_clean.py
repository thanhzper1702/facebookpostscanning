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

            # Find real candidates with length < 60
            candidates = await page.evaluate("""() => {
                const results = [];
                const all = document.querySelectorAll('div[role="button"], span');
                for (const el of all) {
                    const t = (el.innerText || '').trim();
                    if (t.length > 0 && t.length < 60) {
                        const tl = t.toLowerCase();
                        if (
                            tl.includes('xem thêm') ||
                            tl.includes('bình luận') ||
                            tl.includes('phù hợp') ||
                            tl.includes('trả lời')
                        ) {
                            const rect = el.getBoundingClientRect();
                            results.push({
                                text: t,
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                y: Math.round(rect.y),
                                visible: rect.width > 0 && rect.height > 0
                            });
                        }
                    }
                }
                return results;
            }""")
            print(f"Found {len(candidates)} candidates with text < 60:")
            for c in candidates:
                print("  ", c)

            # Test clicking actual short 'Xem thêm bình luận'
            print("\nTesting expanding with specific innermost click...")
            for step in range(15):
                count_before = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
                clicked_text = await page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('div[role="button"], span'));
                    // Filter matching candidates with short text
                    const matches = all.filter(el => {
                        const t = (el.innerText || '').trim();
                        if (t.length === 0 || t.length > 60) return false;
                        const tl = t.toLowerCase();
                        return (
                            tl.includes('xem thêm bình luận') ||
                            tl.includes('xem các bình luận') ||
                            tl.includes('bình luận trước') ||
                            tl.includes('bình luận cũ hơn') ||
                            tl.includes('view more comments') ||
                            tl.includes('view previous comments')
                        );
                    });

                    if (matches.length > 0) {
                        // Pick the one with shortest innerText (most specific/innermost)
                        matches.sort((a, b) => a.innerText.trim().length - b.innerText.trim().length);
                        const target = matches[0];
                        target.scrollIntoView({ block: 'center', behavior: 'instant' });
                        target.click();
                        return target.innerText.trim();
                    }
                    return null;
                }""")

                # Scroll down as well
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(1.2)
                count_after = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
                print(f"Step {step}: clicked='{clicked_text}', articles: {count_before} -> {count_after}")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
