# -*- coding: utf-8 -*-
import filters
from filters import verify_vietnamese_account, clean_profile_url, process_category_interactions, calculate_contest_score

test_cases = [
    ('王伟 (Wang Wei)', False),
    ('สมชาย วงศ์สวัสดิ์', False),
    ('محمد عبد الله', False),
    ('राहुल शर्मा (Rahul Sharma)', False),
    ('Иван Петров', False),
    ('Nguyễn Hoàng Nam', True),
    ('Trần Thị Mai Phương', True),
    ('Bùi Khánh Vy', True),
    ('Đỗ Thành Đạt', True),
    ('Luong Gia Huy', True),
    ('Nguyen Van Binh', True),
    ('Hoang Yen Nhi', True),
    ('Rahul Sharma', False),
    ('Priya Patel', False),
    ('John Smith', False),
    ('Mohammed Ali', False)
]

all_passed = True
for name, expected in test_cases:
    valid, reason = verify_vietnamese_account(name)
    ok = (valid == expected)
    if not ok:
        all_passed = False
        print(f"FAIL: {repr(name)} => valid={valid}, expected={expected}, reason={reason}")
    else:
        print(f"PASS: {repr(name)} => valid={valid} (reason: {reason})")

print(f"\nLinguistic Name Tests Passed: {all_passed}")
assert all_passed

# Test URL cleaner
url1 = clean_profile_url("https://www.facebook.com/nam.nguyen?__cft__[0]=AZX&__tn__=-R")
assert url1 == "https://www.facebook.com/nam.nguyen", f"URL mismatch: {url1}"

url2 = clean_profile_url("https://m.facebook.com/profile.php?id=10001001&comment_id=123")
assert url2 == "https://www.facebook.com/profile.php?id=10001001", f"URL mismatch: {url2}"
print("URL Cleaner tests: Passed")

# Test deduplication
mock_raw_comments = [
    {"account_name": "Nguyễn Hoàng Nam", "profile_url": "https://facebook.com/nam.nguyen?cmt=1", "interaction_type": "Comment"},
    {"account_name": "Nguyễn Hoàng Nam", "profile_url": "https://facebook.com/nam.nguyen?cmt=2", "interaction_type": "Comment"},
    {"account_name": "Nguyễn Hoàng Nam", "profile_url": "https://facebook.com/nam.nguyen?cmt=3", "interaction_type": "Comment"},
    {"account_name": "Rahul Sharma", "profile_url": "https://facebook.com/rahul?cmt=1", "interaction_type": "Comment"},
    {"account_name": "Rahul Sharma", "profile_url": "https://facebook.com/rahul?cmt=2", "interaction_type": "Comment"},
]
res = process_category_interactions(mock_raw_comments, "Comment")
assert res["valid_count"] == 1, f"Expected 1 valid, got {res['valid_count']}"
assert res["invalid_count"] == 4, f"Expected 4 invalid, got {res['invalid_count']}"
print("Deduplication test: Passed (1 valid user with 3 comments -> 1 valid + 2 dup invalid; 1 bot with 2 comments -> 2 bot invalid)")

# Test score calculation
score = calculate_contest_score(valid_reactions=10, valid_comments=5, valid_shares=2)
# 10*1 + 5*2 + 2*3 = 10 + 10 + 6 = 26
assert score["final_total_score"] == 26
print("Score calculation test: Passed (10*1 + 5*2 + 2*3 = 26 pts)")
print("\nALL ANTI-SPAM & SCORING TESTS PASSED PERFECTLY!")
