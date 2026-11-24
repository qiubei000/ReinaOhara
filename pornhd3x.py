#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PornHD3X (https://www9.pornhd3x.tv) -> PeekPro 接口脚本
=====================================================

站点是一套自建 CMS (ASP.NET) 的欧美片库:
    列表    /premium-porn-hd/page-N     40 条/页
    分类    /category/{slug}/page-N
    工作室  /studio/{slug}/page-N
    女优    /pornstar/{slug}/page-N
    标签    /tag/{slug}/page-N
    搜索    /search/{kw}/page-N
    详情    /movies/{slug}
    播放    /ajax/get_sources/{episode}/{hash}  -> m3u8

播放链路(页面脚本里那套签名, 已还原):
    1. 详情页取 episode-id
    2. 生成 6 位随机串 r
    3. cookie:  <盐[13:37]> + episode + <盐[40:64]>  =  r
    4. hash = md5(episode + r + 盐串)
    5. GET /ajax/get_sources/{episode}/{hash}?count=1&mobile=false
       (必须带 X-Requested-With 和上面那个 cookie, 否则返回空)

片源是 "PNG 包装的 HLS": m3u8 里的分片实际是 PNG 文件,
PNG 头(IEND)之后跟一段填充, 再往后就是标准 MPEG-TS(720p h264+aac)。
本脚本内置本地代理, 实时把分片解包成 TS, 播放器直接播就行。

两种用法:

1) 当 PeekPro 的 py 接口脚本导入
   对外暴露 class Spider(homeContent / categoryContent / detailContent /
   searchContent / playerContent ...) + 同名模块级函数 + main(action, *args)

2) 本地起服务, 走 HTTPS 接口(标准 CMS 协议)
   python3 pornhd3x_peekpro.py serve --port 8899
   接口地址: http://<ip>:8899/api.php/provide/vod/

零第三方依赖, 纯标准库。
"""

import base64
import hashlib
import html as htmlmod
import http.cookiejar
import json
import random
import re
import socket
import string
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ================================================================ 基础配置

HOSTS = [
    "https://www9.pornhd3x.tv",
    "https://www.pornhd3x.tv",
    "https://www3.pornhd3x.tv",
    "https://pornhd3x.tv",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

PAGE_SIZE = 40
PLAY_FROM = "PornHD3X"

# 详情页脚本里的播放签名素材
SALT = "98126avrbi6m49vd7shxkn985"
THFQ = ("n1sqcua67bcq9826avrbi6m49vd7shxkn985mhodk06twz87wwxtp3dqiicks2dfyud2"
        "13k6ygiomq01s94e4tr9v0k887bkyud213k6ygiomq01s94e4tr9v0k887bkqocxzw39e"
        "sdyfhvtkpzq9n4e7at4kc6k8sxom08bl4dukp16h09oplu7zov4m5f8")
COOKIE_PREFIX = THFQ[13:37]
COOKIE_SUFFIX = THFQ[40:64]

TAG_HOT = [
    ("pov", "POV"), ("big-tits", "Big Tits"), ("anal", "Anal"),
    ("milf", "MILF"), ("blonde", "Blonde"), ("teen", "Teen"),
    ("creampie", "Creampie"), ("bbc", "BBC"), ("threesome", "Threesome"),
    ("brunette", "Brunette"), ("interracial", "Interracial"),
    ("latina", "Latina"), ("stockings", "Stockings"), ("squirt", "Squirt"),
]
CATEGORIES = [
    ('-round-asses', 'Round Asses'),
    ('2-chicks-same-time', '2 Chicks Same Time'),
    ('8th-street-latinas', '8th Street Latinas'),
    ('after-school', 'After School'),
    ('american-daydreams', 'American Daydreams'),
    ('asian-1-on-1', 'Asian 1 On 1'),
    ('ass-masterpiece', 'Ass Masterpiece'),
    ('ass-parade', 'Ass Parade'),
    ('baby-got-boobs', 'Baby Got Boobs'),
    ('bad-girl', 'Bad Girl'),
    ('bang-bus', 'Bang Bus'),
    ('bang-pov', 'Bang POV'),
    ('bangbros-18', 'BangBros 18'),
    ('bangbros-clips', 'Bangbros Clips'),
    ('bangbros-vault', 'Bangbros Vault'),
    ('big-butts-like-it-big', 'Big Butts Like It Big'),
    ('big-cock-bully', 'Big Cock Bully'),
    ('big-naturals', 'Big Naturals'),
    ('big-tit-cream-pie', 'Big Tit Cream Pie'),
    ('big-tits-at-school', 'Big Tits at School'),
    ('big-tits-at-work', 'Big Tits at Work'),
    ('big-tits-boss', 'Big Tits Boss'),
    ('big-tits-in-sports', 'Big Tits In Sports'),
    ('big-wet-butts', 'Big Wet Butts'),
    ('blockbuster', 'Blockbuster'),
    ('blowjob-fridays', 'BlowJob Fridays'),
    ('boss', 'Boss'),
    ('boss-s-wife', "Boss's Wife"),
    ('brazzers', 'Brazzers'),
    ('brazzers-en-espanol', 'Brazzers en Español'),
    ('brazzers-exxtra', 'Brazzers Exxtra'),
    ('brazzers-live', 'Brazzers Live'),
    ('brown-bunnies', 'Brown Bunnies'),
    ('captain-stabbin', 'Captain Stabbin'),
    ('college-sugar-babes', 'College Sugar Babes'),
    ('cougar', 'Cougar'),
    ('crazy-asian-gfs', 'Crazy Asian GFs'),
    ('crazy-college-gfs', 'Crazy College GFs'),
    ('cum-fiesta', 'Cum Fiesta'),
    ('dangerous-dongs', 'Dangerous Dongs'),
    ('dare-dorm', 'Dare Dorm'),
    ('day-with-a-pornstar', 'Day With A Pornstar'),
    ('diary-of-a-milf', 'Diary of a Milf'),
    ('diary-of-a-nanny', 'Diary of a Nanny'),
    ('dirty-masseur', 'Dirty Masseur'),
    ('dirty-wives-club', 'Dirty Wives Club'),
    ('doctor-adventures', 'Doctor Adventures'),
    ('don-t-break-me', "Don't Break Me"),
    ('dp-parody', 'DP Parody'),
    ('ebony-sex-tapes', 'Ebony Sex Tapes'),
    ('episodes', 'Episodes'),
    ('euro-sex-parties', 'Euro Sex Parties'),
    ('fake-agent', 'Fake Agent'),
    ('fake-college', 'Fake College'),
    ('fake-driving-school', 'Fake Driving School'),
    ('fake-hostel', 'Fake Hostel'),
    ('fake-taxi', 'Fake Taxi'),
    ('fakehub-originals', 'Fakehub Originals'),
    ('fast-times', 'Fast Times'),
    ('female-fake-taxi', 'Female Fake Taxi'),
    ('first-time-auditions', 'First Time Auditions'),
    ('flixxx', 'Flixxx'),
    ('friend-s-girlfriend', "Friend's Girlfriend"),
    ('friend-s-mom', "Friend's Mom"),
    ('fuck-team-five', 'Fuck Team Five'),
    ('gf-leaks', 'GF Leaks'),
    ('gf-revenge', 'GF Revenge'),
    ('girlfriend', 'Girlfriend'),
    ('girlfriend-s-friend', "Girlfriend's Friend"),
    ('girls-gone-pink', 'Girls Gone Pink'),
    ('happy-tugs', 'Happy Tugs'),
    ('he-s-got-rizz', "He's Got Rizz"),
    ('hot-and-mean', 'Hot And Mean'),
    ('hot-girls-game', 'Hot Girls Game'),
    ('housewife-1-on-1', 'Housewife 1 on 1'),
    ('i-have-a-wife', 'I Have a Wife'),
    ('i-know-that-girl', 'I Know That Girl'),
    ('in-the-vip', 'In the VIP'),
    ('latin-adultery', 'Latin Adultery'),
    ('latina-sex-tapes', 'Latina Sex Tapes'),
    ('let-s-post-it', "Let's Post It"),
    ('lets-try-anal', 'Lets Try Anal'),
    ('lil-humpers', 'Lil Humpers'),
    ('look-at-her-now', 'Look At Her Now'),
    ('lpi', 'lpi'),
    ('mike-s-apartment', "Mike's Apartment"),
    ('milf-hunter', 'Milf Hunter'),
    ('milfs-like-it-big', 'Milfs Like it Big'),
    ('mofos-b-sides', 'Mofos B Sides'),
    ('mofos-lab', 'MOFOS Lab'),
    ('momishorny', 'MomIsHorny'),
    ('mommy-got-boobs', 'Mommy Got Boobs'),
    ('moms-bang-teens', 'Moms Bang Teens'),
    ('moms-in-control', 'Moms in control'),
    ('moms-lick-teens', 'Moms Lick Teens'),
    ('money-talks', 'Money Talks'),
    ('monster-curves', 'Monster Curves'),
    ('monsters-of-cock', 'Monsters of Cock'),
    ('mrs-creampie', 'Mrs. Creampie'),
    ('my-dad-s-hot-girlfriend', "My Dad's Hot Girlfriend"),
    ('my-daughter-s-hot-friend', "My Daughter's Hot Friend"),
    ('my-dirty-maid', 'My Dirty Maid'),
    ('my-first-sex-teacher', 'My First Sex Teacher'),
    ('my-friend-s-hot-girl', "My Friend's Hot Girl"),
    ('my-friend-s-hot-mom', "My Friend's Hot Mom"),
    ('my-girl-loves-anal', 'My Girl Loves Anal'),
    ('my-girlfriend-s-busty-friend', "My Girlfriend's Busty Friend"),
    ('my-naughty-latin-maid', 'My Naughty Latin Maid'),
    ('my-naughty-massage', 'My Naughty Massage'),
    ('my-sister-s-hot-friend', "My Sister's Hot Friend"),
    ('my-wife-s-hot-friend', "My Wife's Hot Friend"),
    ('naughty-america', 'Naughty America'),
    ('naughty-athletics', 'Naughty Athletics'),
    ('naughty-bookworms', 'Naughty Bookworms'),
    ('naughty-country-girls', 'Naughty Country Girls'),
    ('naughty-flipside', 'Naughty Flipside'),
    ('naughty-office', 'Naughty Office'),
    ('naughty-rich-girls', 'Naughty Rich Girls'),
    ('neighbor-affair', 'Neighbor Affair'),
    ('nubilefilms', 'NubileFilms'),
    ('perfect-fucking-strangers', 'Perfect Fucking Strangers'),
    ('pervs-on-patrol', 'Pervs On Patrol'),
    ('porn-star', 'Porn Star'),
    ('pornstars-like-it-big', 'Pornstars Like it Big'),
    ('professor', 'Professor'),
    ('public-agent', 'Public Agent'),
    ('public-bang', 'Public Bang'),
    ('public-pickups', 'Public Pickups'),
    ('pure-18', 'Pure 18'),
    ('real-wife-stories', 'Real Wife Stories'),
    ('reckless-in-miami', 'Reckless in Miami'),
    ('rk-prime', 'RK Prime'),
    ('rk-shorts', 'RK Shorts'),
    ('round-and-brown', 'Round and Brown'),
    ('seduced-by-a-cougar', 'Seduced By A Cougar'),
    ('share-my-bf', 'Share My BF'),
    ('sister-s-friend', "Sister's Friend"),
    ('sneaky-sex', 'Sneaky Sex'),
    ('stranded-teens', 'Stranded Teens'),
    ('street-blowjobs', 'Street BlowJobs'),
    ('teens-like-it-big', 'Teens Like It Big'),
    ('teens-love-huge-cocks', 'Teens Love Huge Cocks'),
    ('thundercock', 'Thundercock'),
    ('tonight-s-girlfriend', "Tonight's Girlfriend"),
    ('we-live-together', 'We Live Together'),
    ('wife', 'Wife'),
    ('wives-on-vacation', 'Wives on Vacation'),
    ('work-me-harder', 'Work Me Harder'),
    ('zz-series', 'ZZ Series'),
]

STUDIOS = [
    ('babes', 'Babes'),
    ('bang-bros', 'Bang bros'),
    ('blacked', 'Blacked'),
    ('brazzers', 'Brazzers'),
    ('digitalplayground', 'Digitalplayground'),
    ('fakehub', 'Fakehub'),
    ('horrorporn', 'Horrorporn'),
    ('mofos', 'Mofos'),
    ('mylf', 'Mylf'),
    ('naughtyamerica', 'Naughtyamerica'),
    ('netvideogirls', 'Netvideogirls'),
    ('nubilefilms', 'Nubilefilms'),
    ('nubiles-porn', 'Nubiles-Porn'),
    ('perversefamily', 'Perversefamily'),
    ('realitykings', 'Realitykings'),
    ('teamskeet', 'Teamskeet'),
    ('vixen', 'Vixen'),
]

# ================================================================ 会话与请求

class _Session(object):
    """一个带 cookie 的会话: 取详情页 + 取片源必须用同一个会话。"""

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [
            ("User-Agent", UA),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ]
        self.base = None

    def cookie(self, name):
        for c in self.cj:
            if c.name == name:
                return c.value
        return None

    def fetch(self, url, referer=None, xhr=False, cookie=None, timeout=30):
        headers = {}
        if referer:
            headers["Referer"] = referer
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        if cookie:
            headers["Cookie"] = cookie
        req = urllib.request.Request(url, headers=headers)
        resp = self.op.open(req, timeout=timeout)
        return resp.read()

    def fetch_final(self, url, referer=None, xhr=False, cookie=None, timeout=30):
        """同 fetch, 但额外返回重定向后的最终地址(用来识别兜底回首页)。"""
        headers = {}
        if referer:
            headers["Referer"] = referer
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        if cookie:
            headers["Cookie"] = cookie
        req = urllib.request.Request(url, headers=headers)
        resp = self.op.open(req, timeout=timeout)
        return resp.read(), resp.geturl()

    def text(self, url, **kw):
        return self.fetch(url, **kw).decode("utf-8", "replace")


_TLS = threading.local()


def _session():
    s = getattr(_TLS, "session", None)
    if s is None:
        s = _Session()
        _TLS.session = s
    return s


_BASE_LOCK = threading.Lock()
_BASE = {"host": None, "ts": 0.0}


def base_url():
    """探测一个能用的镜像域名, 缓存 30 分钟。"""
    with _BASE_LOCK:
        h = _BASE["host"]
        if h and (time.time() - _BASE["ts"]) < 1800:
            return h
    for host in HOSTS:
        try:
            req = urllib.request.Request(host + "/", headers={"User-Agent": UA})
            resp = urllib.request.urlopen(req, timeout=12)
            if resp.status == 200 and len(resp.read(2048) or b"") > 0:
                with _BASE_LOCK:
                    _BASE["host"] = host
                    _BASE["ts"] = time.time()
                return host
        except Exception:                                          # noqa: BLE001
            continue
    return HOSTS[0]


def full_url(path, base=None):
    if not path:
        return ""
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("http"):
        return path
    b = base or base_url()
    return b + ("" if path.startswith("/") else "/") + path


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


# ================================================================ 列表解析

_CARD_SPLIT = re.compile(r'<div\s+data-movie-id="\d+"\s+class="ml-item[^"]*">')


def parse_cards(html, base=None):
    """把列表页拆成 PeekPro 的 vod 结构。"""
    base = base or base_url()
    out = []
    seen = set()
    parts = _CARD_SPLIT.split(html)[1:]
    for blk in parts:
        nxt = blk.find('<div  data-movie-id=')
        if nxt > 0:
            blk = blk[:nxt]
        blk = blk[:4000]
        m = re.search(r'<a\s+href="(/movies/[^"]+)"', blk)
        if not m:
            continue
        path = m.group(1)
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)

        t = re.search(r'title="([^"]*)"', blk)
        name = htmlmod.unescape(t.group(1)).strip() if t else ""
        if not name:
            name = slug.replace("-", " ").title()

        img = re.search(r"""<img[^>]+(?:data-original|data-src|src)\s*=\s*["']([^"']+)["']""", blk)
        pic = htmlmod.unescape(img.group(1)) if img else ""
        if pic and not pic.startswith("http"):
            pic = base + ("" if pic.startswith("/") else "/") + pic

        q = re.search(r'class="mli-quality">([^<]*)<', blk)
        remarks = q.group(1).strip() if q and q.group(1).strip() else ""

        out.append({
            "vod_id": slug,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_content": "",
            "vod_play_from": PLAY_FROM,
            "vod_play_url": "%s$%s" % (remarks or "HD", slug),
        })
    return out


def parse_pager(html):
    """从分页栏取最大页码。"""
    m = re.search(r"href=['\"]/?[^'\"]*?page-(\d+)['\"][^>]*>\s*Last", html)
    if m:
        return _int(m.group(1), 1)
    pages = [int(x) for x in re.findall(r"page-(\d+)", html) if x.isdigit()]
    return max(pages) if pages else 1


# ================================================================ 详情解析

def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", htmlmod.unescape(s)).strip()


def parse_detail(html, slug):
    base = base_url()

    title = ""
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
    if m:
        title = htmlmod.unescape(m.group(1)).strip()
    if not title:
        m = re.search(r'class="mvic-desc">\s*<h3>(.*?)</h3>', html, re.S)
        if m:
            title = clean_text(m.group(1))
    if not title:
        title = slug.replace("-", " ").title()

    pic = ""
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
    if m:
        pic = htmlmod.unescape(m.group(1)).strip()
    if not pic:
        m = re.search(r'background-image:\s*url\(([^)]+)\)', html)
        pic = m.group(1).strip("'\" ") if m else ""
    # 封面统一走当前镜像站
    if pic:
        mm = re.search(r"(/Cms_Data/[^\s\"']+)$", pic)
        if mm:
            pic = base + mm.group(1)

    desc = ""
    m = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
    if m:
        desc = htmlmod.unescape(m.group(1)).strip()
    if not desc:
        m = re.search(r'<div class="desc">(.*?)</div>', html, re.S)
        if m:
            desc = clean_text(m.group(1))

    cats = []
    for c in re.findall(r'href="/category/([^"]+)"[^>]*>([^<]*)<', html):
        cname = htmlmod.unescape(c[1]).strip() or c[0]
        if (c[0], cname) not in cats:
            cats.append((c[0], cname))
    if not cats:
        for c in re.findall(r'href="/category/([^"]+)"', html):
            if (c, c) not in cats:
                cats.append((c, c))

    actors = []
    for a in re.findall(r'href="/pornstar/([^"]+)"[^>]*>([^<]*)<', html):
        aname = htmlmod.unescape(a[1]).strip() or a[0]
        if (a[0], aname) not in actors:
            actors.append((a[0], aname))

    tags = []
    for t in re.findall(r'href="/tag/([^"]+)"[^>]*>\s*<h5>([^<]*)</h5>', html):
        tags.append((t[0], htmlmod.unescape(t[1]).strip() or t[0]))

    quality = ""
    m = re.search(r'class="btn-eps[^"]*"[^>]*>\s*([^<]+?)\s*<', html)
    if m:
        quality = m.group(1).strip()

    episodes = extract_episodes(html)

    vod = {
        "vod_id": slug,
        "vod_name": title,
        "vod_pic": pic,
        "vod_remarks": quality or "HD",
        "vod_content": desc,
        "vod_year": "",
        "vod_area": "欧美",
        "vod_lang": "",
        "vod_actor": ", ".join(n for _, n in actors),
        "vod_director": "",
        "vod_play_from": PLAY_FROM,
        "vod_play_url": "%s$%s" % (quality or "HD", slug),
    }
    if cats:
        vod["type_name"] = ", ".join(n for _, n in cats)
        vod["vod_class"] = vod["type_name"]
    if tags:
        vod["vod_tag"] = ", ".join(n for _, n in tags)
    vod["_cats"] = cats
    vod["_actors"] = actors
    vod["_tags"] = tags
    vod["_episodes"] = episodes
    return vod


_EP_RE = re.compile(r"""onclick=['"]\s*loadEpisode\(\s*(\d+)\s*,\s*['"]?([A-Za-z0-9]+)""")


def extract_episodes(html):
    """[(server, episode_id), ...] 去重保序"""
    out = []
    seen = set()
    for sv, ep in _EP_RE.findall(html):
        key = (sv, ep)
        if key in seen:
            continue
        seen.add(key)
        out.append((sv, ep))
    return out


# ================================================================ 播放

def _rand6():
    return "".join(random.choice(string.ascii_lowercase + string.digits)
                   for _ in range(6))


def _sign(episode):
    """(cookie_name, cookie_value, md5_hash)"""
    r = _rand6()
    h = hashlib.md5((episode + r + SALT).encode("utf-8")).hexdigest()
    return COOKIE_PREFIX + episode + COOKIE_SUFFIX, r, h


def fetch_sources(slug, server_pref=("8",), timeout=25):
    """详情页 -> 片源 m3u8 列表。

    返回 dict: {"episodes": [...], "urls": [...], "html": <详情页 html>}
    """
    s = _session()
    base = base_url()
    s.base = base
    page = base + "/movies/" + urllib.parse.quote(slug.strip("/"))
    html = s.text(page, timeout=timeout)

    episodes = extract_episodes(html)
    if not episodes:
        return {"episodes": [], "urls": [], "html": html, "error": "no_episode"}

    # 优先内部服务器(8), 其次任意
    ordered = [e for e in episodes if e[0] in server_pref] + \
              [e for e in episodes if e[0] not in server_pref]

    sid = s.cookie("ASP.NET_SessionId")
    urls = []
    err = ""
    for sv, ep in ordered:
        cname, cval, hsh = _sign(ep)
        cookie = ("ASP.NET_SessionId=%s; " % sid) if sid else ""
        cookie += "%s=%s" % (cname, cval)
        api = "%s/ajax/get_sources/%s/%s?count=1&mobile=false" % (base, ep, hsh)
        try:
            raw = s.text(api, referer=page, xhr=True, cookie=cookie, timeout=timeout)
            data = json.loads(raw)
        except Exception as e:                                     # noqa: BLE001
            err = "%s: %s" % (sv, e)
            continue
        for pl in (data.get("playlist") or []):
            for src in (pl.get("sources") or []):
                f = (src.get("file") or "").strip()
                if f and f not in urls:
                    urls.append(f)
        if len(urls) >= 4:
            break

    return {"episodes": episodes, "urls": urls, "html": html, "error": err}


# ---- PNG 包装的 TS 分片 ------------------------------------------------

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def unpack_segment(data):
    """把 "PNG 包装的 TS 分片" 还原成裸 TS。

    结构: PNG(IEND) -> 一段填充 -> MPEG-TS(0x47 同步, 188 字节包)
    不是 PNG 的(某些 CDN 直接给 TS) 原样返回。
    """
    if not data or not data.startswith(PNG_SIG):
        return data
    n = len(data)
    i = 8
    while i + 8 <= n:
        try:
            ln, typ = struct.unpack(">I4s", data[i:i + 8])
        except struct.error:
            break
        i += 12 + ln
        if typ == b"IEND":
            break
        if ln > n or i > n:
            break
    body = data[i:] if i < n else b""
    k = body.find(b"\x47")
    while k != -1:
        if k + 376 < len(body) and body[k + 188] == 0x47 and body[k + 376] == 0x47:
            return body[k:]
        k = body.find(b"\x47", k + 1)
    return body if body else data


def pack_check(url, timeout=8):
    """探一下分片是不是真有视频数据(有些片源只给占位图)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        head = resp.read(4096)
        resp.close()
    except Exception:                                              # noqa: BLE001
        return False
    if not head:
        return False
    if head.startswith(PNG_SIG):
        i = head.find(b"IEND")
        body = head[i + 8:] if i != -1 else head
        return b"\x47" in body[:600] and len(head) > 2000
    return head[:1] == b"\x47" or len(head) > 2000


def first_segment_url(m3u8_url, timeout=10):
    """取 m3u8 的第一个分片地址。"""
    text = _fetch_bytes(m3u8_url, timeout=timeout).decode("utf-8", "replace")
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return urllib.parse.urljoin(m3u8_url, s)
    return ""


def usable_source(m3u8_url):
    try:
        seg = first_segment_url(m3u8_url)
        return bool(seg) and pack_check(seg)
    except Exception:                                              # noqa: BLE001
        return False


def probe_stream(m3u8_url):
    """返回 (首分片大小, 是否有视频数据)"""
    try:
        seg = first_segment_url(m3u8_url)
        if not seg:
            return 0, False
        req = urllib.request.Request(seg, headers={"User-Agent": UA, "Accept": "*/*"})
        resp = urllib.request.urlopen(req, timeout=12)
        head = resp.read(4096)
        resp.close()
        size = len(head)
        if head.startswith(PNG_SIG) and size <= 1024:
            return size, False                       # 1x1 占位图 = 没片源
        return size, pack_check(seg)
    except Exception:                                              # noqa: BLE001
        return 0, False


def _b64u(s):
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _unb64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")


# ================================================================ 本地代理

class _PublicHolder(threading.local):
    base = None


_PUBLIC = _PublicHolder()

_PROXY_LOCK = threading.Lock()
_PROXY = {"httpd": None, "port": 0}


def _proxy_port():
    with _PROXY_LOCK:
        if _PROXY["httpd"] is not None:
            return _PROXY["port"]
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *a):
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:                                  # noqa: BLE001
                    pass

            def do_HEAD(self):
                self.do_GET(head=True)

            def do_GET(self, head=False):
                port = self.server.server_address[1]
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                if path == "/ping":
                    self._send(200, b"ok", "text/plain")
                    return
                try:
                    if path.startswith("/hls/"):
                        src = _unb64u(path[5:])
                        body = _hls_body(src, port)
                        self._send(200, body.encode("utf-8"),
                                   "application/vnd.apple.mpegurl")
                        return
                    if path.startswith("/seg/"):
                        src = _unb64u(path[5:])
                        data = unpack_segment(_fetch_bytes(src))
                        ct = "video/mp2t" if data[:1] == b"\x47" else "application/octet-stream"
                        # 空分片(占位图) 也照发, 播放器自己会跳
                        if head:
                            self.send_response(200)
                            self.send_header("Content-Type", ct)
                            self.send_header("Content-Length", str(len(data)))
                            self.end_headers()
                            return
                        self._send(200, data, ct)
                        return
                except Exception:                                  # noqa: BLE001
                    pass
                self._send(404, b"not found", "text/plain")

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        httpd.daemon_threads = True
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        _PROXY["httpd"] = httpd
        _PROXY["port"] = port
        return port


def _fetch_bytes(url, timeout=30, referer=None):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read()
    resp.close()
    return data


def _hls_body(src, port, public_base=None):
    """拉原始 m3u8 并把里面所有地址改写到本地代理。"""
    if public_base:
        _PUBLIC.base = public_base.rstrip("/")
    text = _fetch_bytes(src).decode("utf-8", "replace")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if s.startswith("#"):
            # 关键标签里的 URI="..." 也换掉(音频轨/加密 key)
            def _rep(m):
                u = urllib.parse.urljoin(src, m.group(1))
                return 'URI="%s"' % _proxy_url(u, port)
            out.append(re.sub(r'URI="([^"]+)"', _rep, line))
            continue
        u = urllib.parse.urljoin(src, s)
        out.append(_proxy_url(u, port, playlist=".m3u8" in u.split("?")[0].lower()))
    return "\n".join(out) + "\n"


def _proxy_url(url, port, playlist=False):
    base = getattr(_PUBLIC, "base", None) or ("http://127.0.0.1:%d" % port)
    kind = "hls" if playlist else "seg"
    return "%s/%s/%s" % (base, kind, _b64u(url))


def proxied_m3u8(url):
    # serve 模式: 用服务自己的地址(客户端能访问到的那台)
    base = getattr(_PUBLIC, "base", None)
    if base:
        return "%s/hls/%s" % (base.rstrip("/"), _b64u(url))
    port = _proxy_port()
    return "http://127.0.0.1:%d/hls/%s" % (port, _b64u(url))


# ================================================================ 业务接口

def _classes():
    out = [
        {"type_id": "latest", "type_name": "最新"},
        {"type_id": "home", "type_name": "首页推荐"},
    ]
    for slug, name in CATEGORIES[:14]:
        out.append({"type_id": "category:" + slug, "type_name": name})
    for slug, name in STUDIOS:
        out.append({"type_id": "studio:" + slug, "type_name": name})
    for slug, name in TAG_HOT[:8]:
        out.append({"type_id": "tag:" + slug, "type_name": "#" + name})
    return out


def _filters():
    cats = [{"n": "全部", "v": ""}] + \
           [{"n": name, "v": "category:" + slug} for slug, name in CATEGORIES]
    studs = [{"n": "全部", "v": ""}] + \
            [{"n": name, "v": "studio:" + slug} for slug, name in STUDIOS]
    tags = [{"n": "全部", "v": ""}] + \
           [{"n": name, "v": "tag:" + slug} for slug, name in TAG_HOT]
    group = [
        {"key": "分类", "name": "分类", "value": cats},
        {"key": "工作室", "name": "工作室", "value": studs},
        {"key": "标签", "name": "标签", "value": tags},
    ]
    out = {"latest": group, "home": group}
    for slug, _name in CATEGORIES[:14]:
        out["category:" + slug] = group
    return out


def _tid_path(tid, pg, extend=None):
    """tid -> (路径模板, 说明) ; 返回 None 表示首页"""
    tid = (tid or "latest").strip()
    if extend:
        for key in ("分类", "工作室", "标签"):
            v = extend.get(key) if isinstance(extend, dict) else None
            if v and v != "全部":
                tid = v
                break
    if tid.lower() in ("", "home", "0", "推荐", "首页"):
        return None
    kind, _, val = tid.partition(":")
    kind = kind.lower()
    if kind == "category":
        return "/category/%s/page-%d" % (urllib.parse.quote(val), pg)
    if kind == "studio":
        return "/studio/%s/page-%d" % (urllib.parse.quote(val), pg)
    if kind == "pornstar":
        return "/pornstar/%s/page-%d" % (urllib.parse.quote(val), pg)
    if kind == "tag":
        return "/tag/%s/page-%d" % (urllib.parse.quote(val), pg)
    if kind == "search":
        return "/search/%s/page-%d" % (urllib.parse.quote(val), pg)
    if tid == "latest":
        return "/premium-porn-hd/page-%d" % pg
    # 裸 slug 当分类
    return "/category/%s/page-%d" % (urllib.parse.quote(tid), pg)


def get_home():
    base = base_url()
    html = _session().text(base + "/", timeout=25)
    return parse_cards(html, base)


def get_list(tid, pg=1, filter=None, extend=None):
    pg = max(1, _int(pg, 1))
    base = base_url()
    path = _tid_path(tid, pg, extend)
    if path is None:
        items = get_home()
        return {"list": items, "page": 1, "pagecount": 1,
                "limit": len(items), "total": len(items)}
    raw, final_url = _session().fetch_final(base + path, timeout=30)
    html = raw.decode("utf-8", "replace")
    # 站点对不存在的分类/女优/标签会 302 回首页, 这里吃掉, 免得给出不相关内容
    if path.split("/")[1] in ("category", "studio", "pornstar", "tag"):
        want = urllib.parse.urlparse(path).path.rstrip("/")
        got = urllib.parse.urlparse(final_url or "").path.rstrip("/")
        if got != want:
            t = re.search(r"<title>(.*?)</title>", html, re.S)
            if got in ("", "/") or (t and t.group(1).strip().startswith("Download PornHD")):
                return {"list": [], "page": pg, "pagecount": 1,
                        "limit": PAGE_SIZE, "total": 0}
    items = parse_cards(html, base)
    pagecount = parse_pager(html)
    if pg >= pagecount:
        pagecount = pg
    return {
        "list": items,
        "page": pg,
        "pagecount": pagecount,
        "limit": PAGE_SIZE,
        "total": pagecount * PAGE_SIZE,
    }


def get_search(key, pg=1):
    pg = max(1, _int(pg, 1))
    base = base_url()
    path = "/search/%s/page-%d" % (urllib.parse.quote(str(key).strip()), pg)
    html = _session().text(base + path, timeout=30)
    items = parse_cards(html, base)
    pagecount = parse_pager(html)
    if pg >= pagecount:
        pagecount = pg
    return {
        "list": items,
        "page": pg,
        "pagecount": pagecount,
        "limit": PAGE_SIZE,
        "total": pagecount * PAGE_SIZE,
    }


def _norm_slug(ids):
    s = str(ids or "").strip()
    if not s:
        return ""
    if s.startswith("http"):
        parsed = urllib.parse.urlparse(s)
        m = re.search(r"/movies/([^/?#]+)", parsed.path)
        return m.group(1) if m else parsed.path.strip("/").rsplit("/", 1)[-1]
    if s.startswith("/movies/"):
        s = s[len("/movies/"):]
    s = s.split("#")[0].split("?")[0]
    return s.strip("/")


def get_detail(ids):
    slug = _norm_slug(ids)
    if not slug:
        return []
    base = base_url()
    html = _session().text(base + "/movies/" + urllib.parse.quote(slug), timeout=30)
    vod = parse_detail(html, slug)
    vod.pop("_cats", None)
    vod.pop("_actors", None)
    vod.pop("_tags", None)
    vod.pop("_episodes", None)
    return [vod]


def get_play(pid):
    slug = _norm_slug(pid)
    fallback = {"parse": 0, "playUrl": "", "url": "", "header": {}, "flag": PLAY_FROM}
    if not slug:
        return fallback
    try:
        info = fetch_sources(slug)
    except Exception:                                              # noqa: BLE001
        return fallback
    urls = info.get("urls") or []
    if not urls:
        return fallback

    # 优先挑真有视频数据的那个(有些服务器返回的是 1x1 占位图)
    chosen = urls[0]
    chosen_size = None
    for u in urls[:3]:
        size, usable = probe_stream(u)
        if usable:
            chosen, chosen_size = u, size
            break
        if chosen_size is None:
            chosen, chosen_size = u, size

    # 首分片小到不可能是视频 = 这部没有片源, 直接如实返回空
    if chosen_size is not None and chosen_size <= 1024:
        return fallback

    try:
        url = proxied_m3u8(chosen)
    except Exception:                                              # noqa: BLE001
        url = chosen
    return {
        "parse": 0,
        "playUrl": "",
        "url": url,
        "header": {"User-Agent": UA},
        "flag": PLAY_FROM,
    }


# ================================================================ PeekPro 接口

class Spider(object):
    localProxy = True

    def __init__(self):
        self.extend = ""

    def init(self, extend=""):
        self.extend = extend or ""
        return None

    def getName(self):
        return "PornHD3X"

    def homeContent(self, filter=None):
        try:
            return {"class": _classes(), "filters": _filters(), "list": get_home()}
        except Exception:                                          # noqa: BLE001
            return {"class": _classes(), "filters": _filters(), "list": []}

    def homeVideoContent(self):
        try:
            return {"list": get_home()}
        except Exception:                                          # noqa: BLE001
            return {"list": []}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        try:
            return get_list(tid, pg, filter, extend)
        except Exception:                                          # noqa: BLE001
            return {"list": [], "page": _int(pg, 1), "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}

    def detailContent(self, ids):
        try:
            return {"list": get_detail(ids)}
        except Exception:                                          # noqa: BLE001
            return {"list": []}

    def searchContent(self, key, quick=False, pg=1):
        try:
            return get_search(key, pg)
        except Exception:                                          # noqa: BLE001
            return {"list": [], "page": _int(pg, 1), "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags=None):
        return get_play(id)

    def isVideoFormat(self, url):
        u = str(url or "")
        return ".m3u8" in u or ".mp4" in u or "/hls/" in u

    def manualVideoCheck(self):
        return False


def _fn(name):
    def wrapper(*args, **kwargs):
        return getattr(Spider(), name)(*args, **kwargs)
    wrapper.__name__ = name
    return wrapper


homeContent = _fn("homeContent")
homeVideoContent = _fn("homeVideoContent")
categoryContent = _fn("categoryContent")
detailContent = _fn("detailContent")
searchContent = _fn("searchContent")
searchContentPage = _fn("searchContentPage")
playerContent = _fn("playerContent")
isVideoFormat = _fn("isVideoFormat")
manualVideoCheck = _fn("manualVideoCheck")
init = _fn("init")


def main(action, *args, **kwargs):
    """PeekPro 分发入口: main('homeContent') / main('categoryContent', tid, pg) ..."""
    act = str(action or "").strip()
    fn = globals().get(act)
    if callable(fn):
        return fn(*args, **kwargs)
    return {}


# ================================================================ CMS 服务模式

def make_cms_response(params, public_base=None):
    if public_base:
        _PUBLIC.base = public_base
    ac = (params.get("ac") or params.get("action") or ["list"])[0].lower()
    tid = (params.get("t") or params.get("tid") or ["latest"])[0] or "latest"
    pg = _int((params.get("pg") or params.get("page") or ["1"])[0], 1) or 1
    wd = (params.get("wd") or params.get("key") or [""])[0]
    ids = (params.get("ids") or params.get("id") or [""])[0]

    if wd:
        data = get_search(wd, pg)
        data["code"] = 1
        data["msg"] = "数据列表"
        return data

    if ac in ("detail", "videolist") or (ids and ac != "play"):
        items = get_detail(ids)
        return {"code": 1, "msg": "数据列表", "page": 1, "pagecount": 1,
                "limit": len(items), "total": len(items), "list": items}

    if ac == "play":
        return get_play(ids)

    data = get_list(tid, pg)
    data["code"] = 1
    data["msg"] = "数据列表"
    return data


def serve(port=8899, host="0.0.0.0"):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            except Exception:                                      # noqa: BLE001
                pass

        def _public_base(self):
            h = self.headers.get("Host") or ("127.0.0.1:%d" % port)
            return "http://" + h

        def do_HEAD(self):
            self.do_get(head=True)

        def do_GET(self, head=False):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            port_now = self.server.server_address[1]
            try:
                if path.startswith("/hls/"):
                    src = _unb64u(path[5:])
                    data = _hls_body(src, port_now, self._public_base())
                    self._send(200, data, "application/vnd.apple.mpegurl")
                    return
                if path.startswith("/seg/"):
                    src = _unb64u(path[5:])
                    data = unpack_segment(_fetch_bytes(src))
                    ct = "video/mp2t" if data[:1] == b"\x47" else "application/octet-stream"
                    self._send(200, data, ct)
                    return
                if path in ("/", "/ping", "/health"):
                    self._send(200, "PornHD3X PeekPro bridge running", "text/plain")
                    return
                params = urllib.parse.parse_qs(parsed.query)
                data = make_cms_response(params, self._public_base())
                self._send(200, json.dumps(data, ensure_ascii=False))
            except Exception as e:                                 # noqa: BLE001
                self._send(500, json.dumps({"code": 0, "msg": str(e)[:200],
                                            "list": []}, ensure_ascii=False))

        do_POST = do_GET

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print("PornHD3X PeekPro bridge: http://%s:%d/api.php/provide/vod/" % (host, port))
    print("  ac=list&t=latest&pg=1    ac=detail&ids=<slug>    wd=<关键词>")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# ================================================================ 命令行调试

def _cli(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("用法:")
        print("  python3 pornhd3x_peekpro.py serve [--port 8899] [--host 0.0.0.0]")
        print("  python3 pornhd3x_peekpro.py home")
        print("  python3 pornhd3x_peekpro.py list latest 1")
        print("  python3 pornhd3x_peekpro.py list category:big-butts-like-it-big 2")
        print("  python3 pornhd3x_peekpro.py list studio:brazzers 1")
        print("  python3 pornhd3x_peekpro.py search brazzers")
        print("  python3 pornhd3x_peekpro.py detail <slug>")
        print("  python3 pornhd3x_peekpro.py play <slug>")
        return

    cmd = argv[0].lower()
    if cmd == "serve":
        port, host = 8899, "0.0.0.0"
        i = 1
        while i < len(argv):
            if argv[i] == "--port" and i + 1 < len(argv):
                port = _int(argv[i + 1], 8899); i += 2
            elif argv[i] == "--host" and i + 1 < len(argv):
                host = argv[i + 1]; i += 2
            else:
                i += 1
        serve(port, host)
        return

    if cmd == "home":
        data = Spider().homeContent()
        for it in data["list"]:
            print("%-70s %s" % (it["vod_name"][:68], it["vod_id"]))
        print("共 %d 条" % len(data["list"]))
        return

    if cmd == "list":
        tid = argv[1] if len(argv) > 1 else "latest"
        pg = _int(argv[2], 1) if len(argv) > 2 else 1
        data = get_list(tid, pg)
        for it in data["list"]:
            print("%-70s %s" % (it["vod_name"][:68], it["vod_id"]))
        print("page=%s pagecount=%s 共 %d 条" % (data["page"], data["pagecount"], len(data["list"])))
        return

    if cmd == "search":
        kw = argv[1] if len(argv) > 1 else ""
        pg = _int(argv[2], 1) if len(argv) > 2 else 1
        data = get_search(kw, pg)
        for it in data["list"]:
            print("%-70s %s" % (it["vod_name"][:68], it["vod_id"]))
        print("page=%s pagecount=%s 共 %d 条" % (data["page"], data["pagecount"], len(data["list"])))
        return

    if cmd == "detail":
        slug = argv[1] if len(argv) > 1 else ""
        for v in get_detail(slug):
            for k in ("vod_name", "vod_pic", "vod_remarks", "vod_actor",
                      "type_name", "vod_tag", "vod_content", "vod_play_url"):
                if v.get(k):
                    print("%-12s %s" % (k + ":", str(v[k])[:200]))
        return

    if cmd == "play":
        slug = argv[1] if len(argv) > 1 else ""
        info = fetch_sources(slug)
        print("episodes:", info["episodes"])
        print("sources :", len(info["urls"]))
        for u in info["urls"]:
            print("  ", u)
        if info["urls"]:
            first = info["urls"][0]
            m3 = _fetch_bytes(first).decode("utf-8", "replace")
            segs = [l for l in m3.splitlines() if l and not l.startswith("#")]
            print("segments:", len(segs))
            if segs:
                seg_url = urllib.parse.urljoin(first, segs[0])
                data = _fetch_bytes(seg_url)
                ts = unpack_segment(data)
                print("segment#0 raw=%d -> ts=%d  同步字节=%r"
                      % (len(data), len(ts), ts[:1]))
                if len(ts) > 1000:
                    open("/tmp/_seg0.ts", "wb").write(ts)
                    print("已写出 /tmp/_seg0.ts (可直接 ffprobe 验证)")
        res = get_play(slug)
        print("playUrl:", res["url"][:160])
        return

    print("未知命令:", cmd)


if __name__ == "__main__":
    _cli(sys.argv[1:])
