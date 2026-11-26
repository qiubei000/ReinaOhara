# coding=utf-8
# 4KHD https://www.4khd.com/ — HD Beautiful Girls 图集站
# WordPress 站：列表走 HTML（轻量），详情走 WP REST API（干净）
# 每套图集是图片集（不是视频）：详情点开用 pics:// 看图，
# 原图下载走 TeraBox 链接，解压密码 4KHD（站内写明）

import html as _html
import json
import re
from urllib.parse import quote, urljoin

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object


class Spider(BaseSpider):
    host = "https://www.4khd.com"
    api = "https://www.4khd.com/wp-json/wp/v2"

    cate_list = [
        {"type_id": "home", "type_name": "🆕 最新更新"},
        {"type_id": "pages/popular", "type_name": "🔥 热门"},
        {"type_id": "pages/cosplay", "type_name": "🎭 Cosplay"},
        {"type_id": "pages/album", "type_name": "📚 全部图集"},
    ]

    def init(self, extend=""):
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def homeContent(self, filter):
        return {"class": self.cate_list}

    def homeVideoContent(self):
        return self._get_list(self.host + "/", "1")

    def categoryContent(self, tid, pg, filter, extend):
        if not pg or str(pg) in ("0", "None"):
            pg = "1"
        pg = str(pg)
        tid = str(tid).strip()
        if tid == "home":
            base = self.host + "/"
        else:
            base = f"{self.host}/{tid.strip('/')}"
        if pg == "1":
            url = base
        else:
            url = base + ("?query-3-page=" + pg if "?" not in base else "&query-3-page=" + pg)
        return self._get_list(url, pg)

    def searchContent(self, key, quick, pg="1"):
        if not pg or str(pg) in ("0", "None"):
            pg = "1"
        pg = str(pg)
        q = quote(key)
        url = f"{self.host}/search/{q}"
        if pg != "1":
            url += "?query-3-page=" + pg
        try:
            return self._get_list(url, pg)
        except Exception:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        vid = str(ids[0]).strip()
        if vid.startswith("http"):
            m = re.search(r"/content/\d+/([^/]+)\.html", vid)
            vid = m.group(1) if m else vid
        if not vid.isdigit():
            # slug 形式：用搜索 API 按 slug 取 id
            try:
                data = self._api_json(f"{self.api}/posts?slug={quote(vid)}")
                if data:
                    vid = str(data[0]["id"])
                else:
                    return {"list": []}
            except Exception:
                return {"list": []}
        try:
            post = self._api_json(f"{self.api}/posts/{vid}")
        except Exception:
            return {"list": []}
        if not post or isinstance(post, list):
            return {"list": []}

        title = self._clean(post.get("title", {}).get("rendered", "") or vid)
        date = str(post.get("date", ""))[:10]
        content = post.get("content", {}).get("rendered", "") or ""
        imgs = self._extract_images(content)
        tera = re.findall(r"https://m\.4khd\.com/[A-Za-z0-9]+", content)
        tera = tera[0] if tera else ""
        cats = post.get("categories", []) or []
        cat_name = {21: "热门", 4: "Cosplay", 3: "Photo", 26: "Bare", 9: "Misc"}.get(cats[0], "") if cats else ""
        size = ""
        sm = re.search(r"\[([^\]]+)\]", title)
        if sm:
            size = sm.group(1)
        remarks = " · ".join(x for x in [size, f"{len(imgs)}张", date] if x)
        desc_parts = []
        if tera:
            desc_parts.append(f"原图下载(TeraBox): {tera}")
            desc_parts.append("解压密码: 4KHD")
        if cat_name:
            desc_parts.append(f"分类: {cat_name}")
        desc_parts.append(title)
        vod = {
            "vod_id": str(post.get("id", vid)),
            "vod_name": title,
            "vod_pic": imgs[0] if imgs else (post.get("jetpack_featured_media_url") or ""),
            "type_name": cat_name or "图集",
            "vod_year": date[:4],
            "vod_area": "网络",
            "vod_remarks": remarks,
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "\n".join(desc_parts),
            "vod_play_from": "图集",
            "vod_play_url": f"查看图集${vid}",
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        vid = str(id or "").strip()
        if vid.startswith("http"):
            imgs = [vid]
        else:
            try:
                post = self._api_json(f"{self.api}/posts/{vid}")
                imgs = self._extract_images(post.get("content", {}).get("rendered", "") or "") if post else []
            except Exception:
                imgs = []
        if not imgs:
            # 兜底：抓详情 HTML
            try:
                html = self.fetch(f"{self.host}/?p={vid}")
                imgs = self._extract_images(html or "")
            except Exception:
                imgs = []
        if not imgs:
            return {"parse": 0, "url": "", "msg": "没有解析到图片"}
        return {
            "parse": 0,
            "url": "pics://" + "&&".join(imgs),
            "header": {
                "User-Agent": self.header["User-Agent"],
                "Referer": self.host + "/",
            },
        }

    def isVideoFormat(self, url):
        u = str(url or "")
        return u.startswith("pics://") or ".jpg" in u or ".webp" in u or ".png" in u or ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    # ---------- 内部 ----------

    def fetch(self, url):
        try:
            if hasattr(self, "net") and self.net:
                r = self.net.get(url, headers=self.header)
                if isinstance(r, str):
                    return r
                if hasattr(r, "text"):
                    return r.text
                return str(r)
        except Exception:
            pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self.header)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _api_json(self, url):
        raw = self.fetch(url)
        if not raw:
            return None
        return json.loads(raw)

    def _clean(self, s):
        s = re.sub(r"<[^>]+>", "", s or "")
        return _html.unescape(s).strip()

    def _extract_images(self, content):
        imgs = []
        seen = set()
        for u in re.findall(r"https://i\d\.wp\.com/pic\.4khd\.com/[^\"'\\\s]+?\.webp", content or ""):
            base = u.split("?")[0]
            if "4KHD-beautifulGirls" in base:
                continue
            if base in seen:
                continue
            seen.add(base)
            imgs.append(base)
        return imgs

    def _get_list(self, url, pg="1"):
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 12, "total": 0}
        items = []
        seen = set()
        for block in re.findall(r'<li class="wp-block-post post-(\d+)[^"]*"([\s\S]*?)</li>', html):
            pid, body = block[0], block[1]
            if pid in seen:
                continue
            seen.add(pid)
            link = ""
            lm = re.search(r'href="(https://www\.4khd\.com/content/[^"]+)"', body)
            if lm:
                link = lm.group(1)
            title = ""
            tm = re.search(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h2>", body, re.S)
            if tm:
                title = self._clean(tm.group(1))
            if not title:
                continue
            pic = ""
            pm = re.search(r'<img[^>]+src="(https://i\d\.wp\.com/[^"]+)"', body)
            if pm:
                pic = pm.group(1).split("?")[0]
            date = ""
            dm = re.search(r'<time datetime="([^"]+)"', body)
            if dm:
                date = dm.group(1)[:10]
            views = ""
            vm = re.search(r'eyeicon"></div>\s*([0-9,]+)', body)
            if vm:
                views = vm.group(1) + " 浏览"
            remarks = " · ".join(x for x in [date, views] if x)
            items.append({
                "vod_id": pid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        pagecount = 1
        pages = re.findall(r"query-3-page=(\d+)", html)
        if pages:
            try:
                pagecount = max(int(p) for p in pages if p.isdigit())
            except Exception:
                pagecount = 10
        return {
            "list": items,
            "page": int(pg),
            "pagecount": max(pagecount, 1),
            "limit": 12,
            "total": max(pagecount, 1) * 12,
        }
