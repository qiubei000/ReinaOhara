from html import unescape as _unescape
import base64
import json
import re
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    try:
        import sys as _sys
        _sys.path.append("..")
        from base.spider import Spider as _BaseSpider
    except Exception:
        class _BaseSpider(object):
            pass

BRAND_NAME = "蝴蝶影视"
BRAND_ACTOR = "🦋 TG群: @tvshare23"
BRAND_DIRECTOR = "🦋 蝴蝶影视"
TG_GROUP = "https://t.me/tvshare23"
SYNOPSIS_GROUP = "🦋 蝴蝶影视官方交流群：@tvshare23"
DIVIDER_THIN = "────────────────────"
DIVIDER_THICK = "━━━━━━━━━━━━━━"
MARKER = "〔影片简介〕"
LINE_NAME = "🦋 蝴蝶专线"
NODE_LINE = "当前节点：https://onejapanese.com"

BASE = "https://onejapanese.com"
HOST = "onejapanese.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
PAGE_SIZE = 116
SEARCH_PAGE = 97
BLOCK_MSG = "onejapanese.com 被 Cloudflare 拦截，请在 extend 里传入浏览器票据后重试，例如 {\"tickets\": {\"onejapanese.com\": {\"cookie\": \"cf_clearance=...\", \"ua\": \"浏览器UA\"}}}"
CLASSES = [['69', '69'], ['amateur', 'Amateur'], ['anal', 'Anal'], ['asian', 'Asian'], ['ass', 'Ass'], ['babes', 'Babes'], ['babysitters', 'Babysitter'], ['bathroom', 'Bathroom'], ['bbw', 'BBW'], ['bdsm', 'BDSM'], ['beach', 'Beach'], ['big-cock', 'Big Cock'], ['big-tits', 'Big Tits'], ['bikini', 'Bikini'], ['blonde', 'Blonde'], ['blowjob', 'Blowjob'], ['brunette', 'Brunette'], ['bukkake', 'Bukkake'], ['camel-toe', 'Cameltoe'], ['car', 'Car'], ['cartoon', 'Cartoon'], ['casting', 'Casting'], ['celebrities', 'Celebrities'], ['cfnm', 'CFNM'], ['chubby', 'Chubby'], ['close-up', 'Close Up'], ['college', 'College'], ['compilation', 'Compilation'], ['couple', 'Couple'], ['creampie', 'Creampie'], ['cuckold', 'Cuckold'], ['cum-swap', 'Cum Swap'], ['cumshot', 'Cumshot'], ['deep-throat', 'Deep Throat'], ['double-penetration', 'Double Penetration'], ['emo', 'Emo'], ['erotic', 'Erotic'], ['ex-girlfriend', 'Ex-Girlfriend'], ['extreme', 'Extreme'], ['facial', 'Facial'], ['femdom', 'Femdom'], ['fetish', 'Fetish'], ['fingering', 'Fingering'], ['first-time', 'First Time'], ['fisting', 'Fisting'], ['flashing', 'Flashing'], ['flexible', 'Flexible'], ['foot', 'Foot'], ['funny', 'Funny'], ['gangbang', 'GangBang'], ['gaping', 'Gaping'], ['glamour', 'Glamour'], ['glasses', 'Glasses'], ['glory-hole', 'Glory Hole'], ['gothic', 'Gothic'], ['granny', 'Granny'], ['group', 'Group'], ['hairy', 'Hairy'], ['handjob', 'Handjob'], ['hardcore', 'Hardcore'], ['hentai', 'Hentai'], ['high-heels', 'High Heels'], ['homemade', 'Homemade'], ['insertion', 'Insertion'], ['interracial', 'Interracial'], ['kissing', 'Kissing'], ['latex', 'Latex'], ['lesbian', 'Lesbian'], ['lick', 'Lick'], ['lingerie', 'Lingerie'], ['machines', 'Machines'], ['maid', 'Maid'], ['massage', 'Massage'], ['masturbation', 'Masturbation'], ['mature', 'Mature'], ['medical', 'Medical'], ['milf', 'Milf'], ['nipples', 'Nipples'], ['nurse', 'Nurse'], ['nylon', 'Nylon'], ['office', 'Office'], ['old-with-young', 'Old With Girls'], ['orgy', 'Orgy'], ['outdoor', 'Outdoor'], ['panties', 'Panties'], ['pantyhose', 'Pantyhose'], ['party', 'Party'], ['piercing', 'Piercing'], ['pissing', 'Pissing'], ['pool', 'Pool'], ['pornstar', 'Pornstar'], ['pov', 'POV'], ['pregnant', 'Pregnant'], ['public', 'Public'], ['pussy', 'Pussy'], ['reality', 'Reality'], ['redhead', 'Redhead'], ['rimming', 'Rimming'], ['romantic', 'Romantic'], ['russian', 'Russian'], ['schoolgirl', 'Schoolgirl'], ['secretary', 'Secretary'], ['shaved', 'Shaved'], ['shemale', 'Shemale'], ['skinny', 'Skinny'], ['small-tits', 'Small Tits'], ['smoking', 'Smoking'], ['softcore', 'Softcore'], ['solo', 'Solo'], ['spanking', 'Spanking'], ['sport', 'Sport'], ['squirting', 'Squirting'], ['stockings', 'Stockings'], ['strapon', 'Strapon'], ['striptease', 'Striptease'], ['swallow', 'Swallow'], ['swingers', 'Swingers'], ['tattoo', 'Tattoo'], ['teacher', 'Teacher'], ['teen', 'Teen'], ['threesome', 'Threesome'], ['titfuck', 'Titfuck'], ['tits', 'Tits'], ['toys', 'Toys'], ['ugly', 'Ugly'], ['uniform', 'Uniform'], ['upskirt', 'Upskirt'], ['vintage', 'Vintage'], ['voyeur', 'Voyeur'], ['webcam', 'Webcam'], ['wife', 'Wife'], ['wrestling', 'Wrestling']]
CLASS_NAME = dict(CLASSES)
SORTS = [["popular", "最热"], ["longest", "最长"], ["newest", "最新"]]
_PACE = {"t": 0.0}
_INFO_CACHE = {}


class _Blocked(Exception):
    pass


def _is_challenge(text):
    if not text or len(text) > 8000:
        return False
    low = text.lower()
    return ("just a moment" in low or "cf_chl_opt" in low or "challenge-platform" in low
            or "challenges.cloudflare.com" in low or "attention required" in low)


def _fix_moji(text):
    s = str(text or "")
    if "ã" not in s and "â" not in s and "æ" not in s and "ç" not in s:
        return s
    try:
        buf = bytearray()
        for ch in s:
            o = ord(ch)
            if o < 256:
                buf.append(o)
            else:
                buf.extend(ch.encode("cp1252"))
        fixed = bytes(buf).decode("utf-8")
    except Exception:
        return s
    if "�" in fixed:
        return s
    return fixed


def _decode_g(g):
    try:
        g = urllib.parse.unquote(str(g or ""))
        r = g[::-1]
        pad = (-len(r)) % 4
        dec = base64.b64decode(r + "=" * pad).decode("utf-8", "replace")
        m = re.search(r"viewkey=([A-Za-z0-9]+)", dec)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _parse_cards(html):
    items = []
    if not html:
        return items
    seen = set()
    pat = re.compile(r"<li><div><span>([^<]*)</span><a href=\"([^\"]+)\"[^>]*><img src=\"([^\"]+)\"[^>]*/></a><p>(.*?)</p></div></li>", re.S)
    for m in pat.finditer(html):
        dur, href, pic, title = m.groups()
        vk = ""
        mv = re.search(r"[?&]viewkey=([A-Za-z0-9]+)", href)
        if mv:
            vk = mv.group(1)
        elif "g=" in href:
            mg = re.search(r"[?&]g=([^&]+)", href)
            if mg:
                vk = _decode_g(mg.group(1))
        if not vk or vk in seen:
            continue
        seen.add(vk)
        if pic.startswith("//"):
            pic = "https:" + pic
        items.append({
            "vod_id": vk,
            "vod_name": _unescape(re.sub(r"<[^>]+>", "", title)).strip(),
            "vod_pic": pic,
            "vod_remarks": dur.strip(),
        })
    return items


def _fmt_dur(sec):
    try:
        sec = int(sec)
    except Exception:
        return ""
    if sec <= 0:
        return ""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)


class Spider(_BaseSpider):
    def __init__(self):
        self.ua = UA
        self.cookie = ""

    def getName(self):
        return BRAND_NAME

    def init(self, extend=""):
        cfg = extend
        if isinstance(cfg, str) and cfg.strip().startswith("{"):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        if isinstance(cfg, str) and "cf_clearance" in cfg:
            cfg = {"cookie": cfg}
        if isinstance(cfg, dict):
            ticket = {}
            tickets = cfg.get("tickets")
            if isinstance(tickets, dict):
                ticket = tickets.get(HOST) or tickets.get("www." + HOST) or {}
            if not ticket and (cfg.get("cookie") or cfg.get("ua")):
                ticket = cfg
            if isinstance(ticket, dict):
                if ticket.get("ua"):
                    self.ua = str(ticket.get("ua"))
                if ticket.get("cookie"):
                    self.cookie = str(ticket.get("cookie"))
        return None

    def _fetch(self, url, timeout=25):
        headers = {"User-Agent": self.ua or UA,
                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                   "Accept-Language": "en-US,en;q=0.9",
                   "Referer": BASE + "/"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        last = None
        for attempt in range(3):
            wait = 1.0 - (time.time() - _PACE["t"])
            if wait > 0:
                time.sleep(wait)
            _PACE["t"] = time.time()
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                text = raw.decode("utf-8", "replace")
                if _is_challenge(text):
                    raise _Blocked(url)
                return text
            except _Blocked:
                raise
            except urllib.error.HTTPError as e:
                try:
                    err_raw = e.read()
                except Exception as read_err:
                    err_raw = getattr(read_err, "partial", b"") or b""
                if _is_challenge(err_raw.decode("utf-8", "replace")):
                    raise _Blocked(url)
                last = e
            except Exception as e:
                partial = getattr(e, "partial", None)
                if partial:
                    try:
                        text = partial.decode("utf-8", "replace")
                    except Exception:
                        text = ""
                    if text and _is_challenge(text):
                        raise _Blocked(url)
                    if text and len(text) > 8000:
                        return text
                last = e
            if attempt < 2:
                time.sleep(0.8 + attempt * 0.8)
        if last is not None:
            raise last
        return ""

    def _detail_info(self, vk):
        hit = _INFO_CACHE.get(vk)
        if hit:
            return hit
        url = "%s/?viewkey=%s" % (BASE, vk)
        html = self._fetch(url)
        info = {"vk": vk, "url": url, "src": "", "embed": "", "title": "", "pic": "", "dur": "", "desc": ""}
        mh = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if mh:
            info["title"] = _fix_moji(_unescape(re.sub(r"<[^>]+>", "", mh.group(1)))).strip()
        if not info["title"]:
            mt = re.search(r"<title>([^<]*)</title>", html)
            if mt:
                info["title"] = _fix_moji(_unescape(mt.group(1))).strip()
        mp = re.search(r"poster=\"([^\"]+)\"", html)
        if mp:
            pic = mp.group(1)
            info["pic"] = "https:" + pic if pic.startswith("//") else pic
        md = re.search(r"knownDuration:(\d+)", html)
        if md:
            info["dur"] = _fmt_dur(md.group(1))
        mdesc = re.search(r"<meta name=\"description\" content=\"([^\"]*)\"", html)
        if mdesc:
            info["desc"] = _fix_moji(_unescape(mdesc.group(1))).strip()
        ms = re.search(r"<source src=\"([^\"]+)\"", html)
        if ms:
            info["src"] = _unescape(ms.group(1))
        else:
            me = re.search(r"<iframe src='(/embed/[^']+)'", html)
            if not me:
                me = re.search(r"<iframe src=\"(/embed/[^\"]+)\"", html)
            if me:
                info["embed"] = BASE + _unescape(me.group(1))
        _INFO_CACHE[vk] = info
        return info

    def homeContent(self, filter=False):
        classes = [{"type_id": slug, "type_name": name} for slug, name in CLASSES]
        filters = {}
        for slug, name in CLASSES:
            filters[slug] = [{"key": "sort", "name": "排序",
                              "value": [{"n": n, "v": v} for v, n in SORTS]}]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            html = self._fetch(BASE + "/")
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        return {"list": _parse_cards(html)}

    def _sort_of(self, filter, extend):
        sort = ""
        for src in (filter, extend):
            if isinstance(src, dict) and src.get("sort"):
                sort = str(src.get("sort"))
                break
            if isinstance(src, str) and src.strip().startswith("{"):
                try:
                    d = json.loads(src)
                except Exception:
                    d = {}
                if isinstance(d, dict) and d.get("sort"):
                    sort = str(d.get("sort"))
                    break
        if sort not in ("popular", "longest", "newest"):
            sort = "popular"
        return sort

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        slug = str(tid or "asian")
        if slug not in CLASS_NAME:
            slug = "asian"
        sort = self._sort_of(filter, extend)
        sub = "" if sort == "popular" else sort + "-videos/"
        url = "%s/%s/%s" % (BASE, slug, sub)
        try:
            html = self._fetch(url)
        except _Blocked:
            return {"list": [], "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": 0, "msg": BLOCK_MSG}
        cards = _parse_cards(html)
        total = len(cards)
        if pg != 1:
            cards = []
        return {"list": cards, "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": total}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = "%s/?k=%s" % (BASE, urllib.parse.quote_plus(str(key or "")))
        if pg > 1:
            url += "&page=%d" % pg
        try:
            html = self._fetch(url)
        except _Blocked:
            return {"list": [], "page": pg, "pagecount": 1, "limit": SEARCH_PAGE, "total": 0, "msg": BLOCK_MSG}
        cards = _parse_cards(html)
        pc = pg
        for m in re.finditer(r"[?&]page=(\d+)", html):
            try:
                v = int(m.group(1))
            except Exception:
                continue
            if v > pc:
                pc = v
        if not cards:
            pc = max(1, pg - 1) if pg > 1 else 1
        if pg >= pc:
            total = (pc - 1) * SEARCH_PAGE + len(cards)
        else:
            total = pc * SEARCH_PAGE
        return {"list": cards, "page": pg, "pagecount": pc, "limit": SEARCH_PAGE, "total": total}

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        vk = str(raw or "").strip()
        mv = re.search(r"viewkey=([A-Za-z0-9]+)", vk)
        if mv:
            vk = mv.group(1)
        try:
            info = self._detail_info(vk)
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        desc = info.get("desc") or info.get("title") or ""
        content = "%s\n%s\n%s\n%s\n%s%s\n%s" % (NODE_LINE, DIVIDER_THICK, BRAND_ACTOR, DIVIDER_THIN, MARKER, desc, SYNOPSIS_GROUP)
        vod = {
            "vod_id": vk,
            "vod_name": info.get("title") or vk,
            "vod_pic": info.get("pic") or "",
            "vod_remarks": info.get("dur") or "",
            "vod_actor": BRAND_ACTOR,
            "vod_director": BRAND_DIRECTOR,
            "vod_content": content,
            "vod_play_from": LINE_NAME,
            "vod_play_url": "正片$%s" % vk,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        vk = str(id or "").strip()
        mv = re.search(r"viewkey=([A-Za-z0-9]+)", vk)
        if mv:
            vk = mv.group(1)
        try:
            info = self._detail_info(vk)
        except _Blocked:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "msg": BLOCK_MSG}
        except Exception:
            info = None
        header = {"User-Agent": UA, "Referer": BASE + "/"}
        if info and info.get("src"):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": info["src"], "header": header}
        if info and info.get("embed"):
            return {"parse": 1, "jx": 0, "playUrl": "", "url": info["embed"], "header": header}
        return {"parse": 1, "jx": 0, "playUrl": "", "url": "%s/?viewkey=%s" % (BASE, vk),
                "header": header, "msg": "未取到播放地址，站点可能已改版或该片已下架"}

    def isVideoFormat(self, url):
        u = str(url or "")
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False
