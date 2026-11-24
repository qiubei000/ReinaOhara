# coding=utf-8
"""
XNXX 源 (影视/TVBox Python 接口)

- 列表页服务端渲染, 正则解析 thumb-block
- 播放页提取 html5player 的 setVideoHLS 签名 m3u8 (多码率), 无 HLS 时回退 MP4
- 播放时现取签名地址, 避免列表/详情缓存导致链接过期
- 多域名并发探测 + 会话中自动换线 (xnxx.com / xnxx.gold)
"""
import re
import sys
import html as html_lib
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.append("..")
from base.spider import Spider

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SEED_HOSTS = [
    "https://www.xnxx.com",
    "https://www.xnxx.gold",
    "https://xnxx.com",
]

CLASSES = [
    {"type_id": "todays-selection", "type_name": "今日精选"},
    {"type_id": "hits", "type_name": "热门"},
    {"type_id": "best", "type_name": "本月最佳"},
    {"type_id": "s:chinese", "type_name": "中国"},
    {"type_id": "s:asian", "type_name": "亚洲"},
    {"type_id": "s:japanese", "type_name": "日本"},
    {"type_id": "s:korean", "type_name": "韩国"},
    {"type_id": "s:taiwan", "type_name": "台湾"},
    {"type_id": "s:hong_kong", "type_name": "香港"},
    {"type_id": "s:amateur", "type_name": "素人"},
    {"type_id": "s:homemade", "type_name": "自拍"},
    {"type_id": "s:stockings", "type_name": "丝袜"},
    {"type_id": "s:massage", "type_name": "按摩"},
]


class Spider(Spider):
    def getName(self):
        return "XNXX"

    # ---------------- 基础网络层 ----------------
    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.host = self._pick_host()

    def _probe(self, host):
        try:
            r = self.session.get(host + "/todays-selection",
                                 timeout=8, verify=False)
            if r.status_code == 200 and "thumb-block" in r.text:
                return host
        except Exception:
            pass
        return None

    def _pick_host(self):
        ex = ThreadPoolExecutor(max_workers=len(SEED_HOSTS))
        try:
            futures = {ex.submit(self._probe, h): h for h in SEED_HOSTS}
            for fut in as_completed(futures):
                host = fut.result()
                if host:
                    return host
        finally:
            ex.shutdown(wait=False)
        return SEED_HOSTS[0]

    def _fetch(self, path):
        """带自动换线的 GET: 当前 host 失败就轮换其他 seed 重试。"""
        hosts = [self.host] + [h for h in SEED_HOSTS if h != self.host]
        for host in hosts:
            for _ in range(2):
                try:
                    r = self.session.get(host + path, timeout=15, verify=False)
                    if r.status_code == 200 and r.text:
                        self.host = host
                        return r.text
                except Exception:
                    pass
        return ""

    # ---------------- 列表解析 ----------------
    def _parse_list(self, page_html):
        # 站点有两套列表标记 (id="video-thumb-…" 与 id="video_…"),
        # 统一按 id="video 切块, 每块取首个视频链接/标题/封面
        videos = []
        seen = set()
        blocks = re.split(r'id="video', page_html)[1:]
        for block in blocks:
            m = re.search(r'href="(/video-[^"]+)"', block)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            title = ""
            mt = re.search(r'<a[^>]+href="/video-[^"]+"[^>]+title="([^"]+)"', block)
            if mt:
                title = mt.group(1)
            if not title:
                mt = re.search(r'<img[^>]+alt="([^"]+)"', block)
                title = mt.group(1) if mt else href
            pic = ""
            mp = re.search(r'data-src="(https://thumb-[^"]+\.jpg)"', block)
            if mp:
                pic = mp.group(1)
            remarks = ""
            md = re.search(r'(\d+\s*h\s*\d+\s*min|\d+\s*min|\d+:\d{2})', block)
            if md:
                remarks = md.group(1).replace(" ", "")
            mq = re.search(r'video-hd">.*?(\d{3,4}p)', block, re.S)
            if mq:
                remarks = (remarks + " " + mq.group(1)).strip()
            videos.append({
                "vod_id": href,
                "vod_name": html_lib.unescape(title).strip(),
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return videos

    def _list_url(self, tid, page):
        if tid.startswith("s:"):
            base = "/search/" + urllib.parse.quote(tid[2:])
        else:
            base = "/" + tid
        if page and int(page) > 1:
            base += "/" + str(int(page) - 1)
        return base

    # ---------------- 接口 ----------------
    def homeContent(self, filter):
        return {"class": CLASSES}

    def homeVideoContent(self):
        page_html = self._fetch("/todays-selection")
        return {"list": self._parse_list(page_html)}

    def categoryContent(self, tid, pg, filter, extend):
        page_html = self._fetch(self._list_url(tid, pg))
        videos = self._parse_list(page_html)
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": 9999,
            "limit": len(videos) or 48,
            "total": 999999,
        }

    def searchContent(self, key, quick, pg="1"):
        path = "/search/" + urllib.parse.quote(key)
        if pg and int(pg) > 1:
            path += "/" + str(int(pg) - 1)
        page_html = self._fetch(path)
        return {"list": self._parse_list(page_html)}

    def detailContent(self, ids):
        vid = ids[0]
        page_html = self._fetch(vid)
        name = ""
        mt = re.search(r"<title>(.*?)\s*-\s*XNXX\.COM</title>", page_html, re.S)
        if mt:
            name = html_lib.unescape(mt.group(1)).strip()
        pic = ""
        mp = re.search(r'property="og:image" content="([^"]+)"', page_html)
        if mp:
            pic = mp.group(1)
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": name,
            "vod_play_from": "XNXX",
            "vod_play_url": "播放$" + vid,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        page_html = self._fetch(id)
        url = ""
        mh = re.search(r"setVideoHLS\('([^']+)'\)", page_html)
        if mh:
            url = mh.group(1)
        if not url:
            mh = re.search(r"setVideoUrlHigh\('([^']+)'\)", page_html)
            if mh:
                url = mh.group(1)
        if not url:
            mh = re.search(r"setVideoUrlLow\('([^']+)'\)", page_html)
            if mh:
                url = mh.group(1)
        return {
            "parse": 0,
            "url": url,
            "header": {
                "User-Agent": UA,
                "Referer": self.host + "/",
            },
        }

    def localProxy(self, param):
        return [404, "text/plain", ""]
