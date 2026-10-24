import asyncio
import os
import re
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

            # Dump all short text buttons on page
            buttons_overview = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('div[role="button"], span[role="button"], a[role="button"], span');
                const list = [];
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t.length > 0 && t.length < 50 && b.children.length <= 2) {
                        const r = b.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            list.push({ text: t, tag: b.tagName, role: b.getAttribute('role'), y: Math.round(r.y) });
                        }
                    }
                }
                return list;
            }""")
            print(f"Found {len(buttons_overview)} short buttons/spans on page.")
            for b in buttons_overview:
                if any(k in b['text'].lower() for k in ['bình luận', 'phù hợp', 'tất cả', 'xem thêm', 'trả lời', 'comment', 'relevant', 'more', 'previous']):
                    print("  Interesting button:", b)

            # Step 1: Check sort menu
            # Look for button that might be the sort dropdown
            sort_clicked = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('div[role="button"], span');
                for (const b of buttons) {
                    const t = (b.innerText || '').trim().toLowerCase();
                    if (t.length < 40 && (t.includes('phù hợp nhất') || t.includes('most relevant'))) {
                        b.click();
                        return t;
                    }
                }
                return null;
            }""")
            print("Sort dropdown click result:", sort_clicked)
            if sort_clicked:
                await asyncio.sleep(1.2)
                # Select "Tất cả bình luận"
                opt_clicked = await page.evaluate("""() => {
                    const items = document.querySelectorAll('div[role="menuitem"], div[role="option"], span, div[role="button"]');
                    for (const it of items) {
                        const t = (it.innerText || '').trim().toLowerCase();
                        if (t.length < 50 && (t === 'tất cả bình luận' || t === 'all comments' || t.includes('tất cả bình luận'))) {
                            it.click();
                            return t;
                        }
                    }
                    return null;
                }""")
                print("Clicked 'Tất cả bình luận':", opt_clicked)
                await asyncio.sleep(2)

            # Step 2: Loop to expand comments and scroll
            print("\n--- Expanding Comments ---")
            for step in range(30):
                # Count current comments
                curr_count = await page.evaluate("() => document.querySelectorAll('div[role=\"article\"]').length")
                
                # Find all REAL expand buttons (text length < 60 and no big children)
                clicked_info = await page.evaluate("""() => {
                    const candidates = [];
                    const all = document.querySelectorAll('div[role="button"], span[role="button"], span');
                    for (const el of all) {
                        const t = (el.innerText || '').trim();
                        const tl = t.toLowerCase();
                        if (t.length > 0 && t.length < 70) {
                            if (
                                tl.includes('xem thêm bình luận') || 
                                tl.includes('xem các bình luận') || 
                                tl.includes('bình luận trước') ||
                                tl.includes('bình luận cũ hơn') ||
                                tl.includes('view more comments') || 
                                tl.includes('view previous comments') ||
                                tl.includes('câu trả lời') ||
                                tl.includes('phản hồi') ||
                                tl.includes('replies')
                            ) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    candidates.push({ el, text: t, y: r.y });
                                }
                            }
                        }
                    }
                    if (candidates.length > 0) {
                        // Click the first candidate
                        candidates[0].el.click();
                        return candidates[0].text;
                    }
                    return null;
                }""")

                print(f"Step {step}: articles={curr_count}, clicked={clicked_info}")

                if clicked_info:
                    await asyncio.sleep(1.0)
                else:
                    # Scroll down gently
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(0.7)

            # Final check of comments
            final_data = await page.evaluate("""() => {
                const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                return articles.map(art => {
                    const aria = art.getAttribute('aria-label') || '';
                    const links = Array.from(art.querySelectorAll('a[role="link"]')).map(l => ({
                        text: l.innerText,
                        href: l.getAttribute('href')
                    })).filter(l => l.href && !l.href.includes('permalink.php'));
                    return { aria, user: links[0] || null };
                });
            }""")

            print(f"\n==========================================")
            print(f"TOTAL ARTICLES FOUND: {len(final_data)}")
            valid_users = [a['user'] for a in final_data if a['user'] and a['user']['text']]
            print(f"TOTAL VALID USERS EXTRACTED: {len(valid_users)}")
            unique_urls = set(u['href'].split('?')[0] for u in valid_users)
            print(f"UNIQUE USER URLS: {len(unique_urls)}")
            print(f"==========================================")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
