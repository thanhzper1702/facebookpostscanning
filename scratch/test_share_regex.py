import re

sample = '<div role="button" aria-label="Chia sẻ, gửi nội dung này cho bạn bè hoặc đăng lên trang cá nhân của bạn."><div class="x9f619"><span dir="auto">15</span></div></div>'
m = re.search(r'aria-label="[^"]*Chia sẻ[^"]*"[^>]*>.*?dir="auto">\s*([\d,\.]+)\s*</span>', sample, re.DOTALL)
print("Matched:", m.group(1) if m else "None")
