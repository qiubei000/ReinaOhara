#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
591AV（PPP.Porn / 精选亚洲素人成人影片）Python 源 —— 2026-11 修复版

修复内容：
  1. 站源：名称改为网站品牌「PPP.Porn」；分类与网站导航一致
     （最新上架 / 热门排行 + 网站 33 个分类，名称/顺序从网站读取）；
  2. 线路：网站只有一条播放源 → 统一显示「PPP.Porn」；
  3. 选集：网站每个视频就是正片 → 选集「正片」；
  4. 简介：用网站自己的描述（og:description / meta description），不再是广告；
  5. 导演/演员：网站没有导演字段（留空），演员取网站的模特/演员链接（/s/…）；
  6. 详情补全：标题、封面、分类、日期、简介；
  7. 播放：网站 m3u8 是 AES-128 且带时效签名、校验 Referer，并会被 CDN 缓存成过期 token。
     现在播放时用「页面地址 + 随机参数」实时取最新 stream，并带上页面 Referer 播放，
     不会再出现黑屏/410；
  8. 域名：从 x99dh 导航页自动解析 591AV 当前域名，跟随 /enter 跳转，失败再回退常用域名。
"""

import base64
import gzip
import json
import random
import re
import sys
import time
import urllib.parse
import zlib
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

SITE_NAME = "PPP.Porn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

NAV_URLS = ["https://x99dh.cc/", "https://x99dh.com/", "https://x99dh.one/"]
FALLBACK_HOSTS = ["https://591av.ws", "https://591av.net", "https://591av.sbs"]


def _clean(text):
    import html as _html
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()


def _b64decode_text(text):
    import html as _html
    return _html.unescape(text or "")


class Spider(SpiderBase):
    def __init__(self):
        super().__init__()
        self.host = FALLBACK_HOSTS[0]
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cache = {}
        self._stream_cache = {}

    # ---------------- 基础 ----------------
    def getName(self):
        return SITE_NAME

    def isVideoFormat(self, url):
        return any(k in (url or "").lower() for k in (".m3u8", ".mp4", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def init(self, extend=""):
        site = ""
        try:
            cached = self.getCache("591av_site_url")
            if cached and str(cached).startswith("http"):
                site = str(cached).strip().rstrip("/")
        except Exception:
            site = ""
        if not site:
            site = self._discover_site()
        self.host = site or FALLBACK_HOSTS[0]
        self.session.headers.update({"Referer": self.host + "/"})
        try:
            self.setCache("591av_site_url", self.host)
        except Exception:
            pass
        return True

    def _get(self, url, allow_redirects=True):
        return self.session.get(url, headers=self.headers, timeout=(5, 20),
                                verify=False, allow_redirects=allow_redirects)

    def _test_site(self, url):
        try:
            r = self._get(url)
            final = (r.url or url).rstrip("/")
            text = r.text or ""
            if urlparse(final).scheme not in ("http", "https"):
                return ""
            if r.status_code == 200 and ("PPP.Porn" in text or "591av" in text.lower()
                                        or "亚洲素人" in text):
                return "%s://%s" % (urlparse(final).scheme, urlparse(final).netloc)
        except Exception:
            pass
        return ""

    def _discover_site(self):
        # 1) 从 x99dh 导航页解析（base64 JSON 站点列表）
        for nav in NAV_URLS:
            try:
                r = self._get(nav)
                text = r.text or ""
            except Exception:
                continue
            for b in re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text):
                try:
                    decoded = base64.b64decode(b).decode("utf-8", "ignore")
                    data = json.loads(unquote(decoded))
                except Exception:
                    continue
                if not isinstance(data, list):
                    continue
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "")
                    if not ("591" in name or "亚洲素人" in name):
                        continue
                    candidates = []
                    if item.get("url"):
                        candidates.append(item["url"])
                    for u in item.get("urls") or []:
                        if isinstance(u, dict) and u.get("url"):
                            candidates.append(u["url"])
                        elif isinstance(u, str):
                            candidates.append(u)
                    for cand in candidates:
                        site = self._test_site(cand)
                        if site:
                            return site
        # 2) 常用域名 + /enter 跳转
        for host in FALLBACK_HOSTS:
            for path in ("/enter", "/"):
                site = self._test_site(host + path)
                if site:
                    return site
        return ""

    def _fetch(self, url):
        if url.startswith("/"):
            url = self.host + url
        for _ in range(2):
            try:
                r = self._get(url)
                if r.status_code == 200 and len(r.text or "") > 3000:
                    r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
            time.sleep(0.3)
        return ""

    # ---------------- 首页 / 分类 ----------------
    def _categories(self):
        cache_key = "cats"
        if cache_key in self._cache:
            return self._cache[cache_key]
        cats = []
        text = self._fetch(self.host + "/categories/")
        if text:
            for m in re.finditer(
                    r'<a[^>]+href="([^"]*?/categories/[^"]+)"[^>]*>([\s\S]*?)</a>', text):
                href = m.group(1)
                name = _clean(m.group(2))
                name = re.sub(r'^\d+\s*影片\s*', '', name).strip()
                if not name or name in ("所有分类",):
                    continue
                if href not in [c[1] for c in cats]:
                    cats.append((name, href))
        self._cache[cache_key] = cats
        return cats

    def homeContent(self, filter=False):
        classes = [
            {"type_name": "最新上架", "type_id": "/new/"},
            {"type_name": "热门排行", "type_id": "/pp1/hot/"},
        ]
        for name, href in self._categories():
            classes.append({"type_name": name, "type_id": href})
        videos = self._list(self.host + "/new/")
        return {"class": classes, "filters": {}, "list": videos}

    def homeVideoContent(self):
        return {"list": self._list(self.host + "/new/")}

    def _category_url(self, tid, page):
        tid = str(tid or "").strip()
        if tid.startswith("http"):
            base = tid.rstrip("/")
        else:
            base = (self.host + (tid if tid.startswith("/") else "/" + tid)).rstrip("/")
        return base + "/" if page == 1 else "%s/%d/" % (base, page)

    def _pagecount(self, html_text):
        html_text = html_text or ""
        i = html_text.find("pagination__list")
        for seg in (html_text[i:i + 30000], html_text):
            m = re.search(r'>\s*\d+\s*/\s*(\d+)\s*<', seg)
            if m:
                try:
                    return max(1, int(m.group(1)))
                except Exception:
                    pass
            m = re.search(r'\b1\s*/\s*(\d+)\b', seg)
            if m:
                try:
                    return max(1, int(m.group(1)))
                except Exception:
                    pass
        return 1

    def _list(self, url):
        html_text = self._fetch(url)
        if not html_text:
            return []
        videos = []
        seen = set()
        idx = [m.start() for m in re.finditer(r'<div class="item card-video', html_text)]
        for k, i in enumerate(idx):
            j = idx[k + 1] if k + 1 < len(idx) else min(len(html_text), i + 5000)
            block = html_text[i:j]
            am = re.search(r'<a href="([^"]*?/v/[^"]+)"', block)
            if not am:
                continue
            href = am.group(1)
            if href.startswith("/"):
                href = self.host + href
            if href in seen:
                continue
            tm = re.search(r'<h4[^>]*class="[^"]*card-video__title[^"]*"[^>]*>([\s\S]*?)</h4>', block)
            title = _clean(tm.group(1)) if tm else ""
            if not title:
                tm = re.search(r'<img[^>]+alt="([^"]+)"', block)
                title = _clean(tm.group(1)) if tm else ""
            if not title:
                continue
            pic = ""
            pm = re.search(r'<img[^>]+data-src="([^"]+)"', block)
            if pm:
                pic = pm.group(1)
            if not pic:
                pm = re.search(r'<img[^>]+src="([^"]+)"', block)
                if pm and "placeholder" not in pm.group(1):
                    pic = pm.group(1)
            dur = ""
            dm = re.search(r'card-video__duration[^>]*>([^<]+)<', block)
            if dm:
                dur = _clean(dm.group(1))
            views = ""
            vm = re.search(r'<span class="num">([^<]+)</span>\s*观看', block)
            if vm:
                views = _clean(vm.group(1))
            seen.add(href)
            videos.append({
                "vod_id": href,
                "vod_name": title[:120],
                "vod_pic": pic,
                "vod_remarks": dur or views,
            })
        return videos

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        url = self._category_url(tid, page)
        html_text = self._fetch(url)
        videos = self._list(url) if html_text else []
        pagecount = self._pagecount(html_text) if html_text else 1
        if page > 1 and not videos:
            first = self._fetch(self._category_url(tid, 1))
            if first:
                pagecount = self._pagecount(first)
            else:
                pagecount = 1
        return {"list": videos, "page": page, "pagecount": max(1, pagecount),
                "limit": len(videos) or 24,
                "total": pagecount * 24 if pagecount > 1 else len(videos)}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        q = quote(str(key or "").strip())
        url = "%s/search/?q=%s" % (self.host, q)
        if page > 1:
            url += "&page=%d" % page
        html_text = self._fetch(url)
        videos = self._list(url) if html_text else []
        pagecount = self._pagecount(html_text) if html_text else 1
        return {"list": videos, "page": page, "pagecount": max(1, pagecount),
                "limit": len(videos) or 24,
                "total": pagecount * 24 if pagecount > 1 else len(videos)}

    # ---------------- 详情 ----------------
    def _detail_page(self, url):
        """带随机参数取详情页，避免 CDN 缓存里过期的 stream token。"""
        sep = "&" if "?" in url else "?"
        busted = "%s%s_=%d" % (url, sep, random.randint(100000, 999999))
        text = self._fetch(busted)
        if not text:
            text = self._fetch(busted)
        return text

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0] if isinstance(ids, list) else ids
        url = vid if str(vid).startswith("http") else self.host + str(vid)
        html_text = self._detail_page(url)
        if not html_text:
            return {"list": []}

        tm = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html_text)
        if not tm:
            tm = re.search(r"<title>([\s\S]*?)</title>", html_text)
        title = _clean(tm.group(1)) if tm else ""
        title = re.sub(r"\s*-\s*PPP\.Porn.*$", "", title).strip()
        title = re.sub(r"\s*-\s*591av.*$", "", title, flags=re.I).strip()

        pic = ""
        pm = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]*)"', html_text)
        if pm:
            pic = pm.group(1)

        date = ""
        dm = re.search(r'<meta[^>]+property="video:release_date"[^>]+content="([^"]*)"', html_text)
        if dm:
            date = dm.group(1)[:10]

        cats = []
        for cm in re.finditer(r'<a[^>]+href="[^"]*?/categories/[^"]*"[^>]*>([^<]+)</a>', html_text):
            name = _clean(cm.group(1))
            if name and name not in cats:
                cats.append(name)

        actors = []
        for am in re.finditer(r'<a[^>]+href="[^"]*?/s/[^"]*"[^>]*>([^<]+)</a>', html_text):
            name = _clean(am.group(1))
            if name and name not in actors:
                actors.append(name)

        desc = ""
        dm2 = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', html_text)
        if not dm2:
            dm2 = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html_text)
        if dm2:
            desc = _clean(dm2.group(1))

        token = base64.b64encode(("page|%s" % url).encode("utf-8")).decode("ascii")
        return {"list": [{
            "vod_id": vid,
            "vod_name": title or SITE_NAME,
            "vod_pic": pic,
            "type_name": " / ".join(cats[:3]),
            "vod_year": date[:4] if date else "",
            "vod_area": "",
            "vod_remarks": date,
            "vod_actor": " / ".join(actors),
            "vod_director": "",
            "vod_content": desc,
            "vod_play_from": SITE_NAME,
            "vod_play_url": "正片$%s" % token,
        }]}

    # ---------------- 播放 ----------------
    def _resolve_stream(self, page_url):
        key = page_url
        cached = self._stream_cache.get(key)
        if cached:
            stream, expire = cached
            if expire - 120 > time.time():
                return stream
        html_text = self._detail_page(page_url)
        if not html_text:
            return ""
        sm = re.search(r"var stream = '([^']+)'", html_text)
        if not sm:
            return ""
        stream = sm.group(1).replace("\\/", "/")
        ts = re.search(r"/(\d{10})/", stream)
        if ts:
            expire = int(ts.group(1))
            # token 已过期就再换一次随机参数重取
            if expire <= time.time() + 60:
                html_text = self._detail_page(page_url)
                sm = re.search(r"var stream = '([^']+)'", html_text or "")
                if sm:
                    stream = sm.group(1).replace("\\/", "/")
                    ts = re.search(r"/(\d{10})/", stream)
                    expire = int(ts.group(1)) if ts else time.time() + 300
            self._stream_cache[key] = (stream, expire)
        return stream

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "").strip()
        if "$" in raw:
            raw = raw.split("$")[-1].strip()
        raw = unquote(raw)
        page_url = ""
        try:
            decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8", "ignore")
            if decoded.startswith("page|"):
                page_url = decoded.split("|", 1)[1]
        except Exception:
            page_url = ""
        if not page_url and raw.startswith("http"):
            page_url = raw
        if not page_url:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}
        stream = self._resolve_stream(page_url)
        if not stream:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}
        return {
            "parse": 0,
            "playUrl": "",
            "url": stream,
            "header": {
                "User-Agent": UA,
                "Referer": page_url,
                "Origin": self.host,
            },
        }

    def localProxy(self, param):
        return None

    def action(self, action=None):
        return {"msg": "ok"}

    def liveContent(self):
        return ""
