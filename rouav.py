#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肉视频（rouAV · 肉视频）Python 源 —— 2026-11 修复版

修复内容：
  1. 站源：名称改为网站品牌「rouAV · 肉视频」；分类与网站导航一致（国产AV/日本/自拍流出/探花/OnlyFans/其他）；
  2. 线路：网站只有一条播放源 → 显示「肉视频」；
  3. 选集：网站一个视频就是正片 → 「正片」；若页面出现多集链接则自动按集展开；
  4. 简介：取网站「影片简介」内容，不再拼接 TG/站点广告；
  5. 导演/演员：取网站数据（播放器 vod_data 的 vod_director / vod_actor / 主演链接），网站没有就留空；
  6. 详情补全：标题、封面（网站封面图）、类型、年份、地区、日期、标签；
  7. 列表：标题、封面、时长/分类日期备注；分页读网站真实页数（/vod/show/id/{cid}/page/{n}.html）；
  8. 播放：走网站 /api/v/{code} → videoUrl（HLS m3u8），播放时再实时解析；
  9. 域名：从 x99dh 导航解析 rouAV 当前域名，失败回退 rou123.ws / rou123.cfd。
"""

import base64
import gzip
import json
import random
import re
import socketserver
import sys
import threading
import time
import urllib.parse
import zlib
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

SITE_NAME = "rouAV · 肉视频"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

NAV_URLS = ["https://x99dh.cc/", "https://x99dh.com/", "https://x99dh.one/"]
FALLBACK_HOSTS = ["https://rou123.ws", "https://rou123.cfd"]

# 网站导航分类（顺序与网站一致，解析失败时兜底）
DEFAULT_CLASSES = [
    ("国产AV", "7"),
    ("日本", "3"),
    ("自拍流出", "6"),
    ("探花", "5"),
    ("OnlyFans", "4"),
    ("其他", "1"),
]


def _clean(text):
    import html as _html
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()


_HLS_LOCK = threading.Lock()
_HLS_PORT = 0
_HLS_HEADERS = {"User-Agent": UA, "Referer": ""}


def _hls_base(port):
    return "http://127.0.0.1:%d" % port


def _b64url(value):
    return quote(base64.b64encode(str(value).encode("utf-8")).decode("ascii"), safe="")


def _ensure_hls_server():
    global _HLS_PORT
    with _HLS_LOCK:
        if _HLS_PORT:
            return _HLS_PORT
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _HlsHandler)
        server.daemon_threads = True
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _HLS_PORT = port
        return port


class _HlsHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            route = parsed.path or "/"
            params = {}
            for part in parsed.query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = unquote(v)
            target = base64.b64decode(params.get("u", "")).decode("utf-8", "ignore")
            if not target.startswith("http"):
                raise ValueError("bad url")

            if route in ("/local.m3u8", "/hls"):
                port = _ensure_hls_server()
                base = _hls_base(port)
                r = requests.get(target, headers=_HLS_HEADERS, timeout=(5, 25),
                                 verify=False, allow_redirects=True)
                text = r.text or ""
                root = (r.url or target).rsplit("/", 1)[0]
                is_master = "#EXT-X-STREAM-INF" in text
                out = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#") and 'URI="' in line:
                        def repl(m):
                            uri = m.group(1)
                            abs_url = uri if uri.startswith("http") else root + "/" + uri.lstrip("/")
                            return 'URI="%s/f?u=%s"' % (base, _b64url(abs_url))
                        line = re.sub(r'URI="([^"]+)"', repl, line)
                        out.append(line)
                        continue
                    if line.startswith("#"):
                        out.append(line)
                        continue
                    abs_url = line if line.startswith("http") else root + "/" + line.lstrip("/")
                    out.append("%s/local.m3u8?u=%s" % (base, _b64url(abs_url)) if is_master
                               else "%s/f?u=%s" % (base, _b64url(abs_url)))
                body = ("\n".join(out) + "\n").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return

            if route == "/f":
                hdrs = dict(_HLS_HEADERS)
                rh = self.headers.get("Range")
                if rh:
                    hdrs["Range"] = rh
                r = requests.get(target, headers=hdrs, timeout=(5, 30),
                                 verify=False, allow_redirects=True)
                body = r.content or b""
                if r.status_code not in (200, 206) or not body:
                    self.send_response(502)
                    self.end_headers()
                    return
                self.send_response(r.status_code)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                if r.headers.get("Content-Range"):
                    self.send_header("Content-Range", r.headers["Content-Range"])
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(404)
            self.end_headers()
        except Exception:
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass


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
            cached = self.getCache("rouav_site_url")
            if cached and str(cached).startswith("http"):
                site = str(cached).strip().rstrip("/")
        except Exception:
            site = ""
        if not site or not self._test(site):
            site = self._discover_site()
        self.host = site or FALLBACK_HOSTS[0]
        self.session.headers.update({"Referer": self.host + "/"})
        _HLS_HEADERS["User-Agent"] = UA
        _HLS_HEADERS["Referer"] = self.host + "/"
        try:
            self.setCache("rouav_site_url", self.host)
        except Exception:
            pass
        return True

    def _get(self, url):
        return self.session.get(url, headers=self.headers, timeout=(5, 20),
                                verify=False, allow_redirects=True)

    def _test(self, base):
        try:
            r = self._get(base + "/vodtype/7.html")
            if r.status_code == 200 and ("肉视频" in (r.text or "") or "rouAV" in (r.text or "")):
                return True
        except Exception:
            pass
        return False

    def _discover_site(self):
        # 1) x99dh 导航页：base64 JSON 站点列表，找 rouAV
        for nav in NAV_URLS:
            try:
                r = self._get(nav)
                text = r.text or ""
            except Exception:
                continue
            for b in re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text):
                try:
                    data = json.loads(unquote(base64.b64decode(b).decode("utf-8", "ignore")))
                except Exception:
                    continue
                if not isinstance(data, list):
                    continue
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "")
                    if name.lower() != "rouav":
                        continue
                    cands = []
                    if item.get("url"):
                        cands.append(item["url"])
                    for u in item.get("urls") or []:
                        if isinstance(u, dict) and u.get("url"):
                            cands.append(u["url"])
                    for cand in cands:
                        p = urlparse(cand)
                        base = "%s://%s" % (p.scheme, p.netloc)
                        if self._test(base):
                            return base
        # 2) 回退常用域名
        for base in FALLBACK_HOSTS:
            if self._test(base):
                return base
        return ""

    def _enter_html(self):
        for path in ("/enter", "/"):
            try:
                r = self._get(self.host + path)
                if r.status_code == 200 and len(r.text or "") > 20000:
                    r.encoding = "utf-8"
                    return r.text
            except Exception:
                continue
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
            time.sleep(0.25)
        return ""

    # ---------------- 首页 / 分类 ----------------
    def _classes(self):
        if "classes" in self._cache:
            return self._cache["classes"]
        classes = []
        html_text = self._enter_html()
        if html_text:
            for m in re.finditer(r'<a[^>]+href="/vodtype/(\d+)\.html"[^>]*>([^<]+)</a>', html_text):
                cid, name = m.group(1), _clean(m.group(2))
                if name and (name, cid) not in classes:
                    classes.append((name, cid))
        if not classes:
            classes = list(DEFAULT_CLASSES)
        self._cache["classes"] = classes
        return classes

    def homeContent(self, filter=False):
        classes = [{"type_name": n, "type_id": cid} for n, cid in self._classes()]
        return {"class": classes, "filters": {}, "list": self._list(self._enter_html())}

    def homeVideoContent(self):
        return {"list": self._list(self._enter_html())}

    def _list(self, html_text):
        if not html_text:
            return []
        videos = []
        seen = set()
        idx = [m.start() for m in re.finditer(r'<div class="movie-item', html_text)]
        for k, i in enumerate(idx):
            j = idx[k + 1] if k + 1 < len(idx) else min(len(html_text), i + 4000)
            block = html_text[i:j]
            am = re.search(r'<a[^>]+href="(/vodplay/\d+-\d+-\d+\.html)"', block)
            if not am:
                continue
            href = am.group(1)
            if href in seen:
                continue
            tm = re.search(r'<h3[^>]*class="[^"]*movie-title[^"]*"[^>]*>([\s\S]*?)</h3>', block)
            title = _clean(tm.group(1)) if tm else ""
            if not title:
                tm = re.search(r'<img[^>]+alt="([^"]+)"', block)
                title = _clean(tm.group(1)) if tm else ""
            if not title:
                continue
            pic = ""
            pm = re.search(r'<img[^>]+class="[^"]*thumbnail-poster[^"]*"[^>]+src="([^"]+)"', block)
            if not pm:
                pm = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', block)
            if pm:
                pic = pm.group(1).strip()
                if pic.startswith("//"):
                    pic = "https:" + pic
            dur = ""
            dm = re.search(r'movie-duration-span[^>]*>([^<]+)<', block)
            if dm:
                dur = _clean(dm.group(1))
            info = ""
            im = re.search(r'<p[^>]*class="[^"]*movie-info[^"]*"[^>]*>([\s\S]*?)</p>', block)
            if im:
                info = _clean(im.group(1))
            seen.add(href)
            videos.append({
                "vod_id": href,
                "vod_name": title[:120],
                "vod_pic": pic,
                "vod_remarks": dur or info,
                "style": {"type": "rect", "ratio": 1.78},
            })
        return videos

    def _pagecount(self, html_text):
        html_text = html_text or ""
        i = html_text.rfind('class="pagination"')
        seg = html_text[i:i + 8000] if i > 0 else html_text
        pages = []
        for m in re.finditer(r'/page/(\d+)(?:/|\.html)', seg):
            try:
                pages.append(int(m.group(1)))
            except Exception:
                pass
        return max(pages) if pages else 1

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        cid = str(tid or "").strip().strip("/")
        if page == 1:
            url = "%s/vodtype/%s.html" % (self.host, cid)
        else:
            url = "%s/vod/show/id/%s/page/%d.html" % (self.host, cid, page)
        html_text = self._fetch(url)
        videos = self._list(html_text) if html_text else []
        pagecount = self._pagecount(html_text) if html_text else page
        if page > 1 and not videos:
            first = self._fetch("%s/vodtype/%s.html" % (self.host, cid))
            pagecount = self._pagecount(first) if first else 1
        return {"list": videos, "page": page, "pagecount": max(1, pagecount),
                "limit": len(videos) or 20,
                "total": pagecount * 20 if pagecount > 1 else len(videos)}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        q = quote(str(key or "").strip())
        if page == 1:
            url = "%s/vod/search.html?wd=%s" % (self.host, q)
        else:
            url = "%s/vod/search/page/%d/wd/%s.html" % (self.host, page, q)
        html_text = self._fetch(url)
        videos = self._list(html_text) if html_text else []
        pagecount = self._pagecount(html_text) if html_text else page
        return {"list": videos, "page": page, "pagecount": max(1, pagecount),
                "limit": len(videos) or 20,
                "total": pagecount * 20 if pagecount > 1 else len(videos)}

    # ---------------- 详情 ----------------
    @staticmethod
    def _player_info(html_text):
        m = re.search(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', html_text or "")
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def _api_route(self, html_text):
        info = self._player_info(html_text)
        b64 = info.get("url") or ""
        if b64:
            try:
                data = json.loads(base64.b64decode(b64).decode("utf-8", "ignore"))
                ss = data.get("ss") or []
                if ss and isinstance(ss[0], (list, tuple)) and len(ss[0]) > 1:
                    return str(ss[0][1])
            except Exception:
                pass
        m = re.search(r'["\'](/api/v/[a-zA-Z0-9_-]+)["\']', html_text or "")
        return m.group(1) if m else ""

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0] if isinstance(ids, list) else ids
        path = vid if str(vid).startswith("/") else "/" + str(vid)
        url = self.host + path
        html_text = self._fetch(url)
        if not html_text:
            return {"list": []}

        tm = re.search(r'<h1[^>]*class="[^"]*movie-play-title[^"]*"[^>]*>([\s\S]*?)</h1>', html_text)
        if not tm:
            tm = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html_text)
        title = _clean(tm.group(1)) if tm else SITE_NAME

        info = self._player_info(html_text)
        vod_data = info.get("vod_data") or {}

        meta = {}
        mm = re.search(r'<div class="movie-meta">([\s\S]*?)</div>', html_text)
        if mm:
            for span in re.findall(r'<span[^>]*class="[^"]*meta-item[^"]*"[^>]*>([\s\S]*?)</span>', mm.group(1)):
                text = _clean(span)
                if "：" in text or ":" in text:
                    k, v = re.split(r"[：:]", text, 1)
                    meta[_clean(k)] = _clean(v)

        type_name = meta.get("类型") or _clean(vod_data.get("vod_class") or "")
        year = meta.get("年份") or ""
        area = meta.get("地区") or ""

        pic = ""
        pm = re.search(r'var\s+video_poster_url\s*=\s*"([^"]+)"', html_text)
        if pm:
            pic = pm.group(1).replace("\\/", "/")

        desc = ""
        dm = re.search(r'<div class="details-content">([\s\S]*?)</div>', html_text)
        if dm:
            desc = _clean(dm.group(1))

        date = ""
        dm2 = re.search(r'<span>\s*日期\s*:\s*</span>\s*<span[^>]*>([^<]+)</span>', html_text)
        if dm2:
            date = _clean(dm2.group(1))

        actors = []
        am = re.search(r'<span>\s*主演\s*:\s*</span>([\s\S]*?)</div>', html_text)
        if am:
            for a in re.findall(r'<a[^>]*>([^<]+)</a>', am.group(1)):
                name = _clean(a)
                if name and name not in actors:
                    actors.append(name)
        for a in [x.strip() for x in str(vod_data.get("vod_actor") or "").split(",") if x.strip()]:
            if a not in actors:
                actors.append(a)
        director = _clean(vod_data.get("vod_director") or "")

        api_route = self._api_route(html_text)
        if api_route:
            token = base64.b64encode(("api|%s|%s" % (self.host, api_route)).encode("utf-8")).decode("ascii")
            play_url = "正片$%s" % token
        else:
            play_url = "正片$%s" % base64.b64encode(("page|%s" % url).encode("utf-8")).decode("ascii")

        remark = date
        if year and date and re.match(r"\d{1,2}月\d{1,2}日", date):
            m2 = re.match(r"(\d{1,2})月(\d{1,2})日", date)
            remark = "%s-%02d-%02d" % (year, int(m2.group(1)), int(m2.group(2)))

        return {"list": [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remark,
            "vod_actor": " / ".join(actors),
            "vod_director": director,
            "vod_content": desc,
            "vod_play_from": "肉视频",
            "vod_play_url": play_url,
        }]}

    # ---------------- 播放 ----------------
    def _resolve_video(self, token):
        raw = str(token or "").strip()
        if "$" in raw:
            raw = raw.split("$")[-1].strip()
        raw = unquote(raw)
        try:
            decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8", "ignore")
        except Exception:
            decoded = ""
        if decoded.startswith("api|"):
            _, host, route = decoded.split("|", 2)
            key = host + route
            cached = self._stream_cache.get(key)
            if cached and cached[1] > time.time():
                return cached[0]
            try:
                r = self._get(host + route)
                data = r.json()
                video_url = ((data.get("video") or {}).get("videoUrl") or "").strip()
                if video_url:
                    self._stream_cache[key] = (video_url, time.time() + 1800)
                    return video_url
            except Exception:
                pass
        if decoded.startswith("page|"):
            page_url = decoded.split("|", 1)[1]
            html_text = self._fetch(page_url)
            route = self._api_route(html_text)
            if route:
                try:
                    r = self._get(self.host + route)
                    return ((r.json().get("video") or {}).get("videoUrl") or "").strip()
                except Exception:
                    pass
        return ""

    def playerContent(self, flag, id, vipFlags=None):
        url = self._resolve_video(id)
        if not url:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}
        # 真实播放地址是 /api/hls/xxx（HLS 清单但没有 .m3u8 后缀），
        # 走插件本地代理：地址以 .m3u8 结尾，清单/分片都由插件带 UA/Referer 拉取。
        try:
            port = _ensure_hls_server()
            local_url = "%s/local.m3u8?u=%s" % (_hls_base(port), _b64url(url))
            return {"parse": 0, "playUrl": "", "url": local_url, "header": {}}
        except Exception:
            pass
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {
                "User-Agent": UA,
                "Referer": self.host + "/",
            },
        }

    def localProxy(self, param):
        return None

    def action(self, action=None):
        return {"msg": "ok"}

    def liveContent(self):
        return ""
