import base64
import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

BRAND_NAME = "蝴蝶影视"
BRAND_ACTOR = "🦋 TG群: @tvshare23"
BRAND_DIRECTOR = "🦋 蝴蝶影视"
TG_GROUP = "https://t.me/tvshare23"
SYNOPSIS_GROUP = "🦋 蝴蝶影视官方交流群：@tvshare23"
DIVIDER_THIN = "────────────────────"
DIVIDER_THICK = "━━━━━━━━━━━━━━"
MARKER = "〔影片简介〕"
LINE_NAME = "🦋 蝴蝶专线"
NODE_LINE = "当前节点：https://supjav.blog"

DEFAULT_SITE = "https://supjav.blog"
BACKUP_SITE = "https://supjav.com"
DEFAULT_EMBED_API = "https://lk1.supremejav.com/supjav.php"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TICKET_TTL = 1200
HLS_MIME = "application/vnd.apple.mpegurl"
BLOCK_MSG = "站点触发 Cloudflare 验证，请在源设置 extend 中填入该站点的浏览器 Cookie（cf_clearance）与签发 UA，或切换站点域名"
FALLBACK_MSG = "com 被 Cloudflare 拦截，当前显示 blog 镜像内容；票据生效后将自动切回 com 主站"
DEFAULT_MODE = "mix"

ROUTES = [
    ("latest", "最新发布", ""),
    ("category/chinese-subtitles", "中文字幕", "chinese"),
    ("category/censored-jav", "有码 JAV", "censored"),
    ("category/uncensored-jav", "无码 JAV", "uncensored"),
    ("category/reducing-mosaic", "流出无码", "uncensored-leaked"),
    ("category/amateur", "素人精选", "amateur"),
    ("genre/1080p", "1080P", "category/1080p"),
    ("genre/4k", "4K", "category/4k"),
    ("genre/60fps", "60FPS", "category/60fps"),
    ("genre/69", "69", "category/69"),
    ("genre/actress-dildo", "Actress Dildo", "category/actress-dildo"),
    ("genre/affair", "Affair", "category/affair"),
    ("genre/anus", "Anus", "category/anus"),
    ("genre/artist", "Artist", "category/artist"),
    ("genre/beautiful-breasts", "Beautiful Breasts", "category/beautiful-breasts"),
    ("genre/beautiful-butt", "Beautiful Butt", "category/beautiful-butt"),
    ("genre/beautiful-butt-beautiful-ass", "Beautiful Butt Beautiful Ass", "category/beautiful-butt-beautiful-ass"),
    ("genre/beautiful-buttocks", "Beautiful Buttocks", "category/beautiful-buttocks"),
    ("genre/beautiful-buttocks-beautiful-ass", "Beautiful Buttocks Beautiful Ass", "category/beautiful-buttocks-beautiful-ass"),
    ("genre/beautiful-girl", "Beautiful Girl", "category/beautiful-girl"),
    ("genre/beautiful-legs", "Beautiful Legs", "category/beautiful-legs"),
    ("genre/beautiful-legs-beautiful-feet", "Beautiful Legs Beautiful Feet", "category/beautiful-legs-beautiful-feet"),
    ("genre/beautiful-skin", "Beautiful Skin", "category/beautiful-skin"),
    ("genre/big-ass", "Big Ass", "category/big-ass"),
    ("genre/big-boobs", "Big Boobs", "category/big-boobs"),
    ("genre/big-breasts", "Big Breasts", "category/big-breasts"),
    ("genre/big-tits", "Big Tits", "category/big-tits"),
    ("genre/bikyaku", "Bikyaku", "category/bikyaku"),
    ("genre/black-hair", "Black Hair", "category/black-hair"),
    ("genre/black-silk", "Black Silk", "category/black-silk"),
    ("genre/black-stockings", "Black Stockings", "category/black-stockings"),
    ("genre/blowjob", "Blowjob", "category/blowjob"),
    ("genre/bondage", "Bondage", "category/bondage"),
    ("genre/breasts", "Breasts", "category/breasts"),
    ("genre/bukkake", "Bukkake", "category/bukkake"),
    ("genre/business-clothing", "Business Clothing", "category/business-clothing"),
    ("genre/butt", "Butt", "category/butt"),
    ("genre/catwoman", "Catwoman", "category/catwoman"),
    ("genre/chinese-av", "Chinese Av", "category/chinese-av"),
    ("genre/classic", "Classic", "category/classic"),
    ("genre/cohabitation", "Cohabitation", "category/cohabitation"),
    ("genre/cosplay", "Cosplay", "category/cosplay"),
    ("genre/cowgirl", "Cowgirl", "category/cowgirl"),
    ("genre/creampie", "Creampie", "category/creampie"),
    ("genre/creampie-bareback", "Creampie Bareback", "category/creampie-bareback"),
    ("genre/creampie-no-condom", "Creampie No Condom", "category/creampie-no-condom"),
    ("genre/cuckold", "Cuckold", "category/cuckold"),
    ("genre/cum", "Cum", "category/cum"),
    ("genre/cum-in-mouth", "Cum In Mouth", "category/cum-in-mouth"),
    ("genre/cum-on-face", "Cum On Face", "category/cum-on-face"),
    ("genre/cunnilingus", "Cunnilingus", "category/cunnilingus"),
    ("genre/cunnilingus-pussy-licking", "Cunnilingus Pussy Licking", "category/cunnilingus-pussy-licking"),
    ("genre/cute", "Cute", "category/cute"),
    ("genre/dirty-talk", "Dirty Talk", "category/dirty-talk"),
    ("genre/dom", "Dom", "category/dom"),
    ("genre/eating", "Eating", "category/eating"),
    ("genre/eimi-fukada", "Eimi Fukada", "category/eimi-fukada"),
    ("genre/electric-massager", "Electric Massager", "category/electric-massager"),
    ("genre/exclusive", "Exclusive", "category/exclusive"),
    ("genre/extreme-orgasm", "Extreme Orgasm", "category/extreme-orgasm"),
    ("genre/face-reveal", "Face Reveal", "category/face-reveal"),
    ("genre/face-ride", "Face Ride", "category/face-ride"),
    ("genre/fair-skin", "Fair Skin", "category/fair-skin"),
    ("genre/fat-girl", "Fat Girl", "category/fat-girl"),
    ("genre/fc2ppv", "FC2 PPV", "category/fc2ppv"),
    ("genre/female-boss", "Female Boss", "category/female-boss"),
    ("genre/female-college-student", "Female College Student", "category/female-college-student"),
    ("genre/female-investigator", "Female Investigator", "category/female-investigator"),
    ("genre/footjob", "Footjob", "category/footjob"),
    ("genre/forced-blowjob", "Forced Blowjob", "category/forced-blowjob"),
    ("genre/giant-breasts", "Giant Breasts", "category/giant-breasts"),
    ("genre/hairless", "Hairless", "category/hairless"),
    ("genre/hairless-white-tiger", "Hairless White Tiger", "category/hairless-white-tiger"),
    ("genre/handjob", "Handjob", "category/handjob"),
    ("genre/hd", "Hd", "category/hd"),
    ("genre/high-school-girl", "High School Girl", "category/high-school-girl"),
    ("genre/hikari-azusa", "Hikari Azusa", "category/hikari-azusa"),
    ("genre/hot-girl", "Hot Girl", "category/hot-girl"),
    ("genre/huge-breasts", "Huge Breasts", "category/huge-breasts"),
    ("genre/huge-butt", "Huge Butt", "category/huge-butt"),
    ("genre/idol-class", "Idol Class", "category/idol-class"),
    ("genre/individual", "Individual", "category/individual"),
    ("genre/individual-photography", "Individual Photography", "category/individual-photography"),
    ("genre/internal-ejaculation", "Internal Ejaculation", "category/internal-ejaculation"),
    ("genre/iramachio", "Iramachio", "category/iramachio"),
    ("genre/kaoru-yasui", "Kaoru Yasui", "category/kaoru-yasui"),
    ("genre/kiss", "Kiss", "category/kiss"),
    ("genre/lesbian", "Lesbian", "category/lesbian"),
    ("genre/married-woman", "Married Woman", "category/married-woman"),
    ("genre/masochist", "Masochist", "category/masochist"),
    ("genre/mina-kitano", "Mina Kitano", "category/mina-kitano"),
    ("genre/missionary-position", "Missionary Position", "category/missionary-position"),
    ("genre/nana-yagi", "Nana Yagi", "category/nana-yagi"),
    ("genre/nao-jinguji", "Nao Jinguji", "category/nao-jinguji"),
    ("genre/neat", "Neat", "category/neat"),
    ("genre/nene-tanaka", "Nene Tanaka", "category/nene-tanaka"),
    ("genre/no-cut", "No Cut", "category/no-cut"),
    ("genre/nozomi-ishihara", "Nozomi Ishihara", "category/nozomi-ishihara"),
    ("genre/ntr", "Ntr", "category/ntr"),
    ("genre/office-lady", "Office Lady", "category/office-lady"),
    ("genre/ol", "Ol", "category/ol"),
    ("genre/older-sister", "Older Sister", "category/older-sister"),
    ("genre/open-eyes", "Open Eyes", "category/open-eyes"),
    ("genre/oral-sex", "Oral Sex", "category/oral-sex"),
    ("genre/orgy", "Orgy", "category/orgy"),
    ("genre/original", "Original", "category/original"),
    ("genre/original-video", "Original Video", "category/original-video"),
    ("genre/other-fetish", "Other Fetish", "category/other-fetish"),
    ("genre/paipan", "Paipan", "category/paipan"),
    ("genre/pantyhose", "Pantyhose", "category/pantyhose"),
    ("genre/personal-photo", "Personal Photo", "category/personal-photo"),
    ("genre/pervert", "Pervert", "category/pervert"),
    ("genre/petite-breasts", "Petite Breasts", "category/petite-breasts"),
    ("genre/planning", "Planning", "category/planning"),
    ("genre/pornstar", "Pornstar", "category/pornstar"),
    ("genre/prank", "Prank", "category/prank"),
    ("genre/pretty-girl", "Pretty Girl", "category/pretty-girl"),
    ("genre/private-teacher", "Private Teacher", "category/private-teacher"),
    ("genre/promiscuity", "Promiscuity", "category/promiscuity"),
    ("genre/promiscuous", "Promiscuous", "category/promiscuous"),
    ("genre/pussy-licking", "Pussy Licking", "category/pussy-licking"),
    ("genre/raw", "Raw", "category/raw"),
    ("genre/raw-hame", "Raw Hame", "category/raw-hame"),
    ("genre/restraint", "Restraint", "category/restraint"),
    ("genre/ride", "Ride", "category/ride"),
    ("genre/second-round", "Second Round", "category/second-round"),
    ("genre/seeded", "Seeded", "category/seeded"),
    ("genre/selfie", "Selfie", "category/selfie"),
    ("genre/sexy", "Sexy", "category/sexy"),
    ("genre/shame", "Shame", "category/shame"),
    ("genre/shaving", "Shaving", "category/shaving"),
    ("genre/short-hair", "Short Hair", "category/short-hair"),
    ("genre/sister", "Sister", "category/sister"),
    ("genre/slender", "Slender", "category/slender"),
    ("genre/slim", "Slim", "category/slim"),
    ("genre/slut", "Slut", "category/slut"),
    ("genre/sm", "Sm", "category/sm"),
    ("genre/small-breasts", "Small Breasts", "category/small-breasts"),
    ("genre/snow-white-skin", "Snow White Skin", "category/snow-white-skin"),
    ("genre/snowy-white-skin", "Snowy White Skin", "category/snowy-white-skin"),
    ("genre/spanking", "Spanking", "category/spanking"),
    ("genre/sports", "Sports", "category/sports"),
    ("genre/squirting", "Squirting", "category/squirting"),
    ("genre/stockings", "Stockings", "category/stockings"),
    ("genre/submissive-men", "Submissive Men", "category/submissive-men"),
    ("genre/swallow", "Swallow", "category/swallow"),
    ("genre/tattoo", "Tattoo", "category/tattoo"),
    ("genre/tights", "Tights", "category/tights"),
    ("genre/tit-job", "Tit Job", "category/tit-job"),
    ("genre/titjob", "Titjob", "category/titjob"),
    ("genre/tits", "Tits", "category/tits"),
    ("genre/toy", "Toy", "category/toy"),
    ("genre/tsukasa-aoi", "Tsukasa Aoi", "category/tsukasa-aoi"),
    ("genre/uncensored-leak", "Uncensored Leak", "category/uncensored-leak"),
    ("genre/underwear", "Underwear", "category/underwear"),
    ("genre/uniform", "Uniform", "category/uniform"),
    ("genre/urinate", "Urinate", "category/urinate"),
    ("genre/vibe", "Vibe", "category/vibe"),
    ("genre/vibrating-egg", "Vibrating Egg", "category/vibrating-egg"),
    ("genre/vibrator", "Vibrator", "category/vibrator"),
    ("genre/virgin", "Virgin", "category/virgin"),
    ("genre/wife", "Wife", "category/wife"),
    ("genre/words", "Words", "category/words"),
    ("genre/young-housewife", "Young Housewife", "category/young-housewife"),
    ("genre/yu-shinoda", "Yu Shinoda", "category/yu-shinoda"),
    ("genre/yua-mikami", "Yua Mikami", "category/yua-mikami"),
    ("genre/yui-hatano", "Yui Hatano", "category/yui-hatano"),
]
ROUTE_PATHS = dict((v, p) for v, n, p in ROUTES)
ROUTES_COM = [
    ("latest", "最新发布", ""),
    ("category/chinese-subtitles", "中文字幕", "category/chinese-subtitles"),
    ("category/censored-jav", "有码 JAV", "category/censored-jav"),
    ("category/uncensored-jav", "无码 JAV", "category/uncensored-jav"),
    ("category/reducing-mosaic", "流出无码", "category/reducing-mosaic"),
    ("category/amateur", "素人精选", "category/amateur"),
    ("category/english-subtitles", "英文字幕", "category/english-subtitles"),
]
ROUTE_PATHS_COM = dict((v, p) for v, n, p in ROUTES_COM)

_CHALLENGE_RE = re.compile(r"Just a moment|cf-browser-verification|_cf_chl_opt|cf-chl-|challenge-platform|challenges\.cloudflare\.com", re.I)
_AD_RE = re.compile(r"(doubleclick|googlesyndication|google-analytics|adsco\.re|exoclick|juicyads|trafficjunky|popads|popcash|magsrv|realsrv|syndication|histats|cnzz|baidu)", re.I)
_ASSET_RE = re.compile(r"\.(js|css|png|jpe?g|webp|gif|svg|ico|woff2?|ttf|json|xml|vtt|srt)(?:[?#]|$)", re.I)
_ABS_MEDIA_RE = re.compile(r"(?:https?:)?//[a-zA-Z0-9._~:/?#\[\]@!$&()*+,;=%\-]+\.(?:m3u8|mp4)(?:\?[a-zA-Z0-9._~:/?#\[\]@!$&()*+,;=%\-]*)?", re.I)
_FIELD_RE = re.compile(r"(?:urlPlay|video_url|hlsUrl|[\"']?(?:file|source|hls|mp4)[\"']?)\s*[:=]\s*[\"']((?:https?:)?//[^\"'\s<>]+)[\"']", re.I)
_ST_RE = re.compile(r"get_video\?id=([a-zA-Z0-9_\-]+)&expires=([0-9]+)&ip=([a-zA-Z0-9._\-]+)&token=([a-zA-Z0-9_\-]+)", re.I)
_ATOB_RE = re.compile(r"atob\(\s*[\"']([A-Za-z0-9+/=]{20,})[\"']\s*\)")
_PACKED_RE = re.compile(r"eval\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*[dr]\s*\)\s*\{[\s\S]*?\}\s*\(\s*(['\"])([\s\S]*?)\1\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(['\"])([\s\S]*?)\5\.split\(\s*['\"]\|['\"]\s*\)")
_EXCLUDE_RE = re.compile(r"^/(?:zh/|ja/|en/)?(?:category|tag|page|popular|wp-admin|wp-json|feed|author|search|chinese|censored|uncensored|uncensored-leaked|amateur|fc2|english-subtitles)(?:/|$)", re.I)
_VIDEOPHP_RE = re.compile(r"^/(?:zh/|ja/|en/)?video\.php\?slug=[^&#]+$", re.I)
_NUMHTML_RE = re.compile(r"^/(?:zh/|ja/|en/)?\d+\.html$", re.I | re.ASCII)
_VIDEOPATH_RE = re.compile(r"^/(?:zh/|ja/|en/)?(?:video|videos|archives|jav)/[^/?#]+/?$", re.I)
_SLUGPATH_RE = re.compile(r"^/(?:zh/|ja/)?[a-zA-Z0-9]+-[a-zA-Z0-9-]+/?$", re.ASCII)
_CODE_RE = re.compile(r"\b([0-9]{0,3}[A-Z]{2,6}-\d{2,5}|FC2-PPV-\d+)\b", re.I | re.ASCII)
_DATE_RE = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b", re.ASCII)
_BADTITLE_RE = re.compile(r"^(popular|latest|more|read more|watch|jav|hd|4k|\d+)$", re.I | re.ASCII)
_CARD_CLASSES = ("box-item", "post", "video-block", "video-item", "post-item")


class _Blocked(Exception):
    pass


class _FetchFail(Exception):
    pass


_VOID_TAGS = set("area base br col embed hr img input link meta param source track wbr".split())


class _El(object):
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.parent = parent


class _Dom(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = _El("", {}, None)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = _El(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(el)
        if tag not in _VOID_TAGS:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        el = _El(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _parse_html(html):
    parser = _Dom()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    return parser.root


def _walk(el):
    yield el
    for child in el.children:
        if isinstance(child, _El):
            for sub in _walk(child):
                yield sub


def _text(el):
    parts = []
    for child in el.children:
        if isinstance(child, _El):
            parts.append(_text(child))
        else:
            parts.append(child)
    return "".join(parts)


def _classes(el):
    return (el.attrs.get("class") or "").split()


def _has_class(el, names):
    have = _classes(el)
    return any(name in have for name in names)


def _has_ancestor(el, names):
    cur = el.parent
    while cur is not None:
        if cur.tag and _has_class(cur, names):
            return True
        cur = cur.parent
    return False


def _closest_card(el):
    cur = el
    while cur is not None:
        if cur.tag == "article" or _has_class(cur, _CARD_CLASSES):
            return cur
        cur = cur.parent
    return None


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace(" ", " ")).strip()


def _origin(url):
    parts = urllib.parse.urlsplit(str(url or ""))
    if parts.scheme and parts.netloc:
        return "%s://%s" % (parts.scheme, parts.netloc)
    return ""


def _resolve(raw, base):
    return urllib.parse.urljoin(str(base or ""), str(raw or ""))


def _query_value(raw, key):
    query = str(raw or "").split("?", 1)[1].split("#", 1)[0] if "?" in str(raw or "") else ""
    for part in query.split("&"):
        if not part:
            continue
        if "=" in part:
            name, value = part.split("=", 1)
        else:
            name, value = part, ""
        try:
            if urllib.parse.unquote_plus(name) == key:
                return urllib.parse.unquote_plus(value)
        except Exception:
            pass
    return ""


def _normalize_http(raw, base):
    text = str(raw or "").strip()
    if not text or re.match(r"^(data:|javascript:|about:blank|#)", text, re.I):
        return ""
    try:
        absolute = _resolve(text, base)
        if re.match(r"^https?://", absolute, re.I):
            return absolute
    except Exception:
        pass
    return ""


def _normalize_content_path(raw, page_url, site_origin):
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        absolute = _resolve(text, page_url)
        if _origin(absolute) == site_origin:
            path = urllib.parse.urlsplit(absolute).path or "/"
            slug = _query_value(absolute, "slug")
            if re.match(r"^/(?:zh/|ja/|en/)?video\.php$", path, re.I) and slug:
                return "/video.php?slug=" + urllib.parse.quote(slug, safe="")
            return re.sub(r"^/(?:zh|ja|en)/(video|videos|archives|jav)/", r"/\1/", path, flags=re.I)
        return absolute
    except Exception:
        return ""


def _is_content_path(path):
    if not path:
        return False
    if _EXCLUDE_RE.match(path):
        return False
    if _VIDEOPHP_RE.match(path):
        return True
    if _NUMHTML_RE.match(path):
        return True
    if _VIDEOPATH_RE.match(path):
        return True
    if _SLUGPATH_RE.match(path):
        return True
    return False


def _valid_title(value):
    text = _clean(value)
    if not text or len(text) < 4:
        return False
    if _BADTITLE_RE.match(text):
        return False
    return True


def _looks_direct(url):
    text = str(url or "").strip()
    if not text:
        return False
    if re.search(r"\.(m3u8|mp4|mkv|flv|webm)(\?.*)?$", text, re.I):
        return True
    if re.search(r"/get_video\?id=.*&token=", text, re.I):
        return True
    if re.search(r"/(hls|m3u8|master\.txt)\b", text, re.I) and not re.search(r"\.html?(\?|$)", text, re.I):
        return True
    return False


def _is_ad(url):
    return bool(_AD_RE.search(str(url or "")))


def _unescape(text):
    out = str(text or "")
    out = out.replace("\\u002f", "/").replace("\\u002F", "/")
    out = out.replace("\\u0026", "&")
    out = out.replace("\\u003d", "=").replace("\\u003D", "=")
    out = out.replace("\\u003f", "?").replace("\\u003F", "?")
    out = out.replace("\\/", "/")
    out = re.sub(r"&amp;", "&", out, flags=re.I)
    return out


def _normalize_media(raw, referer):
    cleaned = str(raw or "")
    cleaned = cleaned.replace("\\u002f", "/").replace("\\u002F", "/")
    cleaned = cleaned.replace("\\u0026", "&")
    cleaned = cleaned.replace("\\/", "/")
    cleaned = re.sub(r"&amp;", "&", cleaned, flags=re.I)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    if re.match(r"^(?:https?%3a%2f%2f|%2f%2f)", cleaned, re.I):
        try:
            cleaned = urllib.parse.unquote(cleaned)
        except Exception:
            pass
    try:
        absolute = _resolve(cleaned, referer)
        if re.match(r"^https?://", absolute, re.I):
            return absolute
    except Exception:
        pass
    return ""


def _player_configs(html):
    results = []
    for match in re.finditer(r"(?:window\s*\.\s*)?PLAYER_CONFIG\s*=\s*", html or ""):
        start = match.end()
        if start >= len(html) or html[start] != "{":
            continue
        depth = 0
        quoted = False
        escape = False
        limit = min(len(html), start + 262144)
        i = start
        while i < limit:
            ch = html[i]
            if quoted:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    quoted = False
            elif ch == '"':
                quoted = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        results.append(json.loads(html[start:i + 1]))
                    except Exception:
                        pass
                    break
            i += 1
        if len(results) >= 8:
            break
    return [item for item in results if isinstance(item, dict)]


def _encode_base(num, radix, chars):
    if num < radix:
        return chars[num]
    return _encode_base(num // radix, radix, chars) + _encode_base(num % radix, radix, chars)


def _unpack_block(payload, radix, count, words):
    if not isinstance(payload, str) or len(payload) > 262144:
        return ""
    if radix < 2 or radix > 62 or count < 1 or count > 10000 or len(words) > 10000:
        return ""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    table = {}
    idx = count
    while idx:
        idx -= 1
        key = _encode_base(idx, radix, chars)
        table[key] = words[idx] if idx < len(words) and words[idx] else key
    return re.sub(r"\b\w+\b", lambda m: table.get(m.group(0), m.group(0)), payload, flags=re.ASCII)


def _unpack_all(html):
    results = []
    for match in _PACKED_RE.finditer(html or ""):
        if len(results) >= 16:
            break
        try:
            unpacked = _unpack_block(match.group(2), int(match.group(3)), int(match.group(4)), match.group(6).split("|"))
            if unpacked:
                results.append(unpacked)
        except Exception:
            pass
    return results


class Spider(_BaseSpider):
    def getName(self):
        return "SupJAV"

    def init(self, extend=""):
        self.base = DEFAULT_SITE
        self.lang = "zh"
        self.timeout = 18
        self.ua = DEFAULT_UA
        self.tickets = {}
        self.mix = False
        self._prof = None
        cfg = {}
        if extend:
            if isinstance(extend, dict):
                cfg = dict(extend)
            else:
                text = str(extend).strip()
                try:
                    parsed = json.loads(text)
                    cfg = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    cfg = {"cookie": text} if "=" in text else {}
        mode = str(cfg.get("mode") or DEFAULT_MODE)
        self.mode_label = mode
        if mode in ("com", "mix"):
            self.mix = mode == "mix"
            self.base = BACKUP_SITE
        elif mode == "custom" and re.match(r"^https?://", str(cfg.get("site") or ""), re.I):
            self.base = str(cfg.get("site")).rstrip("/")
        if mode in ("com", "mix"):
            self.routes = ROUTES_COM
            self.route_paths = ROUTE_PATHS_COM
        else:
            self.routes = ROUTES
            self.route_paths = ROUTE_PATHS
        lang = str(cfg.get("lang") or "zh")
        self.lang = lang if lang in ("zh", "ja", "en") else "zh"
        try:
            seconds = int(cfg.get("timeout") or 18)
        except Exception:
            seconds = 18
        self.timeout = min(max(seconds, 5), 45)
        self.ua = str(cfg.get("ua") or DEFAULT_UA)
        now = time.time()
        base_host = urllib.parse.urlsplit(self.base).netloc
        if cfg.get("cookie"):
            cookie = re.sub(r"[\r\n]+", "; ", str(cfg.get("cookie")))
            self.tickets[base_host] = {"cookie": cookie, "ua": str(cfg.get("ua") or ""), "issued_at": now}
        extra = cfg.get("tickets")
        if isinstance(extra, dict):
            for host, ticket in extra.items():
                if isinstance(ticket, dict) and ticket.get("cookie"):
                    name = urllib.parse.urlsplit(str(host)).netloc if "://" in str(host) else str(host)
                    try:
                        issued = float(ticket.get("issued_at") or now)
                    except Exception:
                        issued = now
                    self.tickets[name] = {"cookie": str(ticket.get("cookie")), "ua": str(ticket.get("ua") or ""), "issued_at": issued}

    def _ticket(self, host):
        ticket = self.tickets.get(host)
        if not ticket:
            return None
        if ticket.get("issued_at") and time.time() - float(ticket["issued_at"]) > TICKET_TTL:
            return None
        return ticket

    def _headers_for(self, url, referer=None):
        host = urllib.parse.urlsplit(str(url or "")).netloc
        ticket = self._ticket(host)
        headers = {
            "User-Agent": (ticket.get("ua") if ticket and ticket.get("ua") else self.ua),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": referer or (_origin(self.base) + "/"),
        }
        if ticket and ticket.get("cookie"):
            headers["Cookie"] = ticket["cookie"]
        return headers

    def _fetch(self, url, referer=None, query=None):
        target = str(url or "")
        if query:
            target = target + ("&" if "?" in target else "?") + urllib.parse.urlencode(query)
        request = urllib.request.Request(target, headers=self._headers_for(target, referer))
        status = 0
        final = target
        raw = b""
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                final = response.geturl()
                raw = response.read()
        except urllib.error.HTTPError as err:
            status = err.code or 0
            try:
                final = err.geturl() or target
            except Exception:
                final = target
            try:
                raw = err.read()
            except Exception as read_err:
                raw = getattr(read_err, "partial", b"") or b""
        except Exception as err:
            raise _FetchFail("NETWORK: %s" % err)
        if raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        text = raw.decode("utf-8", "replace")
        if len(text) < 8000 and _CHALLENGE_RE.search(text):
            raise _Blocked(target)
        if status == 429:
            raise _FetchFail("RATE_LIMITED")
        if status == 404:
            raise _FetchFail("NOT_FOUND")
        if status < 200 or status >= 300:
            raise _FetchFail("HTTP %d" % status)
        if not text.strip():
            raise _FetchFail("EMPTY")
        return status, final, text

    def _home_url(self):
        if self.base == BACKUP_SITE or self.lang == "en":
            return self.base + "/"
        return "%s/%s/" % (self.base, self.lang)

    def _route_url(self, value):
        path = getattr(self, "route_paths", ROUTE_PATHS).get(value)
        if path is None:
            return ""
        if not path:
            return self.base + "/"
        return "%s/%s" % (self.base, path)

    def _cache_get(self, key):
        try:
            if hasattr(self, "getCache"):
                return self.getCache(key)
        except Exception:
            pass
        return None

    def _cache_set(self, key, value):
        try:
            if hasattr(self, "setCache"):
                self.setCache(key, value)
        except Exception:
            pass

    def _profile(self):
        if self._prof:
            return self._prof
        if self.base == BACKUP_SITE:
            prof = {"search_url": self.base + "/", "search_key": "s", "paging": "path"}
        else:
            prof = {"search_url": self.base + "/search", "search_key": "keyword", "paging": "query"}
        cache_key = "supjav18_profile_%s_%s" % (self.base, self.lang)
        cached = self._cache_get(cache_key)
        if cached:
            try:
                saved = json.loads(cached)
                if time.time() - float(saved.get("at") or 0) < 3600:
                    self._prof = {"search_url": saved["search_url"], "search_key": saved["search_key"], "paging": saved["paging"]}
                    return self._prof
            except Exception:
                pass
        try:
            status, final, text = self._fetch(self._home_url())
        except _FetchFail:
            self._prof = prof
            return prof
        root = _parse_html(text)
        origin = _origin(final)
        for form in [el for el in _walk(root) if el.tag == "form"]:
            method = str(form.attrs.get("method") or "get").lower()
            if method != "get":
                continue
            field = ""
            for inp in [el for el in _walk(form) if el.tag == "input"]:
                name = inp.attrs.get("name") or ""
                if name in ("keyword", "s") or ((inp.attrs.get("type") or "").lower() == "search" and name):
                    field = name
                    break
            if not field:
                continue
            action = _normalize_http(form.attrs.get("action") or final, final)
            if action and _origin(action) == origin:
                prof["search_url"] = action
                prof["search_key"] = field
                break
        query_paging = False
        has_box = False
        for el in _walk(root):
            if _has_class(el, ("box-item",)):
                has_box = True
            if el.tag == "a" and el.attrs.get("href"):
                if _has_ancestor(el, ("pagination", "page-numbers")) and _query_value(_resolve(el.attrs["href"], final), "page"):
                    query_paging = True
        prof["paging"] = "query" if (query_paging or has_box) else "path"
        self._prof = prof
        try:
            self._cache_set(cache_key, json.dumps({"at": time.time(), "search_url": prof["search_url"], "search_key": prof["search_key"], "paging": prof["paging"]}))
        except Exception:
            pass
        return prof

    def _page_url(self, route_url, page, paging):
        if page <= 1:
            return route_url
        if paging == "query":
            return route_url + ("&" if "?" in route_url else "?") + "page=%d" % page
        return route_url.rstrip("/") + "/page/%d/" % page

    def _parse_cards(self, html, page_url):
        root = _parse_html(html)
        site_origin = _origin(page_url)
        entries = {}
        order = []
        for anchor in [el for el in _walk(root) if el.tag == "a" and el.attrs.get("href")]:
            raw = str(anchor.attrs.get("href") or "").strip()
            if not raw or raw.startswith("#") or raw.lower().startswith("javascript:"):
                continue
            nid = _normalize_content_path(raw, page_url, site_origin)
            if not _is_content_path(nid):
                continue
            entry = entries.get(nid)
            if entry is None:
                entry = {"id": nid, "links": [], "containers": []}
                entries[nid] = entry
                order.append(nid)
            entry["links"].append(anchor)
            card = _closest_card(anchor)
            if card is not None:
                entry["containers"].append(card)
        items = []
        for nid in order:
            card = self._build_card(entries[nid], page_url)
            if card:
                items.append(card)
        return items, root

    def _build_card(self, entry, page_url):
        title = ""
        poster = ""
        nodes = list(entry["links"]) + list(entry["containers"])
        for node in nodes:
            if not title:
                attr_title = _clean(node.attrs.get("title"))
                if _valid_title(attr_title):
                    title = attr_title
            imgs = [node] if node.tag == "img" else [el for el in _walk(node) if el.tag == "img"]
            for img in imgs:
                if not title:
                    alt = _clean(img.attrs.get("alt"))
                    if _valid_title(alt):
                        title = alt
                if not poster:
                    raw_src = img.attrs.get("data-original") or img.attrs.get("data-src") or img.attrs.get("data-lazy-src") or img.attrs.get("src") or ""
                    poster = _normalize_http(raw_src, page_url)
        if not title:
            for node in nodes:
                for el in _walk(node):
                    if el.tag in ("h2", "h3", "h4") or _has_class(el, ("title", "entry-title")):
                        text = _clean(_text(el))
                        if _valid_title(text):
                            title = text
                            break
                if title:
                    break
        if not title:
            for anchor in entry["links"]:
                text = _clean(_text(anchor))
                if _valid_title(text):
                    title = text
                    break
        if not title:
            return None
        parts = []
        code = _CODE_RE.search(title)
        if code:
            parts.append(code.group(1).upper())
        for container in entry["containers"]:
            meta = ""
            for el in _walk(container):
                if _has_class(el, ("meta", "date", "views", "post-meta")):
                    meta = _clean(_text(el))
                    break
            if not meta:
                meta = _clean(_text(container))
            found = _DATE_RE.search(meta)
            if found and found.group(1) not in parts:
                parts.append(found.group(1))
                break
        item = {"vod_id": entry["id"][:1024], "vod_name": title[:240], "vod_pic": poster, "vod_remarks": " · ".join(parts)}
        return item

    def _has_next(self, root, page_url, page):
        candidates = []
        for el in _walk(root):
            if el.tag == "a" and el.attrs.get("href"):
                if _has_ancestor(el, ("pagination", "page-numbers")) or _has_class(el, ("next", "nextpostslink")) or (el.attrs.get("rel") or "") == "next":
                    candidates.append(el)
            elif el.tag == "link" and (el.attrs.get("rel") or "") == "next" and el.attrs.get("href"):
                candidates.append(el)
        for el in candidates:
            absolute = _normalize_http(el.attrs.get("href"), page_url)
            if not absolute or _origin(absolute) != _origin(page_url):
                continue
            target = 0
            query_page = _query_value(absolute, "page")
            if query_page.isdigit():
                target = int(query_page)
            else:
                matched = re.search(r"/page/(\d+)/?$", urllib.parse.urlsplit(absolute).path)
                if matched:
                    target = int(matched.group(1))
            label = " ".join([el.attrs.get("rel") or "", el.attrs.get("class") or "", _text(el)])
            if target > page or (not target and re.search(r"next", label, re.I)):
                return True
        return False

    def _assert_route(self, root, final_url, expected_url, page):
        canonical = ""
        for el in _walk(root):
            if el.tag == "link" and (el.attrs.get("rel") or "") == "canonical" and el.attrs.get("href"):
                canonical = _normalize_http(el.attrs.get("href"), final_url)
                break

        def comparable(url):
            path = urllib.parse.urlsplit(url).path or "/"
            path = re.sub(r"/+", "/", path)
            path = re.sub(r"/page/\d+/?$", "", path)
            return path.rstrip("/")

        if canonical and comparable(canonical) != comparable(expected_url):
            expected_path = comparable(expected_url)
            alias_path = ""
            matched = re.match(r"^/category/(.+)$", expected_path)
            if matched:
                alias_path = "/genre/" + matched.group(1)
            if not alias_path or comparable(canonical) != alias_path:
                return "站点返回了其他栏目页面，请重新读取分类"
        for el in _walk(root):
            if _has_class(el, ("active", "current")) and _has_ancestor(el, ("pagination", "page-numbers")):
                text = _clean(_text(el))
                if text.isdigit() and int(text) != page:
                    return "站点没有返回请求的分页，已停止重复加载"
                break
        return ""

    def _list_result(self, items, page, has_next, msg=""):
        if items:
            result = {"list": items, "page": page, "pagecount": 9999 if has_next else page, "limit": len(items), "total": 999999}
        else:
            result = {"list": [], "page": page, "pagecount": page, "limit": 24, "total": 0}
        if msg:
            result["msg"] = msg
        return result

    def homeContent(self, filter):
        classes = [{"type_id": value, "type_name": name} for value, name, path in getattr(self, "routes", ROUTES)]
        if self.base == BACKUP_SITE:
            classes.append({"type_id": "__diag__", "type_name": "🔧 站点诊断"})
        return {"class": classes, "filters": {}}

    def _blog_items(self, url, query=None):
        status, final, text = self._fetch(url, query=query)
        items, root = self._parse_cards(text, final)
        for item in items:
            item["vod_id"] = "blog@@" + item["vod_id"]
        return items

    def _blog_route_url(self, tid, page):
        path = ROUTE_PATHS.get(str(tid or ""))
        if path is None:
            return ""
        url = DEFAULT_SITE + "/" + path if path else DEFAULT_SITE + "/"
        if page and page > 1:
            url = self._page_url(url, page, {"paging": "query"})
        return url

    def _blog_fallback(self, tid, page):
        url = self._blog_route_url(tid, page)
        if not url:
            return None
        try:
            items = self._blog_items(url)
        except Exception:
            return None
        return self._list_result(items, page, len(items) >= 24, FALLBACK_MSG)

    def homeVideoContent(self):
        try:
            status, final, text = self._fetch(self._route_url("latest"))
            items, root = self._parse_cards(text, final)
            return {"list": items}
        except _Blocked:
            if getattr(self, "mix", False):
                try:
                    return {"list": self._blog_items(self._blog_route_url("latest", 1)), "msg": FALLBACK_MSG}
                except Exception:
                    pass
            return {"list": [], "msg": BLOCK_MSG}
        except Exception as err:
            return {"list": [], "msg": "首页加载失败：%s" % err}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        if str(tid or "") == "__diag__":
            return self._diag_result(page)
        route_url = self._route_url(str(tid or ""))
        if not route_url:
            return self._list_result([], page, False, "当前站点没有这个分类")
        try:
            prof = self._profile()
            url = self._page_url(route_url, page, prof["paging"])
            status, final, text = self._fetch(url)
            items, root = self._parse_cards(text, final)
            if not items and "box-item" in text:
                return self._list_result([], page, False, "页面结构与内容目录不匹配，请更新源")
            mismatch = self._assert_route(root, final, route_url, page)
            if mismatch:
                return self._list_result([], page, False, mismatch)
            return self._list_result(items, page, self._has_next(root, final, page))
        except _Blocked:
            if getattr(self, "mix", False):
                fb = self._blog_fallback(tid, page)
                if fb is not None:
                    return fb
            return self._list_result([], page, False, BLOCK_MSG)
        except Exception as err:
            return self._list_result([], page, False, "分类加载失败：%s" % err)

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        keyword = str(key or "").strip()
        if not keyword:
            return self._list_result([], page, False)
        if len(keyword) > 200:
            return self._list_result([], page, False, "搜索词长度不能超过 200 个字符")
        try:
            prof = self._profile()
            query = {prof["search_key"]: keyword}
            if prof["paging"] == "query":
                if page > 1:
                    query["page"] = str(page)
                status, final, text = self._fetch(prof["search_url"], query=query)
            else:
                status, final, text = self._fetch(self._page_url(prof["search_url"], page, "path"), query=query)
            items, root = self._parse_cards(text, final)
            if not items and "box-item" in text:
                return self._list_result([], page, False, "页面结构与内容目录不匹配，请更新源")
            mismatch = self._assert_route(root, final, prof["search_url"], page)
            if mismatch:
                return self._list_result([], page, False, mismatch)
            return self._list_result(items, page, self._has_next(root, final, page))
        except _Blocked:
            if getattr(self, "mix", False):
                try:
                    items = self._blog_items(DEFAULT_SITE + "/search", query={"keyword": keyword})
                    return self._list_result(items, page, False, FALLBACK_MSG)
                except Exception:
                    pass
            return self._list_result([], page, False, BLOCK_MSG)
        except Exception as err:
            return self._list_result([], page, False, "搜索失败：%s" % err)


    def _detail_url(self, cid):
        text = str(cid or "").strip()
        if text.startswith("blog@@"):
            rest = text[6:]
            return DEFAULT_SITE + (rest if rest.startswith("/") else "/" + rest)
        if text.startswith("http"):
            return text
        if text.startswith("/"):
            return self.base + text
        return self.base + "/" + text

    def _detail_title(self, root):
        raw = ""
        for el in _walk(root):
            if el.tag == "h1" and _has_ancestor(el, ("post-meta",)):
                raw = _clean(_text(el))
                break
        if not raw:
            for el in _walk(root):
                if el.tag == "h1" and _has_class(el, ("entry-title",)):
                    raw = _clean(_text(el))
                    break
        if not raw:
            for el in _walk(root):
                if el.tag == "h1":
                    raw = _clean(_text(el))
                    break
        if not raw:
            for el in _walk(root):
                if el.tag == "meta" and (el.attrs.get("property") or "") == "og:title":
                    raw = _clean(el.attrs.get("content"))
                    break
        if not raw:
            for el in _walk(root):
                if el.tag == "title":
                    raw = _clean(_text(el))
                    break
        raw = re.sub(r"\s*[-|]\s*Supjav.*$", "", raw, flags=re.I)
        raw = re.sub(r"\s*[-|]\s*免费在线观看.*$", "", raw)
        return raw.strip()

    def _detail_poster(self, root, base_url):
        candidates = []
        for el in _walk(root):
            if el.tag == "meta" and (el.attrs.get("property") or "") == "og:image":
                candidates.append(el.attrs.get("content"))
                break
        target = None
        for el in _walk(root):
            if el.tag == "img" and (_has_ancestor(el, ("post-meta", "video-meta")) or _has_class(el, ("wp-post-image",))):
                target = el
                break
        if target is not None:
            candidates.append(target.attrs.get("data-original"))
            candidates.append(target.attrs.get("src"))
        for candidate in candidates:
            url = _normalize_http(candidate, base_url)
            if url:
                return url
        return ""

    def _detail_summary(self, root):
        lines = []
        for el in _walk(root):
            take = False
            if el.tag in ("p", "li") and _has_ancestor(el, ("post-meta",)):
                take = True
            elif el.tag == "p" and _has_ancestor(el, ("cats", "video-info")):
                take = True
            if not take:
                continue
            text = _clean(_text(el))
            if text and 2 < len(text) < 300 and text not in lines:
                lines.append(text)
        if not lines:
            for prop, name in (("property", "og:description"), ("name", "description")):
                for el in _walk(root):
                    if el.tag == "meta" and (el.attrs.get(prop) or "") == name:
                        text = _clean(el.attrs.get("content"))
                        if text:
                            lines.append(text)
                            break
                if lines:
                    break
        return "\n".join(lines)

    def _collect_servers(self, root):
        servers = {}
        order = []
        anchors = [el for el in _walk(root) if el.tag == "a" and (el.attrs.get("data-link") or "").strip()]
        for idx, anchor in enumerate(anchors):
            token = str(anchor.attrs.get("data-link") or "").strip()
            if not token:
                continue
            name = _clean(_text(anchor)) or "线路 %d" % (idx + 1)
            if name not in servers:
                servers[name] = []
                order.append(name)
            if token not in servers[name]:
                servers[name].append(token)
        return [(name, servers[name]) for name in order]

    def _detail_groups(self, root, cid, detail_url):
        groups = []
        servers = self._collect_servers(root)
        if servers:
            for name, tokens in servers:
                episodes = []
                for idx, token in enumerate(tokens):
                    ep_name = "正片" if len(tokens) == 1 else "CD %d" % (idx + 1)
                    ep_id = "slot@@%s@@%s@@%d" % (urllib.parse.quote(str(cid), safe=""), urllib.parse.quote(name, safe=""), idx)
                    episodes.append({"name": ep_name, "id": ep_id})
                groups.append({"name": "线路 %s" % name, "episodes": episodes})
            return groups
        seen = set()
        for el in _walk(root):
            if el.tag != "iframe":
                continue
            raw = el.attrs.get("src") or el.attrs.get("data-src") or el.attrs.get("data-lazy-src") or ""
            absolute = _normalize_http(raw, detail_url)
            if not absolute or _is_ad(absolute) or absolute in seen:
                continue
            seen.add(absolute)
            ep_id = "iframe@@%s@@%s" % (urllib.parse.quote(str(cid), safe=""), absolute.split("#", 1)[0])
            groups.append({"name": "播放器线路 %d" % (len(groups) + 1), "episodes": [{"name": "正片", "id": ep_id}]})
        if not groups:
            ep_id = "page@@%s" % urllib.parse.quote(str(cid), safe="")
            groups.append({"name": "默认线路", "episodes": [{"name": "正片", "id": ep_id}]})
        return groups

    def _blog_detail_url(self, cid):
        text = str(cid or "").strip()
        if not text:
            return ""
        if text.startswith("http"):
            return text
        if text.startswith("/"):
            return DEFAULT_SITE + text
        return DEFAULT_SITE + "/" + text

    def _mirror_groups(self, title):
        try:
            matched = _CODE_RE.search(str(title or ""))
            if not matched:
                return []
            code = matched.group(1).upper()
            status, final, text = self._fetch(DEFAULT_SITE + "/search", query={"keyword": code})
            items, root = self._parse_cards(text, final)
            target = None
            for item in items:
                if code in str(item.get("vod_name") or "").upper():
                    target = item
                    break
            if not target:
                return []
            blog_url = self._blog_detail_url(target.get("vod_id"))
            if not blog_url:
                return []
            status, final, text = self._fetch(blog_url, referer=final)
            root = _parse_html(text)
            groups = self._detail_groups(root, blog_url, final or blog_url)
            out = []
            for group in groups:
                out.append({"name": "BLOG镜像-" + group["name"], "episodes": group["episodes"]})
            return out
        except Exception:
            return []

    def _diag_probe(self, label, url, use_fetch=True):
        try:
            if use_fetch:
                status, final, text = self._fetch(url)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA, "Accept": "text/html"})
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        status, final, text = resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")
                except urllib.error.HTTPError as err:
                    status, final = err.code or 0, url
                    text = err.read().decode("utf-8", "replace")
            if status < 200 or status >= 300:
                return "%s：失败 · HTTP %d" % (label, status)
            if len(text) < 8000 and _CHALLENGE_RE.search(text):
                return "%s：被 Cloudflare 拦截" % label
            items, root = self._parse_cards(text, final)
            return "%s：成功 · 状态 %d · 解析卡片 %d 张" % (label, status, len(items))
        except _Blocked:
            return "%s：被 Cloudflare 拦截（票据未生效）" % label
        except Exception as err:
            return "%s：失败 · %s" % (label, str(err)[:80])

    def _diag_result(self, page):
        lines = []
        lines.append("模式：%s · 节点：%s" % (getattr(self, "mode_label", ""), self.base))
        ticket = self.tickets.get(urllib.parse.urlsplit(BACKUP_SITE).netloc) or {}
        if ticket.get("cookie"):
            lines.append("票据：已载入 · 长度 %d · UA：%s" % (len(ticket["cookie"]), "iPhone Safari" if "iPhone" in (ticket.get("ua") or "") else (ticket.get("ua") or "")[:24]))
        else:
            lines.append("票据：无（未载入任何票据）")
        lines.append(self._diag_probe("com 首页（带票）", self.base + "/"))
        cat_url = self._route_url("category/chinese-subtitles")
        if cat_url:
            lines.append(self._diag_probe("com 分类·中文字幕（带票）", cat_url))
        lines.append(self._diag_probe("com 首页（无票裸连）", self.base + "/", use_fetch=False))
        lines.append(self._diag_probe("blog 首页（对比）", DEFAULT_SITE + "/"))
        self._diag_lines = lines
        items = [{"vod_id": "diag@@%d" % i, "vod_name": line, "vod_pic": "", "vod_remarks": "诊断"} for i, line in enumerate(lines)]
        return self._list_result(items, page, False, "诊断完成，把这几行结果发给 Dialen")

    def detailContent(self, ids):
        cid = str(ids[0] if ids else "").strip()
        if not cid or len(cid) > 1024:
            return {"list": [], "msg": "内容标识无效"}
        if cid.startswith("diag@@"):
            lines = getattr(self, "_diag_lines", None) or ["请先打开「🔧 站点诊断」分类"]
            vod = {"vod_id": cid, "vod_name": "站点诊断", "vod_pic": "", "vod_remarks": "", "type_name": "JAV", "vod_actor": BRAND_ACTOR, "vod_director": BRAND_DIRECTOR, "vod_content": "\n".join(lines), "vod_play_from": "", "vod_play_url": ""}
            return {"list": [vod]}
        detail_url = self._detail_url(cid)
        try:
            status, final, text = self._fetch(detail_url)
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception as err:
            return {"list": [], "msg": "详情加载失败：%s" % err}
        root = _parse_html(text)
        title = self._detail_title(root)
        poster = self._detail_poster(root, final)
        summary = self._detail_summary(root)
        groups = self._detail_groups(root, cid, final)
        if getattr(self, "mix", False) and not cid.startswith("blog@@"):
            groups = groups + self._mirror_groups(title)
        froms = []
        urls = []
        multi = False
        for group in groups:
            froms.append(group["name"])
            if len(group["episodes"]) > 1:
                multi = True
            urls.append("#".join("%s$%s" % (ep["name"], ep["id"]) for ep in group["episodes"]))
        content_parts = ["当前节点：%s" % self.base, DIVIDER_THICK, SYNOPSIS_GROUP]
        if summary:
            content_parts.append(MARKER)
            content_parts.append(summary[:2000])
        vod = {
            "vod_id": cid,
            "vod_name": title[:240] if title else cid,
            "vod_pic": poster,
            "vod_remarks": "剧集" if multi else "电影",
            "type_name": "JAV",
            "vod_actor": BRAND_ACTOR,
            "vod_director": BRAND_DIRECTOR,
            "vod_content": "\n".join(content_parts),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod]}

    def _media_source(self, url, referer, hint=""):
        is_hls = bool(re.search(r"\.m3u8(\?|$)", url, re.I) or re.search(r"/(hls|master\.txt)\b", url, re.I))
        if hint:
            mime = hint
        elif is_hls:
            mime = HLS_MIME
        elif re.search(r"\.mp4(?:[?#]|$)", url, re.I):
            mime = "video/mp4"
        elif re.search(r"\.webm(?:[?#]|$)", url, re.I):
            mime = "video/webm"
        elif re.search(r"\.mkv(?:[?#]|$)", url, re.I):
            mime = "video/x-matroska"
        elif re.search(r"\.flv(?:[?#]|$)", url, re.I):
            mime = "video/x-flv"
        else:
            mime = ""
        origin = _origin(referer) if referer else DEFAULT_SITE
        return {
            "url": url,
            "mime": mime,
            "headers": {
                "User-Agent": self.ua,
                "Referer": referer or (origin + "/"),
                "Origin": origin,
                "Sec-Fetch-Mode": "cors",
            },
        }

    def _add_source(self, sources, seen, raw, referer, hint=""):
        resolved = _normalize_media(raw, referer)
        if not resolved or resolved in seen or _is_ad(resolved):
            return
        if _ASSET_RE.search(resolved):
            return
        seen.add(resolved)
        sources.append(self._media_source(resolved, referer, hint))

    def _scan(self, html, page_url, sources, seen, queue, depth):
        root = _parse_html(html)
        for cfg in _player_configs(html):
            if isinstance(cfg.get("m3u8"), str) and cfg.get("m3u8").strip():
                self._add_source(sources, seen, cfg["m3u8"], page_url, HLS_MIME)
            if isinstance(cfg.get("alternate720"), str) and cfg.get("alternate720").strip():
                self._add_source(sources, seen, cfg["alternate720"], page_url, HLS_MIME)
        for el in _walk(root):
            if el.tag in ("video", "source") or any(name in el.attrs for name in ("data-hash", "data-video", "data-m3u8")):
                candidates = [el.attrs.get("src"), el.attrs.get("data-hash"), el.attrs.get("data-video"), el.attrs.get("data-m3u8")]
                for candidate in candidates:
                    if not candidate:
                        continue
                    typ = el.attrs.get("type") or ""
                    if re.search(r"mpegurl|m3u8", typ, re.I) or candidate == el.attrs.get("data-m3u8"):
                        hint = HLS_MIME
                    elif re.match(r"(?:video|audio)/", typ):
                        hint = typ
                    else:
                        hint = ""
                    if not candidate.startswith("blob:") and (_looks_direct(candidate) or hint):
                        self._add_source(sources, seen, candidate, page_url, hint)
            if el.tag == "iframe":
                raw = el.attrs.get("src") or el.attrs.get("data-src") or el.attrs.get("data-lazy-src") or ""
                absolute = _normalize_http(raw, page_url)
                if absolute and not _is_ad(absolute) and all(item["url"] != absolute for item in queue):
                    queue.append({"url": absolute, "referer": page_url, "depth": depth + 1})
        combined = html
        unpacked = _unpack_all(html)
        if unpacked:
            combined = combined + "\n" + "\n".join(unpacked)
        unescaped = _unescape(combined)
        for match in _ABS_MEDIA_RE.finditer(unescaped):
            self._add_source(sources, seen, match.group(0), page_url)
        for match in _FIELD_RE.finditer(unescaped):
            if _looks_direct(match.group(1)):
                self._add_source(sources, seen, match.group(1), page_url)
        st = _ST_RE.search(unescaped)
        if st:
            st_url = "https://streamtape.com/get_video?id=%s&expires=%s&ip=%s&token=%s&stream=1" % (st.group(1), st.group(2), st.group(3), st.group(4))
            self._add_source(sources, seen, st_url, page_url)
        for match in _ATOB_RE.finditer(unescaped):
            try:
                decoded = base64.b64decode(match.group(1)).decode("utf-8", "ignore").strip()
            except Exception:
                continue
            if _looks_direct(decoded):
                self._add_source(sources, seen, decoded, page_url)
            else:
                for sub in _ABS_MEDIA_RE.finditer(decoded):
                    self._add_source(sources, seen, sub.group(0), page_url)

    def _extract_sources(self, html, page_url, referer):
        sources = []
        seen = set()
        queue = []
        self._scan(html, page_url, sources, seen, queue, 0)
        if sources:
            return sources
        visited = set([page_url])
        requested = 0
        while queue and requested < 10:
            item = queue.pop(0)
            if item["url"] in visited or item["depth"] > 2:
                continue
            visited.add(item["url"])
            requested += 1
            try:
                status, final, text = self._fetch(item["url"], referer=item["referer"])
            except _Blocked:
                raise
            except Exception:
                continue
            self._scan(text, final or item["url"], sources, seen, queue, item["depth"])
            if sources:
                return sources
        return sources

    def _detect_embed_api(self, html):
        match = re.search(r"https?://[a-zA-Z0-9.-]+/supjav\.php", html or "", re.I)
        return match.group(0) if match else DEFAULT_EMBED_API

    def _resolve_datalink(self, token, api, detail_url):
        reversed_code = str(token)[::-1]
        url = api + ("&" if "?" in api else "?") + "c=" + urllib.parse.quote(reversed_code, safe="")
        status, final, text = self._fetch(url, referer=detail_url)
        return self._extract_sources(text, final or url, detail_url)

    def _play_ok(self, source):
        return {"parse": 0, "jx": 0, "playUrl": "", "url": source["url"], "header": source["headers"]}

    def _play_msg(self, msg):
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "msg": msg}

    def playerContent(self, flag, id, vipFlags):
        eid = str(id or "").strip()
        try:
            if eid.startswith("slot@@"):
                parts = eid.split("@@")
                if len(parts) != 4:
                    return self._play_msg("选集参数无效，请重新打开详情")
                cid = urllib.parse.unquote(parts[1])
                server = urllib.parse.unquote(parts[2])
                try:
                    index = int(parts[3])
                except Exception:
                    return self._play_msg("选集参数无效，请重新打开详情")
                detail_url = self._detail_url(cid)
                status, final, text = self._fetch(detail_url)
                root = _parse_html(text)
                servers = dict(self._collect_servers(root))
                tokens = servers.get(server) or []
                if index >= len(tokens):
                    return self._play_msg("该线路已变化，请重新读取详情")
                api = self._detect_embed_api(text)
                sources = self._resolve_datalink(tokens[index], api, final or detail_url)
                if not sources:
                    return self._play_msg("当前线路没有提供可识别的播放地址，请尝试切换其他线路（如 TV / ST / VOE）")
                return self._play_ok(sources[0])
            if eid.startswith("datalink:"):
                parts = eid.split(":")
                token = urllib.parse.unquote(parts[1]) if len(parts) > 1 else ""
                api = urllib.parse.unquote(parts[2]) if len(parts) > 2 and parts[2] else DEFAULT_EMBED_API
                if not token:
                    return self._play_msg("选集参数无效，请重新打开详情")
                sources = self._resolve_datalink(token, api, self.base + "/")
                if not sources:
                    return self._play_msg("该服务器线路未能解析出有效视频源，请尝试切换其他线路（如 TV / ST / VOE）")
                return self._play_ok(sources[0])
            if eid.startswith("iframe@@") or eid.startswith("page@@"):
                parts = eid.split("@@", 2)
                if len(parts) < 2:
                    return self._play_msg("选集参数无效，请重新打开详情")
                cid = urllib.parse.unquote(parts[1])
                detail_url = self._detail_url(cid)
                target = parts[2] if eid.startswith("iframe@@") and len(parts) > 2 else detail_url
                if _looks_direct(target):
                    return self._play_ok(self._media_source(target, detail_url))
                try:
                    status, final, text = self._fetch(target, referer=detail_url)
                    sources = self._extract_sources(text, final or target, detail_url)
                except _Blocked:
                    raise
                except Exception:
                    sources = []
                if sources:
                    return self._play_ok(sources[0])
                headers = {"User-Agent": self.ua, "Referer": detail_url}
                return {"parse": 1, "jx": 1, "playUrl": "", "url": target, "header": headers}
            if _looks_direct(eid):
                return self._play_ok(self._media_source(eid, self.base + "/"))
            if eid.startswith("http"):
                try:
                    status, final, text = self._fetch(eid, referer=self.base + "/")
                    sources = self._extract_sources(text, final or eid, self.base + "/")
                except _Blocked:
                    raise
                except Exception:
                    sources = []
                if sources:
                    return self._play_ok(sources[0])
                headers = {"User-Agent": self.ua, "Referer": self.base + "/"}
                return {"parse": 1, "jx": 1, "playUrl": "", "url": eid, "header": headers}
            return self._play_msg("选集参数无效，请重新打开详情")
        except _Blocked:
            return self._play_msg(BLOCK_MSG)
        except Exception as err:
            return self._play_msg("播放解析失败：%s" % err)
