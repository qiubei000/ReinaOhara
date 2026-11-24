# coding=utf-8
#!/usr/bin/python
"""
神秘电影 (sm) —— 自动换域名版

结构 (2026-11-21 实测):
  - 入口 sm65.top 已废, 跳转链: sm65.top -> saodns.com:9527 -> 随机子域导航页
    (sd41/42/43/45/47.vip), 导航页 vip.js 里明文写着当前线路池:
    fab = 导航域 (smdy51/52.vip), luo = 内容域 (sm247~sm269.vip)。
  - 内容域是泛解析: https://任意6位.sm250.vip/ 就能进, 前缀随便编。
  - 列表页服务端渲染: <a class="vodbox" href="/vid/{id}.html">,
    标题被 XOR 128 混淆放在 document.write(l('...')) 里, 本文件已内置解码。
  - 播放页明文: bfz = https://38.je:38/{id}/index.m3u8,
    但 CDN 有防盗链: 不带 Referer 返回 404, 必须带站点 Referer。

自动换域名:
  1. 内置种子线路并发测活, 第一个活的当选 (冷启动快);
  2. 种子全灭才去导航页 vip.js 拉最新线路池再测;
  3. 请求中途失败自动作废当前域名并切换重试。
"""
import html as html_lib
import json
import random
import re
import string
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests

sys.path.append("..")
from base.spider import Spider  # noqa: E402


class Spider(Spider):

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0.0.0 Safari/537.36")

    PLAY_CDN = "https://38.je:38"
    PIC_CDN = "https://36.je:36"

    # 导航页域名 (拉最新线路池用)
    NAV_BASES = ["sd41.vip", "sd42.vip", "sd43.vip", "sd45.vip", "sd47.vip",
                 "smdy51.vip", "smdy52.vip"]
    # 2026-11-21 从 vip.js 解出的内容域种子池
    SEED_BASES = ["sm250", "sm251", "sm253", "sm254", "sm255", "sm256",
                  "sm257", "sm258", "sm259", "sm260", "sm261", "sm262",
                  "sm263", "sm247", "sm248", "sm266", "sm267", "sm268", "sm269"]

    CLASSES = [
        {"type_id": "home", "type_name": "首页"},
        {"type_id": "1", "type_name": "国产"},
        {"type_id": "2", "type_name": "日本"},
        {"type_id": "3", "type_name": "韩国"},
        {"type_id": "4", "type_name": "欧美"},
        {"type_id": "5", "type_name": "三级"},
        {"type_id": "6", "type_name": "动漫"},
    ]

    def getName(self):
        return "神秘电影"

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.UA})
        self.host = None
        self.host_bad = set()
        self.custom_host = None
        # 泛解析前缀: 每次运行随机一个 6 位, 所有内容域共用
        self.prefix = "".join(random.choice(string.ascii_lowercase + string.digits)
                              for _ in range(6))
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict) and cfg.get("host"):
                    self.custom_host = cfg["host"].rstrip("/")
            except Exception:
                if str(extend).startswith("http"):
                    self.custom_host = str(extend).rstrip("/")

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    # ---------- 工具 ----------

    @staticmethod
    def _xor(text):
        """站点文字混淆: 每字符 XOR 128 (导航页是 129, 站内是 128)"""
        return "".join(chr(128 ^ ord(c)) for c in text)

    def _host_of(self, base):
        return "https://%s.%s.vip" % (self.prefix, base)

    def _get(self, url, timeout=12, **kw):
        r = self.session.get(url, timeout=timeout, verify=False, **kw)
        r.encoding = "utf-8"
        if r.status_code != 200:
            raise ValueError("http %s" % r.status_code)
        return r.text

    def _post(self, url, data, timeout=12):
        r = self.session.post(url, data=data, timeout=timeout, verify=False)
        r.encoding = "utf-8"
        if r.status_code != 200:
            raise ValueError("http %s" % r.status_code)
        return r.text

    # ---------- 域名池 ----------

    def _publish_bases(self):
        """去导航页拉 vip.js, 解出最新内容域池 (luo 数组)"""
        for nav in self.NAV_BASES:
            try:
                url = "https://%s.%s/vip.js" % (self.prefix, nav)
                js = self._get(url, timeout=8)
                m = re.search(r"var luo=\[([^\]]+)\]", js)
                if m:
                    bases = re.findall(r"'([a-z0-9]+)'", m.group(1))
                    if bases:
                        return bases
            except Exception:
                continue
        return []

    def _host_alive(self, host, timeout=4):
        try:
            r = requests.get(host + "/", timeout=timeout, verify=False, stream=True,
                             headers={"User-Agent": self.UA})
            if r.status_code != 200:
                return False
            chunk = b""
            for part in r.iter_content(chunk_size=8192):
                chunk += part
                if len(chunk) >= 16384:
                    break
            r.close()
            return b"vodbox" in chunk or b"sm.js" in chunk or b"vodlist" in chunk
        except Exception:
            return False

    def _probe_first_alive(self, hosts):
        cands = [h for h in dict.fromkeys(hosts) if h not in self.host_bad]
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
        first = []
        if self.custom_host:
            first.append(self.custom_host)
        first += [self._host_of(b) for b in self.SEED_BASES]
        host = self._probe_first_alive(first)
        if host:
            self.host = host
            return host
        # 种子全灭: 域名又轮换了, 去导航页拉最新池
        host = self._probe_first_alive([self._host_of(b) for b in self._publish_bases()])
        if host:
            self.host = host
            return host
        self.host = first[0] if first else self._host_of(self.SEED_BASES[0])
        return self.host

    def _fetch(self, path, post_data=None):
        last_err = None
        for _ in range(2):
            host = self._ensure_host()
            try:
                if post_data is not None:
                    page = self._post(host + path, post_data, timeout=15)
                else:
                    page = self._get(host + path, timeout=15)
                if "vodbox" in page or "bfz" in page or "document.title" in page:
                    return page
                raise ValueError("bad content")
            except Exception as e:
                last_err = e
                if host:
                    self.host_bad.add(host)
                self.host = None
        raise RuntimeError("所有域名均不可用: %s" % last_err)

    # ---------- 列表解析 ----------

    def _decode_l(self, chunk):
        m = re.search(r"document\.write\(l\('([^']+)'\)\)", chunk)
        if not m:
            m = re.search(r'document\.write\(l\("([^"]+)"\)\)', chunk)
        if not m:
            return ""
        try:
            return html_lib.unescape(self._xor(m.group(1))).strip()
        except Exception:
            return ""

    def _parse_list(self, page):
        vods = []
        if not page:
            return vods
        parts = re.split(r'<a class="vodbox" href="/vid/(\d+)\.html">', page)
        # split 后奇数位是 id, 偶数位是其后的内容块
        for i in range(1, len(parts) - 1, 2):
            vid, chunk = parts[i], parts[i + 1][:1200]
            mp = re.search(r'data-src="([^"]+)"', chunk)
            pic = mp.group(1) if mp else "%s/%s.jpg" % (self.PIC_CDN, vid)
            name = self._decode_l(chunk) or ("视频 " + vid)
            vods.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return vods

    @staticmethod
    def _pagecount(page, pg):
        nums = [int(x) for x in re.findall(r'/list/\d+/(\d+)\.html', page)]
        nums += [int(x) for x in re.findall(r'/so/[^"]+/(\d+)\.html', page)]
        return max(nums) if nums else (pg + 1)

    # ---------- TVBox 接口 ----------

    def homeContent(self, filter):
        return {"class": self.CLASSES, "list": []}

    def homeVideoContent(self):
        try:
            return {"list": self._parse_list(self._fetch("/"))}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if tid == "home":
            path = "/" if pg <= 1 else "/list/1/%d.html" % pg
        elif pg <= 1:
            path = "/list/%s.html" % tid
        else:
            path = "/list/%s/%d.html" % (tid, pg)
        try:
            page = self._fetch(path)
            vods = self._parse_list(page)
            pagecount = self._pagecount(page, pg)
        except Exception:
            vods, pagecount = [], pg
        return {"list": vods, "page": pg, "pagecount": pagecount,
                "limit": len(vods), "total": 999999}

    def detailContent(self, ids):
        vid = str(ids[0])
        vod = {"vod_id": vid, "vod_name": "", "vod_pic": "%s/%s.jpg" % (self.PIC_CDN, vid),
               "type_name": "神秘电影"}
        try:
            page = self._fetch("/vid/%s.html" % vid)
            # document.title=l("..正在播放.."+ "标题") + "-" + l("神秘电影"): 取最长一段当标题
            segs = []
            mt = re.search(r"document\.title\s*=\s*l\((.*?)\)\s*\+", page, re.S)
            if mt:
                for q in re.findall(r'"([^"]+)"', mt.group(1)):
                    try:
                        segs.append(self._xor(q))
                    except Exception:
                        pass
            title = max(segs, key=len) if segs else ""
            vod["vod_name"] = title or ("视频 " + vid)
            vod["vod_play_from"] = "神秘电影"
            vod["vod_play_url"] = "播放$" + vid
        except Exception as e:
            vod["vod_name"] = "加载失败: %s" % e
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        vid = str(id)
        host = self._ensure_host()
        return {
            "parse": 0,
            "url": "%s/%s/index.m3u8" % (self.PLAY_CDN, vid),
            # CDN 防盗链: 必须带站点 Referer, 否则 404
            "header": {"User-Agent": self.UA,
                       "Referer": "%s/vid/%s.html" % (host, vid)},
        }

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        try:
            if pg <= 1:
                page = self._fetch("/so.html", post_data={"wd": key})
            else:
                page = self._fetch("/so/%s/%d.html" % (quote(key), pg))
            vods = self._parse_list(page)
            pagecount = self._pagecount(page, pg)
        except Exception:
            vods, pagecount = [], pg
        return {"list": vods, "page": pg, "pagecount": pagecount,
                "limit": len(vods), "total": 999999}

    def isVideoFormat(self, url):
        return url.endswith(".m3u8") or url.endswith(".mp4")

    def manualVideoCheck(self):
        return False
