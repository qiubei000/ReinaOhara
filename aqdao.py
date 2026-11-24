# coding=utf-8
#!/usr/bin/python
"""
爱情岛论坛 (aqdlt) —— 自动换域名版

原理:
  1. 站点页面是混淆下发的 (crypt_html_js), 解法固定:
     html 变量先整体反转, 再 decodeURIComponent, 即 unquote(html[::-1])。
  2. 域名池两个来源, 失效自动切换:
     a. 发布页 http://s515i.com/ 的跳转脚本里下发的当前线路
        (vip.aqdmNNN.com:20844 + 38.148.206.x:30019 备用 IP 线);
     b. 内置种子域名 (2026-11-21 实测可用), 发布页挂了时兜底。
  3. 每次请求失败或返回内容不对, 自动作废当前域名, 按
     发布页最新池 -> 种子池 的顺序逐个测活, 第一个能出列表的当选。
  4. 列表/分类/搜索都是服务端渲染 HTML, 播放页里有明文
     let video_url = 'https://cdn.aqd-tv.com/.../xxx.m3u8', 直接播。

extend 用法 (可选):
  - 不填: 全自动
  - 填一个 http(s) 地址: 作为最高优先级的自定义域名
  - 填 JSON: {"host": "https://vip.aqdm831.com:20844", "publish": "http://s515i.com/"}
"""
import html as html_lib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote

import requests

sys.path.append("..")
from base.spider import Spider  # noqa: E402


class Spider(Spider):

    # ---------- 基础配置 ----------

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0.0.0 Safari/537.36")

    PUBLISH_URL = "http://s515i.com/"

    # 2026-11-21 从发布页解出并逐个测活的种子池 (发布页刷新会覆盖/补充)
    SEED_HOSTS = [
        "https://vip.aqdm831.com:20844",
        "https://vip.aqdm843.com:20844",
        "https://vip.aqdm835.com:20844",
        "https://vip.aqdm868.com:20844",
        "https://vip.aqdm852.com:20844",
        "https://vip.aqdm862.com:20844",
        "https://vip.aqdm881.com:20844",
        "https://vip.aqdm840.com:20844",
        "https://vip.aqdm834.com:20844",
        "https://vip.aqdm807.com:20844",
        "https://38.148.206.7:30019",
        "https://38.148.206.8:30019",
        "https://38.148.206.9:30019",
        "https://38.148.206.15:30019",
        "https://38.148.206.16:30019",
        "https://38.148.206.17:30019",
        "https://38.148.206.23:30019",
        "https://38.148.206.24:30019",
        "https://38.148.206.25:30019",
    ]

    CLASSES = [
        {"type_id": "home", "type_name": "首页推荐"},
        {"type_id": "cn", "type_name": "中国大陆"},
        {"type_id": "west", "type_name": "欧美"},
        {"type_id": "jp", "type_name": "日本"},
        {"type_id": "kr", "type_name": "韩国"},
        {"type_id": "hk", "type_name": "中国香港"},
        {"type_id": "tw", "type_name": "中国台湾"},
        {"type_id": "southeast-asia", "type_name": "东南亚"},
    ]

    def getName(self):
        return "爱情岛论坛"

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.UA})
        self.host = None            # 当前在用域名
        self.host_bad = set()       # 本次运行内已判死的域名
        self._url_cache = {}        # 详情页顺手缓存的播放地址, 免得播放时再抓一遍
        self.publish_url = self.PUBLISH_URL
        self.custom_host = None
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict):
                    self.custom_host = cfg.get("host") or None
                    self.publish_url = cfg.get("publish") or self.publish_url
            except Exception:
                if str(extend).startswith("http"):
                    self.custom_host = str(extend).rstrip("/")

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    # ---------- 混淆解码 / 基础请求 ----------

    @staticmethod
    def _decode(text):
        """站点所有页面都是 crypt 混淆下发: 反转 + unquote 还原真实 HTML"""
        if not text:
            return ""
        if "crypt_html_js" in text or "var html =" in text:
            m = re.search(r"var html = '([\s\S]*?)';", text)
            if m:
                try:
                    return unquote(m.group(1)[::-1])
                except Exception:
                    return text
        return text

    def _raw_get(self, url, timeout=12):
        r = self.session.get(url, timeout=timeout, verify=False,
                             headers={"Referer": url.split("/")[0] + "//" + url.split("/")[2] + "/"})
        r.encoding = "utf-8"
        return r

    def _get_html(self, url, timeout=12):
        r = self._raw_get(url, timeout=timeout)
        if r.status_code != 200:
            raise ValueError("http %s" % r.status_code)
        return self._decode(r.text)

    # ---------- 域名池: 发布页刷新 + 测活 + 自动切换 ----------

    def _publish_hosts(self):
        """走 s515i.com 的跳转链, 从最终线路页里解出当前域名池"""
        hosts = []
        try:
            r = self._raw_get(self.publish_url, timeout=8)
            text = r.text or ""
            # 第一跳是 JS: location.replace("https://cross.301jump.com:8989?u=" + (location.protocol+"//"+location.host))
            m = re.search(r'location\.replace\("([^"]+?)\?u="', text)
            if m:
                jump = m.group(1) + "?u=http://" + self.publish_url.split("/")[2]
                for _ in range(2):  # 中转站偶尔拒连, 重试一次
                    try:
                        r2 = self._raw_get(jump, timeout=8)  # 自动跟 302 到线路页
                        if r2.text:
                            text = r2.text
                            break
                    except Exception:
                        continue
            text = self._decode(text).replace("\\/", "/")
            hosts += re.findall(r"https://vip\.aqdm\d+\.com:20844", text)
            hosts += re.findall(r"https://38\.148\.206\.\d+:30019", text)
        except Exception:
            pass
        # 去重保序
        seen, out = set(), []
        for h in hosts:
            if h not in seen:
                seen.add(h)
                out.append(h)
        return out

    def _host_alive(self, host, timeout=4):
        """轻量测活: 流式只读开头一小段, 命中混淆标记就算活, 不下整页"""
        try:
            r = requests.get(host + "/", timeout=timeout, verify=False, stream=True,
                             headers={"User-Agent": self.UA})
            if r.status_code != 200:
                return False
            chunk = next(r.iter_content(chunk_size=8192), b"")
            r.close()
            return b"crypt_html_js" in chunk or b"aqdm" in chunk or "爱情岛".encode("utf-8") in chunk
        except Exception:
            return False

    def _probe_first_alive(self, candidates):
        """并发测活: 全部一起测, 第一个活的立即当选 (冷启动提速的关键)"""
        cands = [h for h in dict.fromkeys(candidates) if h not in self.host_bad]
        if not cands:
            return None
        ex = ThreadPoolExecutor(max_workers=min(10, len(cands)))
        try:
            futs = {ex.submit(self._host_alive, h): h for h in cands}
            for f in as_completed(futs, timeout=12):
                try:
                    if f.result():
                        return futs[f]
                except Exception:
                    continue
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)
        return None

    def _ensure_host(self):
        if self.host:
            return self.host
        # 1) 先并发测内置种子池: 通常一两秒就能选出可用域名
        first = []
        if self.custom_host:
            first.append(self.custom_host.rstrip("/"))
        first += self.SEED_HOSTS
        host = self._probe_first_alive(first)
        if host:
            self.host = host
            return host
        # 2) 种子全灭才说明域名又轮换了: 去发布页拉最新池再并发测
        host = self._probe_first_alive(self._publish_hosts())
        if host:
            self.host = host
            return host
        # 3) 全军覆没时也给个默认, 让上层拿到明确报错而不是崩溃
        self.host = first[0] if first else self.SEED_HOSTS[0]
        return self.host

    def _fetch(self, path):
        """带自动换域名的页面抓取: 失败/内容不对就换下一个域名重试一轮"""
        last_err = None
        for _ in range(2):
            host = self._ensure_host()
            try:
                page = self._get_html(host + path, timeout=15)
                if "data-video-id" in page or "video_url" in page or "爱情岛" in page:
                    return page
                raise ValueError("bad content")
            except Exception as e:
                last_err = e
                if host:
                    self.host_bad.add(host)
                self.host = None
        raise RuntimeError("所有域名均不可用: %s" % last_err)

    # ---------- 列表解析 ----------

    def _parse_list(self, page):
        vods = []
        if not page:
            return vods
        chunks = re.split(r'<div class="col-xlg videos-item">', page)[1:]
        for chunk in chunks:
            mid = re.search(r'data-video-id="(\d+)"', chunk)
            if not mid:
                mid = re.search(r'href="/videos/play/(\d+)\.html"', chunk)
            if not mid:
                continue
            vid = mid.group(1)
            mt = re.search(r'class="thumbnail-cover-link"[^>]*alt="([^"]*)"', chunk)
            if not mt:
                mt = re.search(r'alt="([^"]+)"', chunk)
            name = html_lib.unescape(mt.group(1)).strip() if mt else ("视频 " + vid)
            mp = re.search(r'data-original="([^"]+)"', chunk)
            pic = re.sub(r"\s+", "", mp.group(1)) if mp else ""
            mv = re.search(r'class="metadata-view">([^<]*)<', chunk)
            md = re.search(r'class="metadata-view">[^<]*</span>\s*<span>([^<]*)<', chunk)
            remarks = " ".join(x for x in [
                mv.group(1).strip() if mv else "",
                md.group(1).strip() if md else "",
            ] if x)
            vods.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return vods

    # ---------- TVBox 接口 ----------

    def homeContent(self, filter):
        return {"class": self.CLASSES, "list": []}

    def homeVideoContent(self):
        try:
            page = self._fetch("/")
            return {"list": self._parse_list(page)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if tid == "home":
            path = "/" if pg <= 1 else "/videos/index/%d.html" % pg
        elif pg <= 1:
            path = "/videos/category/%s.html" % tid
        else:
            path = "/videos/category/%s/%d.html" % (tid, pg)
        try:
            page = self._fetch(path)
            vods = self._parse_list(page)
        except Exception:
            vods = []
        return {
            "list": vods,
            "page": pg,
            "pagecount": pg + 1 if vods else pg,
            "limit": len(vods),
            "total": 999999,
        }

    def detailContent(self, ids):
        vid = str(ids[0])
        vod = {"vod_id": vid, "vod_name": "", "vod_pic": "", "type_name": "爱情岛论坛"}
        try:
            page = self._fetch("/videos/play/%s.html" % vid)
            mt = re.search(r"<title>(.*?)</title>", page, re.S)
            title = html_lib.unescape(mt.group(1)) if mt else ""
            title = re.sub(r"^如遇到打不开，请输入域名：\S+\s*", "", title)
            title = re.sub(r"\s*-\s*爱情岛论坛.*$", "", title).strip()
            vod["vod_name"] = title or ("视频 " + vid)
            mp = re.search(r'property="og:image" content="([^"]+)"', page)
            if mp:
                vod["vod_pic"] = re.sub(r"\s+", "", mp.group(1))
            md = re.search(r'name="description" content="([^"]*)"', page)
            if md:
                vod["vod_content"] = html_lib.unescape(md.group(1))
            vod["vod_play_from"] = "爱情岛"
            vod["vod_play_url"] = "播放$" + vid
            mv = re.search(r"let video_url = '([^']+)'", page)
            if mv:
                self._url_cache[vid] = mv.group(1)
        except Exception as e:
            vod["vod_name"] = "加载失败: %s" % e
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = self._url_cache.get(str(id), "")
        if not url:
            try:
                page = self._fetch("/videos/play/%s.html" % id)
                m = re.search(r"let video_url = '([^']+)'", page)
                if not m:
                    m = re.search(r"(https?://[^\s'\"]+?\.m3u8[^\s'\"]*)", page)
                if m:
                    url = m.group(1)
                    self._url_cache[str(id)] = url
            except Exception:
                url = ""
        host = self._ensure_host()
        return {
            "parse": 0,
            "url": url,
            "header": {"User-Agent": self.UA, "Referer": host + "/"},
        }

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        path = "/videos/search.html?key=%s&page=%d" % (quote(key), pg)
        try:
            page = self._fetch(path)
            vods = self._parse_list(page)
        except Exception:
            vods = []
        return {
            "list": vods,
            "page": pg,
            "pagecount": pg + 1 if vods else pg,
            "limit": len(vods),
            "total": 999999,
        }

    def isVideoFormat(self, url):
        return url.endswith(".m3u8") or url.endswith(".mp4")

    def manualVideoCheck(self):
        return False
