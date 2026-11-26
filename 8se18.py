import base64
import html as _html
import json
import threading
import re
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
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
LINE_NAME_ALT = "🦋 蝴蝶专线·直连"
BASE = "https://8se.me"
NODE_LINE = "当前节点：https://8se.me"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
IMG_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
IMG_REF = "https://8se.me/"
PAGE_SIZE = 12
DETAIL_PAGE_CAP = 60
TICKET_TTL = 1200
BLOCK_MSG = "8se.me 被 Cloudflare 人机校验拦截，请在 extend 传入你浏览器里的票据后重试，例如 {\"tickets\": {\"8se.me\": {\"cookie\": \"cf_clearance=...\", \"ua\": \"浏览器UA\"}}}；票据与获取它的网络和浏览器绑定，换网络需重新获取"
SERIES = [
    ("series-6443d480eb757", "AI图区", 0),
    ("series-6310ce9b90056", "PANS", 2027),
    ("series-665f8bafab4bc", "黄甫", 181),
    ("series-64f44d99ce673", "行色", 148),
    ("series-665f7d787d681", "其他中国工作室", 150),
    ("series-5f1dcdeaee582", "相约中国", 381),
    ("series-6666a7ac3ba9c", "风吟鸟唱", 82),
    ("series-665f8595408fa", "希威社", 47),
    ("series-5f1d784995865", "丽图100", 537),
    ("series-5f14a5eb5b0d7", "推女郎", 87),
    ("series-67028a27d02a6", "U238", 17),
    ("series-5f1ae6caae922", "轰趴猫", 264),
    ("series-5f60b98248a81", "A4U", 49),
    ("series-5f15f389e993e", "爱丝", 132),
    ("series-5f23c44cd66bd", "潘多拉", 201),
    ("series-646c69b675f3d", "ISS系列", 41),
    ("series-638e5a60b1770", "深夜企划", 46),
    ("series-5f2089564c6c2", "蜜丝", 74),
    ("series-676c3e9b90749", "蜜柚摄影", 29),
    ("series-5f382ba894af4", "SK丝库", 22),
    ("series-619a92aa1fa7a", "无忌影社", 90),
    ("series-5f4b5f4eb8b71", "妖精社", 99),
    ("series-5f14806585bef", "头条女神", 53),
    ("series-5f148046cb2c7", "爱尤物", 133),
    ("series-622c7f95220a4", "北京天使", 41),
    ("series-5f15f727df393", "DDY", 28),
    ("series-5f22ea422221c", "东莞V女郎", 26),
    ("series-5f1817b42772b", "果团网", 132),
    ("series-61b997728043b", "尤美", 38),
    ("series-64be21c972ca4", "国模套图", 6036),
    ("series-64be22b4a0fa0", "韩模套图", 398),
    ("series-64be2283bf3af", "日模套图", 555),
    ("series-64be21ef4cc51", "台模套图", 264),
    ("series-64be224b662c0", "港模套图", 64),
    ("series-64be239ce73d4", "其他地区套图", 28),
    ("series-66600a3a227ee", "私购流出", 691),
    ("series-5f1476781eab4", "秀人网", 11031),
    ("series-601ef80997845", "语画界", 750),
    ("series-5f184ff551888", "尤蜜荟", 594),
    ("series-5f71afc92d8ab", "爱蜜社", 742),
    ("series-5f181625966a6", "模范学院", 568),
    ("series-5fc4ce40386af", "花漾", 631),
    ("series-6141c88882a36", "星颜社", 310),
    ("series-5f1495dbda4de", "美媛馆", 504),
    ("series-5f1dd5a7ebe9a", "蜜桃社", 149),
    ("series-60673bec9dd11", "尤物馆", 175),
    ("series-5f14a3105d3e8", "FEILIN嗲囡囡", 125),
    ("series-61263de287e2f", "瑞丝馆", 88),
    ("series-63d435352808c", "影私荟", 22),
    ("series-6224e755e21f4", "Pure Media", 147),
    ("series-60a4a953ca563", "ArtGravia", 201),
    ("series-665f81885f103", "Makemodel", 106),
    ("series-665a2385a2367", "Espacia Korea", 42),
    ("series-62888afad416b", "Loozy", 21),
    ("series-6692ea004cc75", "Urabon", 90),
    ("series-6450b47c9db0b", "Graphis", 246),
    ("series-62a0a15911f16", "Super Pose Book", 44),
    ("series-66659e2d94489", "FRIDAY", 93),
    ("series-66e68b9c96ab0", "周刊ポストデジタル写真集", 46),
    ("series-66fb8cca706ae", "X-City", 30),
    ("series-670791f5f2f0f", "Prestige", 62),
    ("series-66603af933ec9", "Escape", 56),
    ("series-670d7142b3d88", "アサ芸SEXY", 32),
    ("series-672a2029d6a32", "FLASHデジタル写真集", 10),
    ("series-637b2029d2347", "JVID", 435),
    ("series-68610041d0aa8", "ED Mosaic", 17),
    ("series-5f889afb37619", "Fantasy Factory", 43),
    ("series-5f7a0a80d3d66", "TPimage", 23),
    ("series-6860e3d718c78", "书籍扫描", 555),
    ("series-6836cd1a2d51d", "街拍", 241),
]
TAGS = [
    ("tag-pussy-visible", "露底"),
    ("tag-interaction", "互动"),
    ("tag-sex", "性爱"),
    ("tag-exposure", "露出"),
    ("tag-stockings", "丝袜"),
    ("tag-lingerie", "情趣内衣"),
    ("tag-props", "道具"),
    ("tag-shaved", "白虎"),
    ("tag-bondage", "捆绑"),
    ("tag-lesbian", "女同"),
    ("tag-cosplay", "Cosplay"),
    ("tag-maid", "女仆"),
    ("tag-jk", "JK"),
    ("tag-ol", "OL"),
    ("tag-ancient", "古装"),
    ("tag-nurse", "护士"),
    ("tag-police", "警察"),
    ("tag-bunny-girl", "兔女郎"),
    ("tag-air-hostess", "空姐"),
    ("tag-teacher", "教师"),
    ("tag-one-piece-swimsuit", "连体泳装"),
    ("tag-fishnet", "渔网袜"),
    ("tag-garter", "吊袜带"),
    ("tag-pantyhose", "连裤袜"),
    ("tag-white-stockings", "白丝袜"),
    ("tag-black-stockings", "黑丝袜"),
    ("tag-color-stockings", "彩色丝袜"),
    ("tag-high-heels", "高跟鞋"),
    ("tag-outdoor", "户外"),
    ("tag-bathroom", "浴室"),
    ("tag-car", "车内"),
    ("tag-classroom", "教室"),
    ("tag-wedding-dress", "婚纱"),
    ("tag-bikini", "比基尼"),
    ("tag-cheongsam", "旗袍"),
    ("tag-spreading", "掰穴"),
    ("tag-peeing", "放尿"),
]
_CLASSES = [("all", "全部套图")] + [(t, n) for t, n, c in SERIES] + [(t, n) for t, n in TAGS]
_SERIES_COUNT = {}
for _t, _n, _c in SERIES:
    _SERIES_COUNT[_t] = _c
_TICKETS = {}
_IMG_CACHE = {}
_IMG_BYTES = {}
_IMG_BYTES_MAX = 12
_IMG_LOCK = threading.Lock()
IMG_RETRY = 4


class _Blocked(Exception):
    pass


def _host_of(url):
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


def _ticket_for(url):
    host = _host_of(url)
    t = _TICKETS.get(host)
    if not t:
        return None
    if t.get("issued") and time.time() - t["issued"] > TICKET_TTL:
        return None
    return t


def _is_challenge(text):
    if not text or len(text) > 8000:
        return False
    low = text.lower()
    for mark in ("just a moment", "cf_chl", "challenge-platform", "challenges.cloudflare.com", "attention required"):
        if mark in low:
            return True
    return False


def _html_headers(url):
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "zh-CN,zh;q=0.9"}
    t = _ticket_for(url)
    if t:
        if t.get("ua"):
            headers["User-Agent"] = t["ua"]
        if t.get("cookie"):
            headers["Cookie"] = t["cookie"]
    return headers


def _fetch(url, timeout=25):
    headers = _html_headers(url)
    last_err = None
    raw = b""
    for _attempt in range(3):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            last_err = None
            break
        except urllib.error.HTTPError as e:
            try:
                err_raw = e.read()
            except Exception as read_err:
                err_raw = getattr(read_err, "partial", b"") or b""
            if _is_challenge(err_raw.decode("utf-8", "replace")):
                raise _Blocked(url)
            raise
        except Exception as net_err:
            partial = getattr(net_err, "partial", b"") or b""
            if partial and _is_challenge(partial.decode("utf-8", "replace")):
                raise _Blocked(url)
            last_err = net_err
            time.sleep(0.5 + _attempt * 0.5)
    if last_err is not None:
        raise last_err
    text = raw.decode("utf-8", "replace")
    if _is_challenge(text):
        raise _Blocked(url)
    return text


def _img_headers(url, referer=""):
    headers = {
        "User-Agent": IMG_UA,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer or IMG_REF,
    }
    t = _ticket_for(url)
    if t:
        if t.get("ua"):
            headers["User-Agent"] = t["ua"]
        if t.get("cookie"):
            headers["Cookie"] = t["cookie"]
    return headers


def _fetch_bytes(url, timeout=25, referer=""):
    last_err = None
    with _IMG_LOCK:
        for attempt in range(IMG_RETRY):
            req = urllib.request.Request(url, headers=_img_headers(url, referer))
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read(), resp.headers.get_content_type() or "image/jpeg"
            except urllib.error.HTTPError as e:
                try:
                    err_raw = e.read()
                except Exception as read_err:
                    err_raw = getattr(read_err, "partial", b"") or b""
                challenged = _is_challenge(err_raw.decode("utf-8", "replace"))
                last_err = _Blocked(url) if challenged else e
                if challenged or e.code in (403, 429, 503):
                    if attempt < IMG_RETRY - 1:
                        time.sleep(1.0 + attempt * 1.2)
                        continue
                    if challenged:
                        raise _Blocked(url)
                raise
            except Exception as net_err:
                last_err = net_err
                if attempt < IMG_RETRY - 1:
                    time.sleep(0.8 + attempt * 0.8)
                    continue
        raise last_err


def _b64e(text):
    return base64.urlsafe_b64encode(str(text).encode("utf-8")).decode("ascii").rstrip("=")


def _b64d(token):
    token = str(token or "").strip()
    token = token.replace("-", "+").replace("_", "/")
    pad = (-len(token)) % 4
    try:
        return base64.b64decode(token + "=" * pad).decode("utf-8", "replace")
    except Exception:
        return ""


def _gallery_id(mode, pid):
    return "%s|%s" % (mode, pid)


def _split_mid(mid):
    s = str(mid or "").strip()
    if s.startswith("http"):
        m = re.search(r"id-([a-z0-9]+)", s)
        return "px", (m.group(1) if m else s)
    if "|" in s:
        a, b = s.split("|", 1)
        return (a or "px"), b
    return "px", s


def _pagecount(html):
    nums = [int(x) for x in re.findall(r'class="pager-num[^"]*">(\d+)<', html)]
    if nums:
        return max(nums)
    return 1


def _parse_cards(html):
    out = []
    seen = set()
    blocks = re.split(r'<div class="item photo">', html)
    for block in blocks[1:]:
        m = re.search(r'href="https://8se\.me/photo/id-([a-z0-9]+)\.html" title="([^"]*)"', block)
        if not m:
            m = re.search(r'href="(?:https://8se\.me)?/photo/id-([a-z0-9]+)\.html" title="([^"]*)"', block)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        title = _html.unescape(m.group(2).strip())
        pic = ""
        mi = re.search(r"background-image:url\('([^']+)'\)", block)
        if mi:
            pic = mi.group(1)
        remarks = ""
        mp = re.search(r"(\d+)\s*P\b", block)
        if mp:
            remarks = mp.group(1) + "P"
        out.append({"vod_id": pid, "vod_name": title, "vod_pic": pic, "vod_remarks": remarks})
    return out


def _list_url(tid, pg):
    if tid == "all":
        return "%s/photos/%d.html" % (BASE, pg)
    if tid.startswith("series-"):
        return "%s/photos/%s/%d.html" % (BASE, tid, pg)
    if tid.startswith("tag-"):
        slug = tid[4:]
        if pg <= 1:
            return "%s/photos/tag/%s" % (BASE, slug)
        return "%s/photos/tag/%s/%d.html" % (BASE, slug, pg)
    return "%s/photos/%d.html" % (BASE, pg)


def _empty_result(pg, msg=None):
    r = {"list": [], "page": int(pg), "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
    if msg:
        r["msg"] = msg
    return r


class Spider(_BaseSpider):
    def getName(self):
        return BRAND_NAME

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                if "cf_clearance" in extend or "=" in extend:
                    cfg = {"cookie": extend}
        if not isinstance(cfg, dict):
            cfg = {}
        tickets = {}
        if isinstance(cfg.get("tickets"), dict):
            for host, t in cfg["tickets"].items():
                if isinstance(t, dict) and t.get("cookie"):
                    tickets[str(host)] = {"cookie": t.get("cookie") or "", "ua": t.get("ua") or "", "issued": 0}
        if cfg.get("cookie"):
            tickets["8se.me"] = {"cookie": cfg.get("cookie") or "", "ua": cfg.get("ua") or "", "issued": 0}
        if cfg.get("img_cookie"):
            tickets["img.xchina.io"] = {"cookie": cfg.get("img_cookie") or "", "ua": cfg.get("img_ua") or "", "issued": 0}
        _TICKETS.update(tickets)
        return True

    def _proxy(self, url, referer=""):
        url = str(url or "").strip()
        if not url.startswith("http"):
            return url
        try:
            base = self.getProxyUrl()
        except Exception:
            return url
        if not base:
            return url
        sep = "&" if "?" in base else "?"
        q = "u=" + _b64e(url)
        if referer:
            q += "&r=" + _b64e(referer)
        return base + sep + q

    def _decorate(self, cards):
        for c in cards:
            if c.get("vod_pic"):
                c["vod_pic"] = self._proxy(c["vod_pic"], IMG_REF)
        return cards

    def localProxy(self, param):
        p = param if isinstance(param, dict) else {}
        if not isinstance(p, dict):
            p = {}
        raw = p.get("u") or p.get("url") or ""
        url = _b64d(raw) if raw and "://" not in str(raw) else str(raw)
        referer = _b64d(p.get("r") or "") or IMG_REF
        if not url.startswith("http"):
            return [400, "text/plain", b"bad image url"]
        hit = _IMG_BYTES.pop(url, None)
        if hit:
            _IMG_BYTES[url] = hit
            return [200, hit[0], hit[1]]
        try:
            body, mime = _fetch_bytes(url, referer=referer)
        except _Blocked:
            return [403, "text/plain", b"cloudflare blocked, refresh ticket"]
        except Exception:
            return [502, "text/plain", b"upstream error"]
        if not body:
            return [502, "text/plain", b"empty body"]
        if not mime or mime == "application/octet-stream":
            if body[:3] == b"\xff\xd8\xff":
                mime = "image/jpeg"
            elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
                mime = "image/webp"
            elif body[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            else:
                mime = "image/jpeg"
        if len(_IMG_BYTES) >= _IMG_BYTES_MAX:
            try:
                _IMG_BYTES.pop(next(iter(_IMG_BYTES)))
            except Exception:
                pass
        _IMG_BYTES[url] = (mime, body)
        return [200, mime, body]

    def homeContent(self, filter=False):
        classes = [{"type_id": t, "type_name": n} for t, n in _CLASSES]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        try:
            html = _fetch(_list_url("all", 1))
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception:
            return {"list": []}
        return {"list": self._decorate(_parse_cards(html))}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        try:
            html = _fetch(_list_url(str(tid), pg))
        except _Blocked:
            return _empty_result(pg, BLOCK_MSG)
        except Exception:
            return _empty_result(pg)
        cards = _parse_cards(html)
        pc = _pagecount(html)
        if not cards:
            pc = pg
        total = _SERIES_COUNT.get(str(tid), 0)
        if not total:
            total = pc * PAGE_SIZE if cards else 0
        return {"list": self._decorate(cards), "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": total}

    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        url = "%s/search.html?keyword=%s" % (BASE, urllib.parse.quote(str(key)))
        if pg > 1:
            url = url + "&page=%d" % pg
        try:
            html = _fetch(url)
        except _Blocked:
            return _empty_result(pg, BLOCK_MSG)
        except Exception:
            return _empty_result(pg)
        cards = _parse_cards(html)
        pc = _pagecount(html) if cards else pg
        return {"list": self._decorate(cards), "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": pc * PAGE_SIZE if cards else 0}

    def _collect_images(self, pid, first_html=None):
        hit = _IMG_CACHE.get(pid)
        if hit and hit[1] and time.time() - hit[0] < 1800:
            return hit[1]
        try:
            html = first_html if first_html is not None else _fetch("%s/photo/id-%s/1.html" % (BASE, pid))
        except _Blocked:
            raise
        total_p = 0
        mp = re.search(r"(\d+)\s*P\b", html)
        if mp:
            total_p = int(mp.group(1))
        images = []
        seen = set()

        def _get(page_html):
            for m in re.finditer(r"img\.xchina\.io/(photos\d*)/%s/(\d+)_600x0\.webp" % re.escape(pid), page_html):
                folder = m.group(1)
                num = m.group(2)
                key = folder + "/" + num
                if key in seen:
                    continue
                seen.add(key)
                images.append("https://img.xchina.io/%s/%s/%s.jpg" % (folder, pid, num))

        _get(html)
        pc = _pagecount(html)
        last = pc
        if total_p:
            last = max(last, (total_p + 17) // 18)
        last = min(last, DETAIL_PAGE_CAP)
        for pno in range(2, last + 1):
            try:
                _get(_fetch("%s/photo/id-%s/%d.html" % (BASE, pid, pno)))
            except _Blocked:
                break
            except Exception:
                break
        images.sort(key=lambda u: int((re.search(r"/(\d+)\.jpg$", u) or [0, 0])[1]))
        if images:
            _IMG_CACHE[pid] = (time.time(), images)
        return images

    def detailContent(self, ids):
        pid = ids[0] if isinstance(ids, (list, tuple)) else ids
        pid = str(pid).strip()
        if pid.startswith("http"):
            m = re.search(r"id-([a-z0-9]+)", pid)
            pid = m.group(1) if m else pid
        page_url = "%s/photo/id-%s/1.html" % (BASE, pid)
        try:
            html = _fetch(page_url)
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception:
            return {"list": []}
        title = ""
        mt = re.search(r'og:title" content="([^"]+)"', html)
        if mt:
            title = _html.unescape(mt.group(1).strip())
        if not title:
            mt = re.search(r"<title>([^<]*)</title>", html)
            if mt:
                title = re.sub(r"\s*-\s*8色人体摄影\s*$", "", mt.group(1)).strip()
        total_p = 0
        mp = re.search(r"(\d+)\s*P\b", html)
        if mp:
            total_p = int(mp.group(1))
        series_names = []
        for m in re.finditer(r'href="https://8se\.me/photos/series-[a-z0-9]+\.html"[^>]*>([^<]+)</a>', html):
            nm = m.group(1).strip()
            if nm and nm not in series_names:
                series_names.append(nm)
        tag_names = []
        for m in re.finditer(r'href="https://8se\.me/photos/tag/[a-z0-9-]+"[^>]*>([^<]+)</a>', html):
            nm = m.group(1).strip()
            if nm and nm not in tag_names:
                tag_names.append(nm)
        try:
            images = self._collect_images(pid, first_html=html)
        except _Blocked:
            return {"list": [], "msg": BLOCK_MSG}
        except Exception:
            images = []
        cover = ""
        if images:
            cover = images[0].replace(".jpg", "_600x0.webp")
        info_lines = []
        if series_names:
            info_lines.append("系列：" + " / ".join(series_names[:3]))
        if tag_names:
            info_lines.append("标签：" + " ".join(tag_names[:8]))
        if total_p:
            info_lines.append("共 %d 张" % total_p)
        if images:
            info_lines.append("已解析 %d 张，点播放直接翻图（左右滑）" % len(images))
        info_lines.append(NODE_LINE)
        content = "\n".join(info_lines) + "\n" + DIVIDER_THIN + "\n" + MARKER + "\n" + (title or "") + "\n" + SYNOPSIS_GROUP
        play_url = "全集$%s" % _gallery_id("px", pid) + "$$$" + "全集$%s" % _gallery_id("dir", pid)
        play_from = LINE_NAME + "$$$" + LINE_NAME_ALT
        # 单张线路（WebHomeTV 兜底）：每集一张直链图，不依赖 pics://
        single_url = "#".join("第{}张$img:{}:{}".format(i + 1, pid, i) for i in range(len(images)))
        if single_url:
            play_url = play_url + "$$$" + single_url
            play_from = play_from + "$$$单张"
        vod = {
            "vod_id": pid,
            "vod_name": title,
            "vod_pic": self._proxy(cover, IMG_REF) if cover else "",
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": BRAND_DIRECTOR,
            "vod_content": content,
            "vod_remarks": ("%dP" % total_p) if total_p else "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        mid = str(id or "").strip()
        # 单张：img:<pid>:<idx> -> 直接返回那一张图的直链地址
        if mid.startswith("img:"):
            parts = mid.split(":")
            pid = parts[1] if len(parts) > 1 else ""
            try:
                idx = int(parts[2]) if len(parts) > 2 else 0
            except Exception:
                idx = 0
            try:
                imgs = self._collect_images(pid)
            except _Blocked:
                return {"parse": 0, "url": "", "msg": BLOCK_MSG}
            except Exception:
                return {"parse": 0, "url": "", "msg": "取图失败：%s" % pid}
            if not imgs or idx >= len(imgs):
                return {"parse": 0, "url": "", "msg": "没有解析到图片"}
            return {"parse": 0, "url": imgs[idx],
                    "header": {"User-Agent": IMG_UA, "Referer": IMG_REF}}
        if mid.startswith("http") and "img.xchina.io" in mid:
            imgs = [mid]
            mode = "dir"
            pid = ""
        else:
            mode, pid = _split_mid(mid)
            try:
                imgs = self._collect_images(pid)
            except _Blocked:
                return {"parse": 0, "url": "", "msg": BLOCK_MSG}
            except Exception:
                return {"parse": 0, "url": "", "msg": "取图失败：%s" % pid}
        if not imgs:
            return {"parse": 0, "url": "", "msg": "没有解析到图片"}
        headers = {"User-Agent": IMG_UA, "Referer": IMG_REF}
        if mode == "dir":
            urls = list(imgs)
        else:
            urls = [self._proxy(u, IMG_REF) for u in imgs]
        return {"parse": 0, "url": "pics://" + "&&".join(urls), "header": headers}

    def isVideoFormat(self, url):
        u = str(url or "")
        return u.startswith("pics://") or ".jpg" in u or ".webp" in u or ".png" in u or ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False
