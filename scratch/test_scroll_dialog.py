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

            # 1. Identify post container (dialog if present, else main)
            container_info = await page.evaluate("""() => {
                const dialogs = document.querySelectorAll('div[role="dialog"]');
                let target = null;
                for (const d of dialogs) {
                    if (d.innerText.includes('Bình luận') || d.innerText.includes('Chia sẻ') || d.innerText.includes('Thích')) {
                        target = d;
                        break;
                    }
                }
                const el = target || document.querySelector('div[role="main"]') || document.body;
                
                // Find its scrollable parent/container
                let scrollable = null;
                const divs = [el, ...Array.from(el.querySelectorAll('div'))];
                for (const d of divs) {
                    const s = window.getComputedStyle(d);
                    if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight + 50) {
                        scrollable = d;
                        break;
                    }
                }
                return {
                    hasTargetDialog: target != null,
                    scrollableFound: scrollable != null,
                    scrollHeight: scrollable ? scrollable.scrollHeight : document.body.scrollHeight,
                    clientHeight: scrollable ? scrollable.clientHeight : window.innerHeight
                };
            }""")
            print("Container info:", container_info)

            # 2. Check sort button inside the dialog
            sort_result = await page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"]') || document.body;
                const buttons = Array.from(dialog.querySelectorAll('div[role="button"], span'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'Phù hợp nhất' || t === 'Most relevant' || t.includes('Phù hợp nhất')) {
                        b.click();
                        return t;
                    }
                }
                return null;
            }""")
            print(f"Sort button in dialog clicked: {sort_result}")
            if sort_result:
                await asyncio.sleep(1.2)
                opt_result = await page.evaluate("""() => {
                    const items = document.querySelectorAll('div[role="menuitem"], div[role="option"], span');
                    for (const it of items) {
                        const t = (it.innerText || '').trim();
                        if (t === 'Tất cả bình luận' || t === 'All comments' || t.includes('Tất cả bình luận')) {
                            it.click();
                            return t;
                        }
                    }
                    return null;
                }""")
                print(f"Switched to: {opt_result}")
                await asyncio.sleep(2)

            # 3. Expand comments and scroll INSIDE the dialog
            print("\nExpanding comments and scrolling container...")
            for step in range(35):
                # Expand buttons inside dialog
                clicked = await page.evaluate("""() => {
                    const dialog = document.querySelector('div[role="dialog"]') || document.body;
                    const all = Array.from(dialog.querySelectorAll('div[role="button"], span'));
                    const matches = all.filter(el => {
                        const t = (el.innerText || '').trim();
                        if (t.length === 0 || t.length > 60) return false;
                        const tl = t.toLowerCase();
                        return (
                            tl.includes('xem thêm bình luận') ||
                            tl.includes('xem các bình luận') ||
                            tl.includes('bình luận trước') ||
                            tl.includes('bình luận cũ hơn') ||
                            tl.includes('câu trả lời') ||
                            tl.includes('phản hồi') ||
                            tl.includes('view more comments') ||
                            tl.includes('view previous comments')
                        );
                    });

                    if (matches.length > 0) {
                        matches.sort((a, b) => a.innerText.trim().length - b.innerText.trim().length);
                        const target = matches[0];
                        target.scrollIntoView({ block: 'center', behavior: 'instant' });
                        target.click();
                        return target.innerText.trim();
                    }
                    return null;
                }""")

                # Scroll the container inside dialog
                scroll_info = await page.evaluate("""() => {
                    const dialog = document.querySelector('div[role="dialog"]') || document.body;
                    let scrollable = null;
                    const divs = [dialog, ...Array.from(dialog.querySelectorAll('div'))];
                    for (const d of divs) {
                        const s = window.getComputedStyle(d);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight + 50) {
                            scrollable = d;
                            break;
                        }
                    }
                    if (scrollable) {
                        scrollable.scrollTop += 600;
                        scrollable.dispatchEvent(new Event('scroll', { bubbles: true }));
                        return { scrollTop: scrollable.scrollTop, max: scrollable.scrollHeight - scrollable.clientHeight };
                    } else {
                        window.scrollBy(0, 600);
                        return { windowScrollY: window.scrollY };
                    }
                }""")

                # Also mouse wheel in center
                await page.mouse.move(640, 500)
                await page.mouse.wheel(0, 600)
                await asyncio.sleep(1.0)

                count = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
                print(f"Step {step}: clicked='{clicked}', scroll={scroll_info}, articles={count}")

            # 4. Extract all comments!
            comments_extracted = await page.evaluate("""() => {
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                const results = [];
                const seen = new Set();
                for (const art of articles) {
                    const aria = art.getAttribute('aria-label') || '';
                    const links = Array.from(art.querySelectorAll('a[role="link"]'));
                    let author = null;
                    let authorUrl = null;
                    for (const l of links) {
                        const h = l.getAttribute('href') || '';
                        const t = (l.innerText || '').trim();
                        if (h && t && !h.includes('permalink.php')) {
                            const cleanH = h.split('?')[0].replace(/\\/$/, '');
                            if (!authorUrl) {
                                authorUrl = cleanH;
                                author = t.split('\\n')[0].trim();
                            }
                        }
                    }
                    if (author && authorUrl && !seen.has(authorUrl + '___' + author)) {
                        seen.add(authorUrl + '___' + author);
                        results.push({ author, authorUrl, aria: aria.substring(0, 60) });
                    }
                }
                return results;
            }""")

            print(f"\n==========================================")
            print(f"TOTAL UNIQUE COMMENTS EXTRACTED: {len(comments_extracted)}")
            for idx, c in enumerate(comments_extracted[:15]):
                print(f"  [{idx+1}] {c['author']} ({c['authorUrl']})")
            print(f"==========================================")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
