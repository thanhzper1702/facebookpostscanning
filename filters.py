"""
Facebook Contest Scoring & Anti-Spam Tool - Filtering & Anti-Spam Engine
=======================================================================
Implements:
1. NFC Unicode Normalization (fixes decomposed Vietnamese diacritics on Facebook).
2. Rule 1: Accurate Vietnamese Account vs. Foreign Bot / Clone Detection:
   - Blocks Non-Latin scripts & non-Vietnamese European/Turkish characters (ñ, ç, ï, î, ğ...).
   - Auto-approves names with exclusive Vietnamese diacritics (đ, ă, ơ, ư, hỏi, nặng, sắc/huyền/ngã trên â/ê/ô)
     unless mixed with foreign scripts.
   - Decomposes joined Vietnamese words in both Display Name & URL ('minngan' -> 'min'+'ngan').
   - Supports GenZ student phonetics ('Wyn Anh' -> Quỳnh Anh, 'Thanhh Haa', 'ThGia Han').
   - Never rejects a valid Vietnamese name just because the user has a shortened URL slug ('dimhu274').
3. Rule 2: Intra-category Deduplication (1 unique user = max 1 count per category).
4. Score Calculation & Real-time Manual Override Recalculator.
"""

import re
import unicodedata
import urllib.parse
from typing import Dict, List, Any, Tuple, Optional

# ---------------------------------------------------------------------------
# 1. Non-Latin Foreign Script Blockers (Regex)
# ---------------------------------------------------------------------------
FOREIGN_SCRIPT_REGEX = re.compile(
    r"["
    r"\u4e00-\u9fff"   # CJK Unified Ideographs (Chinese)
    r"\u3400-\u4dbf"   # CJK Unified Ideographs Extension A
    r"\uf900-\ufaff"   # CJK Compatibility Ideographs
    r"\u3040-\u30ff"   # Japanese Hiragana and Katakana
    r"\uac00-\ud7af"   # Korean Hangul Syllables
    r"\u1100-\u11ff"   # Korean Hangul Jamo
    r"\u0e00-\u0e7f"   # Thai
    r"\u0900-\u0d7f"   # Indian scripts (Devanagari, Bengali, Tamil, etc.)
    r"\u0600-\u06ff"   # Arabic
    r"\u0750-\u077f"   # Arabic Supplement
    r"\u08a0-\u08ff"   # Arabic Extended-A
    r"\ufb50-\ufdff"   # Arabic Presentation Forms-A
    r"\ufe70-\ufeff"   # Arabic Presentation Forms-B
    r"\u0400-\u04ff"   # Cyrillic
    r"\u0500-\u052f"   # Cyrillic Supplement
    r"\u0590-\u05ff"   # Hebrew
    r"\u1000-\u109f"   # Myanmar
    r"\u1780-\u17ff"   # Khmer
    r"]"
)

# ---------------------------------------------------------------------------
# 2. Foreign Latin Diacritics (NEVER used in Vietnamese)
# Blocks: ñ, ç, ï, î, û, ğ, ş, ë, ä, ö, ü, ÿ, ł, ø, å, æ, œ, ß, č, š, ž, ć, ń, ź, ż
# ---------------------------------------------------------------------------
NON_VIETNAMESE_LATIN_CHARS = set("ñçïîûğşëäöüÿłøåæœßčšžćńźż")

# ---------------------------------------------------------------------------
# 3. Exclusive Vietnamese Diacritics (After NFC Normalization)
# Characters that ONLY exist in Vietnamese (đ, ă, ơ, ư, and tone marks hỏi/nặng/ngã on â/ă/ê/ô/ơ/ư).
# Does NOT include simple é, è, ê, ô, ã, í, ó, ú which exist in French/Portuguese/Spanish.
# ---------------------------------------------------------------------------
EXCLUSIVE_VN_DIACRITICS_REGEX = re.compile(
    r"[ăằắặẳẵầấậẩẫđềếệểễồốộổỗơờớợởỡưừứựửữ"
    r"ảạẩậắặểệỉịỏọổộởợủụửựỷỵ]",
    re.IGNORECASE
)

ANY_VN_DIACRITICS_REGEX = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# 4. Vietnamese Phonotactics: Illegal Consonant Clusters in Vietnamese Syllables
# Real Vietnamese words NEVER contain clusters like br, bl, dr, fl, fr, gr, pl, pr, sl, st, sp, sk, rll, ldm, sh...
# ---------------------------------------------------------------------------
ILLEGAL_VN_CLUSTERS = re.compile(
    r"(?:br|bl|cl|cr|dr|fl|fr|gr|gl|pl|pr|sl|st|sp|sk|sm|sn|sw|rll|ldm|sh|ts|ps|rt|rk|lp|lt|mb|mp|nd|nt|ngt|mm|bb|dd|ff|kk|pp|tt|zz)",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# 4b. Korean / Japanese / Chinese foreign-exclusive surnames (romanized)
# IMPORTANT: Only include surnames that are NOT also common Vietnamese syllables.
# We deliberately EXCLUDE: han, nam, kim, lin, nana, song, tang, ho, cha, ji, nam
# because they are also Vietnamese. We only keep UNAMBIGUOUS foreign surnames.
# ---------------------------------------------------------------------------
# Korean surnames that DON'T overlap with Vietnamese words
KOREAN_SURNAMES_UNAMBIGUOUS = {
    "park", "choi", "jung", "kang", "yoon", "jang",
    "kwon", "hwang", "shin", "yoo", "baek", "jeon", "yeom",
    "noh", "pyo", "bae", "joo", "hyun", "lee"  # 'lee' is Americanized Korean, distinct from VN 'le'
}

# Korean surnames that require word-boundary check (longer = safer)
KOREAN_SURNAMES_LONG = {
    "minho", "jisoo", "jungkook", "taehyung", "seokjin", "namjoon", "hoseok",
    "jimin", "yoongi", "sungwoon", "jaehyun", "jungwoo", "doyoung", "taeyong",
    "haechan", "renjun", "jaemin", "yangyang", "chenle", "eunha", "sowon", "yerin",
    "yuju", "sinb", "umji", "seulgi", "irene", "wendy", "yeri", "joohyun",
    "seungwan", "sooyoung", "joohyeon", "jiyeon", "heejin", "hyunjin", "haseul",
    "vivi", "yeojin", "choerry", "gowon", "olivia", "jinsoul"
}

# Japanese surnames that are clearly Japanese (≥5 chars, unambiguous)
JAPANESE_SURNAMES_UNAMBIGUOUS = {
    "yamamoto", "tanaka", "suzuki", "watanabe", "kobayashi",
    "nakamura", "yoshida", "yamada", "sasaki", "yamaguchi", "matsumoto",
    "inoue", "kimura", "hayashi", "shimizu", "ogawa", "fujita",
    "ikeda", "hashimoto", "sakamoto", "ishikawa", "nishimura", "saito",
    "akira", "haruto", "hinata", "sakura", "yamato", "riku", "souta"
}

# Chinese pinyin surnames that are unambiguous (≥4 chars)
CHINESE_SURNAMES_UNAMBIGUOUS = {
    "zhang", "zhao", "huang", "zheng", "xiao", "cheng", "dong", "feng",
    "yuan", "shao", "qian"
}

ALL_FOREIGN_SURNAMES_UNAMBIGUOUS = (
    KOREAN_SURNAMES_UNAMBIGUOUS |
    KOREAN_SURNAMES_LONG |
    JAPANESE_SURNAMES_UNAMBIGUOUS |
    CHINESE_SURNAMES_UNAMBIGUOUS
)

# Korean-specific syllable starters that NEVER start Vietnamese syllables
KOREAN_STARTER_PATTERNS = re.compile(
    r"(?:^|[._\-])(?:ji|joo|jae|joon|je|yoo|yeon|yeong|yeo|hyu|hyun|hyung|eun|eui|oo|oe)[a-z]{1,5}(?:[._\-]|$)",
    re.IGNORECASE
)

# Syllables that exist in both Korean and Vietnamese but are suspicious
# when ALL words in a 2-word name are from this set AND no URL validation passes
KOREAN_VN_AMBIGUOUS_SYLLABLES = {
    # These syllables appear in Korean names frequently
    # but require URL confirmation when they form the entire name
    "ho", "na", "so", "ra", "ri", "ro"
}

# ---------------------------------------------------------------------------
# 5. Vietnamese Surnames, Syllables & Student Nicknames (Unaccented)
# ---------------------------------------------------------------------------
STRONG_VN_SURNAMES = {
    "nguyen", "tran", "le", "pham", "hoang", "huynh", "phan", "vu", "vo", "dang",
    "bui", "do", "ho", "ngo", "duong", "ly", "dinh", "doan", "truong", "trinh",
    "dao", "luong", "luu", "thai", "chau", "lam", "cao", "mai", "ha", "ta", "ton",
    "bach", "quach", "phung", "diep", "khuu", "thach", "nham", "nghiem", "chu", "trieu", "vuong"
}

VN_NAME_WORDS = STRONG_VN_SURNAMES | {
    # Tên đệm & Tên chính tiếng Việt
    "an", "anh", "bao", "binh", "bich", "cam", "canh", "chi", "chien", "chinh",
    "cong", "cuong", "danh", "dat", "duy", "duc", "dung", "duyen", "dan", "dieu",
    "diem", "dien", "giang", "gia", "han", "hanh", "hao", "hai", "hau", "hien", "hieu", "hiep",
    "hoa", "hoai", "hoan", "hong", "huyen", "hung", "huong", "huy", "kiet", "khanh",
    "khoa", "khoi", "khang", "khiet", "kieu", "kien", "kim", "ky", "lan", "liem", "lien",
    "linh", "loan", "loc", "long", "luan", "luat", "manh", "minh", "my", "nam",
    "nga", "ngan", "nghi", "nghia", "ngoc", "nguyet", "nha", "nhan", "nhat", "nhi",
    "nhien", "nhu", "nhung", "nu", "oanh", "phat", "phi", "phong", "phuc", "phuoc",
    "phuong", "quang", "quoc", "quan", "quyen", "quynh", "son", "sang", "sinh",
    "suong", "tam", "tan", "tai", "thach", "thanh", "thao", "thang", "thi", "thien",
    "thinh", "tho", "thoa", "thong", "thu", "thuan", "thuy", "thuyen", "tien", "thy",
    "tin", "tinh", "toan", "toai", "trang", "tri", "triet", "trong", "truc", "trung",
    "tu", "tuan", "tung", "tuyen", "tuyet", "tuong", "uyen", "van", "viet", "vinh", "vuong",
    "vy", "vi", "xuan", "yen",
    # Từ còn thiếu - tên tiếng Việt phổ biến
    "uy", "khai", "quy", "sy", "the", "kha", "khue", "khuong", "khuyen", "quyet",
    "dong", "bien", "bac", "bang", "chung", "chuong", "lanh", "lap", "loi", "luc",
    "luyen", "phu", "tao", "hop", "huan", "y",
    "tra", "tram", "truyen", "cu", "ty", "da", "gio", "du",
    "ai", "ah", "hin", "hani", "quyh",  # biệt danh & biến thể
    # Biệt danh học sinh / GenZ Việt Nam
    "bi", "em", "be", "bo", "bon", "kem", "mit", "gau", "heo", "soc",
    "bin", "su", "tit", "bap", "chip", "mun", "miu", "cun", "nhim", "na", "mi",
    "wyn", "win", "myn", "min", "ry", "ty", "cu", "ke", "ko",
    # Viết tắt phổ biến của học sinh / họ tên viết tắt
    "ng", "tr", "ph", "th", "nh", "hg", "dg", "bn", "pt", "vt", "nt",
    "vq", "vk", "vh", "nv", "nd", "tv", "tc", "lh", "ld", "lv", "pv", "tl", "tk", "qd", "hq", "ct", "st",
    # Viết tắt 2-3 ký tự đặc biệt (kiểu nick như 'Phucc Fh', 'PT Dlinh')
    "fh", "bh", "mh", "kh", "ch", "gh", "lh", "dh",
    # Viết tắt họ tên ghép (NGThi = Nguyễn Thị, NTAnh, Dlinh=Đ+Linh...)
    "ngthi", "ngth", "ntanh", "nta", "nq", "lt", "bt", "dt",
    "dlinh", "dlinh", "tlinh", "nlinh", "vlinh",  # D + Linh kiểu viết tắt
}

VIETNAMESE_NAME_WORDS = VN_NAME_WORDS

# ---------------------------------------------------------------------------
# 5b. Vietnamese Phonetic Syllable Structure (Phụ âm đầu + Vần tự động)
# Thay vì chỉ dựa vào từ điển cứng, thuật toán này tự động kiểm tra cấu trúc
# ngữ âm hợp lệ của tiếng Việt không dấu (Phụ âm đầu + Vần) để nhận diện mọi tên mới.
# ---------------------------------------------------------------------------
VN_INITIALS = {
    "b", "c", "ch", "d", "đ", "g", "gh", "gi", "h", "k", "kh", "l", "m", "n", 
    "ng", "ngh", "nh", "p", "ph", "q", "qu", "r", "s", "t", "th", "tr", "v", "x",
    # Biến thể & viết tắt học sinh
    "w", "hg", "dy"
}

# Bảng các vần (Rhymes) hợp lệ trong tiếng Việt không dấu đầy đủ và chuẩn xác
VN_VOWELS = {
    # Nguyên âm đơn
    "a", "e", "i", "o", "u", "y",
    
    # Vần bắt đầu bằng a
    "ac", "ach", "ai", "am", "an", "ang", "anh", "ao", "ap", "at", "au", "ay",
    
    # Vần bắt đầu bằng e / ê
    "ec", "ech", "em", "en", "eng", "enh", "eo", "ep", "et", "eu",
    
    # Vần bắt đầu bằng i / y
    "ia", "ich", "iem", "ien", "iep", "iet", "ieu", "im", "in", "ing", "inh", "ip", "it", "iu",
    "y", "yeu", "yen", "yet", "ym", "yn", "ynh", "yp", "yt",
    
    # Vần bắt đầu bằng o / ô / ơ
    "oa", "oac", "oach", "oai", "oam", "oan", "oang", "oanh", "oap", "oat", "oay",
    "oc", "oe", "oem", "oen", "oeo", "oet", "oi", "om", "on", "ong", "op", "ot",
    
    # Vần bắt đầu bằng u / ư
    "ua", "uac", "uai", "uam", "uan", "uang", "uanh", "uat", "uay",
    "uc", "ue", "uen", "uet", "ui", "um", "un", "ung",
    "uo", "uoc", "uoi", "uom", "uon", "uong", "uot", "up", "ut", "uu",
    
    # Vần uy
    "uy", "uya", "uyen", "uyet", "uyn", "uynh", "uyp", "uyt"
}

def is_valid_vietnamese_syllable(syllable: str) -> bool:
    """
    Thuật toán tự động kiểm tra một âm tiết bất kỳ có tuân theo cấu trúc 
    ngữ âm tiếng Việt hay không (Giúp nhận diện mọi tên mới phát sinh mà không cần hardcode).
    """
    w = syllable.lower().strip()
    if len(w) < 1 or len(w) > 7:
        return False
        
    # Trường hợp từ là nguyên âm đơn hoặc vần đứng độc lập không có phụ âm đầu (VD: 'anh', 'em', 'an', 'ao', 'yen', 'oanh', 'uyen')
    if w in VN_VOWELS:
        return True
        
    # Tách phụ âm đầu và phần vần (ưu tiên phụ âm dài hơn: ngh, ng, th, ch, qu, kh, tr, ph...)
    for init in sorted(VN_INITIALS, key=len, reverse=True):
        if w.startswith(init):
            vowel = w[len(init):]
            if not vowel:
                return False
            if vowel in VN_VOWELS:
                return True
                
    return False

# Popular English/GenZ first names often paired with a Vietnamese surname (e.g., Liam Nguyễn, Wyn Anh)
STUDENT_ENGLISH_FIRSTNAMES = {
    "liam", "ali", "kevin", "david", "john", "peter", "tom", "anna", "lisa", "mary",
    "jenny", "andy", "tony", "kenny", "eric", "alex", "ben", "max", "leo", "sam",
    "hana", "mina", "lina", "nina", "tina", "bella", "stella", "wendy", "cindy", "candy",
    "amy", "mia", "emma", "olivia", "sophia", "chloe", "ruby", "lucas", "jack", "ryan",
    "kate", "rose", "grace", "lily", "elle", "jade", "coco", "nora", "ivy", "luna"
}


def _is_foreign_url_slug(url_slug: str) -> bool:
    """
    Checks if a Facebook URL slug contains unambiguous foreign (Korean, Japanese, Chinese)
    patterns. Uses ONLY clearly foreign-exclusive surnames (not ones that overlap with Vietnamese).
    Matching is done on full word-boundary tokens in the slug.
    Returns True if slug is clearly foreign.
    """
    slug_lower = url_slug.lower()
    # Tokenize slug into meaningful parts (split by . _ - and digits)
    tokens = re.split(r'[.\-_0-9]+', slug_lower)
    tokens = [t for t in tokens if t and len(t) >= 2]

    for token in tokens:
        # Exact match on unambiguous foreign surnames (longer ones first)
        if token in ALL_FOREIGN_SURNAMES_UNAMBIGUOUS:
            return True
        # Substring match only for long foreign surnames (>=6 chars)
        for fs in ALL_FOREIGN_SURNAMES_UNAMBIGUOUS:
            if len(fs) >= 6 and fs in token:
                return True

    # Korean-specific multi-char patterns in slug tokens
    full_slug_no_sep = slug_lower.replace(".", "").replace("_", "").replace("-", "")
    if KOREAN_STARTER_PATTERNS.search(url_slug.lower()):
        return True

    return False

# ---------------------------------------------------------------------------
# 5. Profile URL Cleaning & Canonicalization
# ---------------------------------------------------------------------------
NON_USER_SLUGS = {
    "posts", "watch", "groups", "events", "photo.php", "photos",
    "hashtag", "browse", "messages", "share", "sharer.php", "login",
    "recover", "help", "settings", "policies", "privacy", "pages",
    "reel", "stories", "permalink.php", "story.php", "live", "about",
    "ad_center", "photo", "l.php", "sharer"
}


def clean_profile_url(raw_url: str) -> str:
    """Cleans Facebook profile URLs and returns a canonical URL."""
    if not raw_url:
        return ""

    raw_url = raw_url.strip()

    if raw_url.startswith("/"):
        raw_url = f"https://www.facebook.com{raw_url}"
    elif not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = f"https://www.facebook.com/{raw_url}"

    raw_url = re.sub(
        r"^https?://(m|touch|web|mbasic)\.facebook\.com",
        "https://www.facebook.com",
        raw_url,
        flags=re.IGNORECASE
    )
    raw_url = re.sub(r"^http://", "https://", raw_url, flags=re.IGNORECASE)

    try:
        parsed = urllib.parse.urlparse(raw_url)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        if "profile.php" in path:
            user_id = query.get("id", [""])[0]
            if user_id:
                return f"https://www.facebook.com/profile.php?id={user_id}"
            return "https://www.facebook.com/profile.php"

        if "/people/" in path:
            clean_path = re.sub(r"/+$", "", path)
            return f"https://www.facebook.com{clean_path}"

        slug = path.lstrip("/")
        slug_parts = slug.split("/")
        first_part = slug_parts[0] if slug_parts else ""

        if not first_part or first_part.lower() in NON_USER_SLUGS:
            return ""

        return f"https://www.facebook.com/{first_part}"
    except Exception:
        return raw_url.split("?")[0].rstrip("/")


# ---------------------------------------------------------------------------
# 6. Helper Functions for Linguistic & URL Analysis
# ---------------------------------------------------------------------------
def _strip_accents(text: str) -> str:
    """Removes Vietnamese/Latin accents and converts đ -> d."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _reduce_repeated_chars(word: str) -> str:
    """
    Normalizes GenZ repeated letters:
    - 'thanhh' -> 'thanh', 'haa' -> 'ha', 'quocss' -> 'quoc', 'binn' -> 'bin'
    - 'kienn' -> 'kien' (double final consonant)
    - 'nhuw' -> 'nhu' (GenZ uses 'w' as suffix for words ending in 'u')
    - 'quyhh' is handled by split_double_consonant later
    """
    w = word.lower().strip()

    # GenZ dung 'w' o cuoi thay cho 'u' (nhuw -> nhu, buw -> bu, thuw -> thu)
    if w.endswith('w') and len(w) > 2:
        base = w[:-1]
        if base in VIETNAMESE_NAME_WORDS:
            return base
        # Also try with the 'w' -> '' reduction: vow -> vo, tuw -> tu
        if base.endswith('u') and base in VIETNAMESE_NAME_WORDS:
            return base

    reduced = re.sub(r"([a-z])\1+", r"\1", w)

    # Extra: if word ends in doubled consonant like 'kienn' -> 'kien'
    # _reduce handles 'nn' -> 'n', but 'kienn' -> 'kien' which may or may not be in dict
    # Already handled by re.sub above: kienn -> kien

    if len(reduced) > 3 and reduced.endswith(("s", "z")) and reduced[:-1] in VIETNAMESE_NAME_WORDS:
        reduced = reduced[:-1]
    return reduced


def _try_split_double_consonant(word: str):
    """
    Try to split a word with a double consonant at syllable boundary into 2 VN syllables.
    E.g. 'minngan' -> ('min', 'ngan'), 'thanhhan' -> ('thanh', 'han')
    Returns a list of split parts if both parts are in VN dict, else empty list.
    """
    w = word.lower()
    # Find doubled consonants (nn, tt, cc, hh, etc.) and try splitting there
    for i in range(2, len(w) - 1):
        if w[i] == w[i-1] and w[i].isalpha():  # doubled char
            part1 = w[:i]        # e.g. 'min'
            part2 = w[i:]        # e.g. 'ngan'
            r1 = re.sub(r"([a-z])\1+", r"\1", part1)
            r2 = re.sub(r"([a-z])\1+", r"\1", part2)
            if (r1 in VIETNAMESE_NAME_WORDS or is_valid_vietnamese_syllable(r1)) and (r2 in VIETNAMESE_NAME_WORDS or is_valid_vietnamese_syllable(r2)):
                return [r1, r2]
    return []


def _split_camel_case(text: str) -> str:
    """Splits joined CamelCase tokens AFTER stripping accents or on NFC text."""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", text)


# ---------------------------------------------------------------------------
# 7. Rule 1: Multi-Layer Vietnamese Account Verification
# ---------------------------------------------------------------------------
def verify_vietnamese_account(
    user_name: str,
    profile_url: str = "",
    has_social_proof: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Bộ lọc Đa Tầng 5 Lớp Xác Thực Tài Khoản Việt Nam vs Bot/Clone Ngoại Quốc:
    - Lớp 1: Chặn ký tự phi Latin (Hàn, Trung, Thái, Ả Rập, Nga, Ấn Độ...) & Latin ngoại quốc (ñ, ç, ï, î, ğ...).
    - Lớp 2: Duyệt ngay lập tức nếu tên có dấu tiếng Việt đặc trưng chuẩn (đ, ă, ơ, ư, hỏi, nặng, ngã...).
    - Lớp 3: Bóc tách ngữ âm tiếng Việt & chặn các cụm phụ âm ngoại lai không thể có trong tiếng Việt (br, dr, cl, fl, rll, ldm, sh...).
    - Lớp 4: Kiểm tra tính hợp lệ của từng từ theo từ điển Họ, Tên, Biệt danh học sinh & Tên tiếng Anh chuẩn ghép Họ Việt.
    - Lớp 5: Phát hiện và loại trừ tài khoản clone tạo hàng loạt (ID 615...).
    """
    if not user_name or not user_name.strip():
        return False, "Thiếu tên tài khoản"

    # Chuẩn hóa Unicode NFC để các dấu tiếng Việt không bị phân rã
    name = unicodedata.normalize("NFC", user_name.strip())
    lower_name = name.lower()

    # LỚP 1: Chặn đứng ký tự tượng hình ngoại quốc (Hàn, Trung, Nhật, Thái, Ả Rập, Nga, Ấn Độ...)
    if FOREIGN_SCRIPT_REGEX.search(name):
        return False, "Foreign/Bot Account (Ký tự phi Latin)"

    # Chặn ký tự Latin châu Âu / Thổ Nhĩ Kỳ / Ả Rập (ñ, ç, ï, î, ğ, ä, ö, ü...)
    if any(ch in NON_VIETNAMESE_LATIN_CHARS for ch in lower_name):
        return False, "Foreign/Bot Account (Ký tự Latin ngoại quốc: ñ/ç/ï/î/ğ)"

    # LỚP 2: Có dấu tiếng Việt đặc trưng chuẩn (đ, ă, ơ, ư, dấu hỏi/ngã/nặng) -> 100% người Việt
    if EXCLUSIVE_VN_DIACRITICS_REGEX.search(name):
        return True, "Hợp lệ (Tên tiếng Việt có dấu chuẩn)"

    # Nhận diện đầu số ID Clone mới tạo hàng loạt gần đây (6155... đến 6159...)
    is_new_clone_id = False
    if profile_url and "profile.php?id=" in profile_url:
        if re.search(r"id=615[5-9]\d+", profile_url):
            is_new_clone_id = True

    # LỚP 3: Chuẩn hóa tên không dấu (Tách CamelCase + Tokenize các từ)
    unaccented_raw = _strip_accents(name)
    spaced_name = _split_camel_case(unaccented_raw)
    raw_words = re.findall(r"[a-zA-Z]+", spaced_name.lower())

    if not raw_words:
        return False, "Tên không hợp lệ (Chỉ có ký tự đặc biệt/số)"

    # Kiểm tra ngữ âm: Chặn đứng các cụm phụ âm không bao giờ tồn tại trong tiếng Việt
    # Ngoại lệ: Một số viết tắt họ tên Việt Nam (ngthi, ngth, ntanh, dlinh...) có cụm phụ âm nhưng hợp lệ
    VN_ABBREVIATION_EXCEPTIONS = {
        "ngthi", "ngth", "ntanh", "nta", "nq", "nt", "lt", "bt", "dt",
        "mnhh", "dnh", "tnh", "qnh", "bnh",
        # Họ + Tên viết tắt (D + Linh, T + Linh, N + Linh...)
        "dlinh", "tlinh", "nlinh", "vlinh", "hlinh", "klinh",
        # PT, DG, BN, VQ kiểu viết tắt 2 chữ
        "pt", "dg", "bn", "vt", "ht", "mt", "kt", "lt",
        "vq", "vk", "vh", "nv", "nd", "tv", "tc", "lh", "ld", "lv", "pv", "tl", "tk", "qd", "hq", "ct", "st",
    }
    for w in raw_words:
        if w.lower() in VN_ABBREVIATION_EXCEPTIONS:
            continue  # Viết tắt họ tên Việt Nam hợp lệ
        if ILLEGAL_VN_CLUSTERS.search(w):
            if w.lower() not in STUDENT_ENGLISH_FIRSTNAMES:
                return False, f"Foreign/Bot Name (Cụm phụ âm không tồn tại trong tiếng Việt: {w})"

    # LỚP 4: Đối soát từng từ với Từ điển Họ, Tên, Biệt danh Việt Nam & Tên tiếng Anh học sinh
    vn_matched: List[str] = []
    english_first: List[str] = []
    unrecognized: List[str] = []

    for w in raw_words:
        rw = _reduce_repeated_chars(w)
        if rw in VN_NAME_WORDS or is_valid_vietnamese_syllable(rw):
            vn_matched.append(rw)
        elif rw in STUDENT_ENGLISH_FIRSTNAMES:
            english_first.append(rw)
        elif len(rw) == 1 and rw.isalpha():
            # Chữ cái viết tắt (Initials như 'N.' trong 'Huỳnh N.Linh', 'T.' trong 'Trần T. Mai')
            vn_matched.append(rw)
        else:
            # Thử tách từ bị ghép đôi phụ âm ranh giới âm tiết (VD: 'minngan' → 'min'+'ngan')
            split_parts = _try_split_double_consonant(w)
            if split_parts:
                vn_matched.extend(split_parts)
            else:
                unrecognized.append(w)

    has_strong_surname = any(w in STRONG_VN_SURNAMES for w in vn_matched)

    # Nếu có bất kỳ từ nào không nhận diện được (ngoại quốc) -> Loại bỏ
    if unrecognized:
        return False, f"Foreign/Bot Name (Từ ngoại quốc/không có trong tiếng Việt: {unrecognized[0]})"

    # Nếu có tên tiếng Anh (VD: Ali, Kevin, Jenny), BẮT BUỘC phải đi kèm Họ Việt Nam chính thống
    if english_first:
        if has_strong_surname:
            return True, "Hợp lệ (Tên tiếng Anh + Họ Việt Nam)"
        return False, "Foreign Name (Tên tiếng Anh không đi kèm Họ Việt Nam)"

    # LỚP 4b: Kiểm tra URL slug để phát hiện tài khoản Hàn/Nhật/Trung dùng âm tiết giống tiếng Việt
    url_slug = ""
    if profile_url:
        url_slug = profile_url.rstrip("/").split("/")[-1].lower()
        # Loại nếu URL slug chứa họ nước ngoài rõ ràng
        if _is_foreign_url_slug(url_slug):
            return False, f"Foreign Account (URL slug chứa họ/tên Hàn/Nhật/Trung: {url_slug[:30]})"

    # LỚP 4c: Phát hiện tên Hàn/Nhật 2 âm tiết dùng âm tiết chung với tiếng Việt
    # Ví dụ: 'Min Ho', 'Ha Na', 'An Na', 'Mi Na', 'Na Na' (tất cả đều là tên Hàn phổ biến)
    # Quy tắc: Nếu tất cả từ trong tên đều là âm tiết ngắn (≤ 3 chữ cái) và không có họ Việt mạnh
    # thì bắt buộc phải xác thực qua URL
    if not has_strong_surname and len(vn_matched) >= 2:
        all_short = all(len(w) <= 3 for w in vn_matched)
        if all_short:
            # Tất cả âm tiết đều ngắn (≤3 chữ) và không có họ Việt mạnh
            # Kiểm tra URL để xác thực
            if profile_url and url_slug:
                # URL chứa họ Việt Nam (whole-word match để không nhầm 'le' với 'lee') -> duyệt
                slug_for_check = "." + url_slug.replace(".", ".").replace("_", ".").replace("-", ".")
                if any("." + s in slug_for_check or slug_for_check.startswith(s + ".") or url_slug.startswith(s) for s in STRONG_VN_SURNAMES if len(s) >= 3):
                    return True, "Hợp lệ (Tên tiếng Việt chuẩn, xác thực qua URL họ Việt)"
                # URL chứa tên VN dài (>=4 chữ) -> duyệt
                if any(v in url_slug for v in VN_NAME_WORDS if len(v) >= 4):
                    return True, "Hợp lệ (Tên tiếng Việt chuẩn, xác thực qua URL tên VN)"
                # URL chứa số -> nhiều khả năng là người thật, duyệt
                if re.search(r'\d{2,}', url_slug):
                    return True, "Hợp lệ (Tên tiếng Việt chuẩn, URL có số ID)"
                # URL chứa profile.php -> ID số, tin cậy hơn
                if 'profile.php' in profile_url:
                    return True, "Hợp lệ (Tên tiếng Việt chuẩn, profile ID số)"
                # Kiểm tra các âm tiết có phải là âm tiết Hàn/Nhật đặc trưng không
                has_korean_syllable = any(w in KOREAN_VN_AMBIGUOUS_SYLLABLES for w in vn_matched)
                if has_korean_syllable:
                    return False, f"Nghi vấn tài khoản Hàn/Nhật (Âm tiết ngắn + không xác thực được URL)"
            elif not profile_url:
                # Không có URL -> không đủ bằng chứng để duyệt tên 2 âm tiết ngắn
                has_korean_syllable = any(w in KOREAN_VN_AMBIGUOUS_SYLLABLES for w in vn_matched)
                if has_korean_syllable:
                    return False, f"Nghi vấn tài khoản Hàn/Nhật (Âm tiết ngắn, thiếu URL xác thực)"

    # LỚP 5: Kiểm soát tài khoản mang ID Clone (615...) không có dấu tiếng Việt
    if is_new_clone_id and not has_social_proof:
        short_nicknames = {"bi", "em", "be", "bo", "bon", "bin", "su", "mi", "na"}
        if all(w in short_nicknames for w in vn_matched):
            return False, "Nghi vấn Acc Clone mới lập (ID 615... + Nickname ảo ngắn)"
        if not has_strong_surname and len(vn_matched) < 2:
            return False, "Nghi vấn Acc Clone mới lập (ID 615... không có Họ Việt Nam)"

    # Tài khoản tên tiếng Việt bình thường có từ 2 từ trở lên (VD: Minh Cam, Phi Phong, Gia Bin Mai...)
    # Phải có ít nhất 1 từ đầy đủ (>= 2 ký tự) để không chấp nhận tên chỉ toàn 1 chữ cái viết tắt (VD: 'A B')
    full_words = [w for w in vn_matched if len(w) >= 2]
    if len(vn_matched) >= 2 and len(full_words) >= 1:
        return True, "Hợp lệ (Tên tiếng Việt chuẩn)"

    # Tên chỉ có 1 từ: Chỉ duyệt nếu URL cá nhân chứa tên tiếng Việt rõ ràng
    if len(vn_matched) == 1 and profile_url:
        if any(s in url_slug for s in STRONG_VN_SURNAMES) or any(v in url_slug for v in VN_NAME_WORDS if len(v) >= 4):
            return True, "Hợp lệ (Xác thực qua URL profile)"

    return False, "Foreign/Bot Name (Không khớp cấu trúc tên tiếng Việt)"


# ---------------------------------------------------------------------------
# 8. Rule 2: Intra-Category Deduplication & Processing Engine
# ---------------------------------------------------------------------------
def process_category_interactions(
    raw_interactions: List[Dict[str, Any]],
    category_name: str,
    is_comment: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Takes a list of raw extracted interactions for a category (Reactions, Comments, Shares).
    - For Reactions: Applies Rule 1 (Multi-Layer Name + URL Filter) and Rule 2 (Deduplication).
    - For Comments: Only filters by spam/duplicates (no name filtering), 1 unique user = 1 valid comment.
    """
    total_extracted = sum(int(it.get("interaction_count", 1)) for it in raw_interactions)

    if is_comment is None:
        cat_lower = category_name.lower()
        is_comment = "comment" in cat_lower or "bình luận" in cat_lower

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []

    for item in raw_interactions:
        raw_url = item.get("profile_url", "")
        clean_url = clean_profile_url(raw_url) or f"unknown_{len(order)}"
        item["clean_profile_url"] = clean_url

        if clean_url not in grouped:
            grouped[clean_url] = []
            order.append(clean_url)
        grouped[clean_url].append(item)

    valid_accounts: List[Dict[str, Any]] = []
    invalid_accounts: List[Dict[str, Any]] = []
    raw_audit_log: List[Dict[str, Any]] = []

    valid_count = 0
    invalid_count = 0
    audit_index = 1

    for clean_url in order:
        user_interactions = grouped[clean_url]
        rep_name = user_interactions[0].get("account_name", "").strip() or "Facebook User"
        rep_raw_url = user_interactions[0].get("profile_url", clean_url)
        interaction_count = sum(int(it.get("interaction_count", 1)) for it in user_interactions)

        first_item = user_interactions[0]
        has_social_proof = bool(first_item.get("has_social_proof", False))

        if is_comment:
            # Bình luận: Không lọc theo tên, chỉ lọc spam / trùng lặp
            is_name_valid = True
            bot_reason = None
            valid_reason = "Bình luận hợp lệ"
        else:
            # Cảm xúc (Reactions): Áp dụng bộ lọc tài khoản Việt Nam & loại bỏ bot nước ngoài
            is_name_valid, bot_reason = verify_vietnamese_account(
                rep_name,
                profile_url=clean_url,
                has_social_proof=has_social_proof
            )
            valid_reason = "Tài khoản Việt Nam hợp lệ"

        if is_name_valid:
            valid_count += 1
            valid_accounts.append({
                "account_name": rep_name,
                "profile_url": rep_raw_url,
                "clean_profile_url": clean_url,
                "interaction_count": interaction_count,
                "is_valid": True,
                "reason": valid_reason
            })

            raw_audit_log.append({
                "index": audit_index,
                "account_name": rep_name,
                "profile_url": rep_raw_url,
                "interaction_type": first_item.get("interaction_type", category_name),
                "is_valid": True,
                "reason": valid_reason,
                "timestamp": first_item.get("timestamp", ""),
                "content": first_item.get("content", "")
            })
            audit_index += 1

            # Xử lý tương tác trùng lặp (Duplicate spam)
            if interaction_count > 1:
                dup_count = interaction_count - 1
                invalid_count += dup_count
                dup_reason = (
                    f"Spam bình luận lặp lại (Bình luận {interaction_count} lần)"
                    if is_comment
                    else f"Duplicate Spam ({interaction_count} lần tương tác)"
                )
                
                if len(user_interactions) > 1:
                    for dup_item in user_interactions[1:]:
                        raw_audit_log.append({
                            "index": audit_index,
                            "account_name": rep_name,
                            "profile_url": rep_raw_url,
                            "interaction_type": dup_item.get("interaction_type", category_name),
                            "is_valid": False,
                            "reason": dup_reason,
                            "timestamp": dup_item.get("timestamp", ""),
                            "content": dup_item.get("content", "")
                        })
                        audit_index += 1
                else:
                    for _ in range(dup_count):
                        raw_audit_log.append({
                            "index": audit_index,
                            "account_name": rep_name,
                            "profile_url": rep_raw_url,
                            "interaction_type": first_item.get("interaction_type", category_name),
                            "is_valid": False,
                            "reason": dup_reason,
                            "timestamp": first_item.get("timestamp", ""),
                            "content": first_item.get("content", "")
                        })
                        audit_index += 1

                invalid_accounts.append({
                    "account_name": rep_name,
                    "profile_url": rep_raw_url,
                    "clean_profile_url": clean_url,
                    "interaction_count": interaction_count,
                    "is_valid": False,
                    "reason": dup_reason
                })
        else:
            invalid_count += interaction_count
            invalid_accounts.append({
                "account_name": rep_name,
                "profile_url": rep_raw_url,
                "clean_profile_url": clean_url,
                "interaction_count": interaction_count,
                "is_valid": False,
                "reason": bot_reason or "Foreign/Bot Account"
            })

            if len(user_interactions) > 1:
                for item in user_interactions:
                    raw_audit_log.append({
                        "index": audit_index,
                        "account_name": rep_name,
                        "profile_url": rep_raw_url,
                        "interaction_type": item.get("interaction_type", category_name),
                        "is_valid": False,
                        "reason": bot_reason or "Foreign/Bot Account",
                        "timestamp": item.get("timestamp", ""),
                        "content": item.get("content", "")
                    })
                    audit_index += 1
            else:
                for _ in range(interaction_count):
                    raw_audit_log.append({
                        "index": audit_index,
                        "account_name": rep_name,
                        "profile_url": rep_raw_url,
                        "interaction_type": first_item.get("interaction_type", category_name),
                        "is_valid": False,
                        "reason": bot_reason or "Foreign/Bot Account",
                        "timestamp": first_item.get("timestamp", ""),
                        "content": first_item.get("content", "")
                    })
                    audit_index += 1

    return {
        "category": category_name,
        "total_extracted": total_extracted,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "valid_accounts": valid_accounts,
        "invalid_accounts": invalid_accounts,
        "raw_audit_log": raw_audit_log
    }


# ---------------------------------------------------------------------------
# 9. Overall Interaction Statistics Calculation (Thống kê tương tác)
# ---------------------------------------------------------------------------
def calculate_contest_score(
    valid_reactions: int,
    valid_comments: int,
    valid_shares: int = 0
) -> Dict[str, Any]:
    """
    Calculates overall interaction statistics:
    Total Valid Interactions = Valid Reactions + Valid Comments + Valid Shares
    """
    total_valid = valid_reactions + valid_comments + valid_shares

    return {
        "valid_reactions": valid_reactions,
        "valid_comments": valid_comments,
        "valid_shares": valid_shares,
        "total_valid_interactions": total_valid,
        "final_total_score": total_valid,  # Tương thích ngược: tổng số tương tác hợp lệ
        "reaction_points": valid_reactions,
        "comment_points": valid_comments,
        "reaction_multiplier": 1,
        "comment_multiplier": 1,
        "share_multiplier": 0,
        "share_points": 0
    }

calculate_interaction_stats = calculate_contest_score