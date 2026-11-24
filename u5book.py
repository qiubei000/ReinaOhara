# coding=utf-8
# 尤物百科 https://u5book.com/
# 分类/UP主与官网对齐 + 封面/播放修复

import re
import time
from urllib.parse import quote, urljoin
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    host = "https://u5book.com"

    # 与官网一致的分类（美化）
    cate_list = [
        {"type_id": "home", "type_name": "🏠 最新更新"},
        {"type_id": "sort/hot", "type_name": "🔥 热门内容"},
        {"type_id": "sort/today", "type_name": "📅 今日精选"},
        {"type_id": "category/twitter", "type_name": "🐦 推特"},
        {"type_id": "category/onlyfans", "type_name": "💋 OnlyFans"},
        {"type_id": "category/tangxin", "type_name": "🍬 糖心Vlog"},
        {"type_id": "category/madou", "type_name": "🎬 麻豆女神"},
        {"type_id": "category/duanju", "type_name": "🎞 尤物短剧"},
        {"type_id": "category/chigua", "type_name": "🍉 尤物吃瓜"},
        {"type_id": "authors", "type_name": "👤 UP主大全"},
        {"type_id": "authors/latest", "type_name": "✨ 最近更新UP"},
        {"type_id": "hots", "type_name": "🔍 尤物热搜"},
        {"type_id": "tags", "type_name": "🏷 尤物标签"},
        {"type_id": "archives", "type_name": "📚 尤物往期"},
    ]

    def init(self, extend=""):
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
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

        # UP 主列表
        if tid in ("authors", "authors/latest"):
            return self._get_authors(tid, pg)

        # 标签云
        if tid == "tags":
            return self._get_tags(pg)

        # 热搜（按热门视频）
        if tid == "hots":
            return self._get_list(f"{self.host}/sort/hot/" if pg == "1" else f"{self.host}/sort/hot/page/{pg}/", pg)

        # 往期：页面无 article，走 JSON-LD / 标题列表
        if tid == "archives":
            return self._get_archives(pg)

        # 单个 UP 主作品 /author/123
        if tid.startswith("author/") or tid.startswith("author_"):
            aid = tid.replace("author_", "author/").split("author/")[-1].strip("/")
            base = f"{self.host}/author/{aid}/"
            url = base if pg == "1" else f"{self.host}/author/{aid}/page/{pg}/"
            return self._get_list(url, pg)

        # 标签 /tag/xxx（中文必须 URL 编码）
        if tid.startswith("tag/"):
            slug = tid[4:].strip("/")
            from urllib.parse import quote
            enc = quote(slug, safe="")
            base = f"{self.host}/tag/{enc}/"
            url = base if pg == "1" else f"{self.host}/tag/{enc}/page/{pg}/"
            return self._get_list(url, pg)

        # 普通分类
        if tid == "home":
            base = self.host + "/"
        else:
            base = f"{self.host}/{tid.strip('/')}/"

        url = base if pg == "1" else urljoin(base if base.endswith("/") else base + "/", f"page/{pg}/")
        return self._get_list(url, pg)

    def searchContent(self, key, quick, pg="1"):
        if not pg or str(pg) in ("0", "None"):
            pg = "1"
        pg = str(pg)
        q = quote(key)
        url = f"{self.host}/search/{q}/" if pg == "1" else f"{self.host}/search/{q}/page/{pg}/"
        try:
            return self._get_list(url, pg)
        except Exception:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        vid = str(ids[0]).strip()

        # 误点文件夹
        if vid.startswith("author") or vid.startswith("tag/"):
            return {"list": []}

        if vid.isdigit():
            url = f"{self.host}/archives/{vid}/"
        elif vid.startswith("http"):
            url = vid
        else:
            url = f"{self.host}/archives/{vid}/"

        html = self.fetch(url)
        if not html:
            return {"list": []}

        title = self._re(r"<title>([^<]+?)(?:\s*-\s*热门|\s*-\s*尤物)", html)
        if not title:
            title = self._re(r"<h1[^>]*>([^<]+)", html) or self._re(r'class="dx-title[^"]*"[^>]*>([^<]+)', html) or vid
        title = re.sub(r"\s+", " ", title).strip()

        pic = self._re(r'thumbnailUrl"\s*:\s*"(https?://[^"]+)"', html) or ""
        if not pic:
            pics = re.findall(r'data-src="(https?://[^"]+\.(?:jpeg|jpg|png|webp)[^"]*)"', html)
            for p in pics:
                if "avatar" in p or "/static/" in p:
                    continue
                pic = p
                break
            if not pic and pics:
                pic = pics[0]

        desc = self._re(r'"description"\s*:\s*"([^"]{10,500})"', html) or ""
        desc = desc.replace("\\n", "\n").replace('\\"', '"').strip()

        actor = ""
        am = re.search(r'href="/author/\d+/"[^>]*>[\s\S]{0,200}?<span[^>]*>([^<]+)</span>', html)
        if am:
            actor = am.group(1).strip()
        if not actor:
            actor = self._re(r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html) or ""

        tags = re.findall(r'href="/category/[^"]+"[^>]*class="[^"]*dx-tag[^"]*"[^>]*>([^<]+)', html)
        type_name = tags[0].strip() if tags else "尤物"

        episodes = self._resolve_play(html, url)
        if episodes:
            play_url = "#".join([f"{n}${u}" for n, u in episodes])
            remarks_extra = f"{len(episodes)}集" if len(episodes) > 1 else ""
        else:
            play_url = f"正片${url}"
            remarks_extra = ""

        vod = {
            "vod_id": vid if vid.isdigit() else (self._re(r"/archives/(\d+)/", url) or vid),
            "vod_name": title,
            "vod_pic": self._proxy_pic(pic),
            "type_name": type_name,
            "vod_year": "",
            "vod_area": "网络",
            "vod_remarks": " · ".join(x for x in [actor, remarks_extra] if x),
            "vod_actor": actor,
            "vod_director": "",
            "vod_content": desc or title,
            "vod_play_from": "线路1",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": id,
            "header": {
                "User-Agent": self.header["User-Agent"],
                "Referer": self.host + "/",
                "Origin": self.host,
            },
        }

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

    def _decode_packer(self, src):
        m = re.search(r"}\('(.+?)',(\d+),(\d+),'(.+?)'\.split\('\|'\)", src, re.S)
        if not m:
            return src
        p, a, c, kstr = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        k = kstr.split("|")
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def encode(n, radix):
            if n == 0:
                return "0"
            s = ""
            while n:
                s = chars[n % radix] + s
                n //= radix
            return s

        mapping = {}
        for i in range(c):
            token = encode(i, a)
            mapping[token] = k[i] if i < len(k) and k[i] else token
        out = p
        for t in sorted(mapping.keys(), key=len, reverse=True):
            out = re.sub(r"\b" + re.escape(t) + r"\b", mapping[t], out)
        return out

    def _resolve_play(self, html, page_url):
        """返回 [(集标题, m3u8), ...]，支持一页多播放器"""
        episodes = []

        # 按 player shell 切分，匹配前方 h2 标题
        parts = re.split(r'(?=<div id="youwu-player-shell-)', html)
        for i, part in enumerate(parts):
            if 'youwu-player-shell-' not in part:
                continue
            prev = parts[i - 1] if i > 0 else ""
            titles = re.findall(r"<h2[^>]*>([^<]+)</h2>", prev)
            title = titles[-1].strip() if titles else ""
            if not title:
                titles = re.findall(r"<h3[^>]*>([^<]+)</h3>", prev)
                title = titles[-1].strip() if titles else ""
            if not title or title in ("提示", "相关推荐", "评论"):
                title = f"第{len(episodes) + 1}集"

            token = ""
            for s in re.findall(r"<script[^>]*>([\s\S]*?)</script>", part):
                if "eval(function" not in s:
                    continue
                if "player" not in s and "api" not in s:
                    continue
                decoded = self._decode_packer(s)
                tm = re.search(r"/api/player/([^/'\"\s]+)/", decoded)
                if tm:
                    token = tm.group(1)
                    break
            if not token:
                continue
            play = self._token_to_m3u8(token, page_url)
            if play:
                episodes.append((title, play))

        # 仅一集时统一叫正片，避免误取正文小标题
        if len(episodes) == 1:
            episodes = [("正片", episodes[0][1])]

        # 整页只有一个播放器时的兜底
        if not episodes:
            token = ""
            for s in re.findall(r"<script[^>]*>([\s\S]*?)</script>", html):
                if "eval(function" not in s:
                    continue
                if "player" not in s and "api" not in s:
                    continue
                decoded = self._decode_packer(s)
                tm = re.search(r"/api/player/([^/'\"\s]+)/", decoded)
                if tm:
                    token = tm.group(1)
                    break
            if token:
                play = self._token_to_m3u8(token, page_url)
                if play:
                    episodes.append(("正片", play))

        # 直接写在页面上的 m3u8
        if not episodes:
            m = re.search(r"(https?://[^\"'\\]+\.m3u8[^\"'\\]*)", html)
            if m:
                episodes.append(("正片", m.group(1).replace("\\/", "/")))

        return episodes

    def _token_to_m3u8(self, token, page_url):
        bucket = int(time.time() / 2000)
        api = f"{self.host}/api/player/{token}/{bucket}"
        headers = dict(self.header)
        headers["Referer"] = page_url
        data = ""
        try:
            import urllib.request
            req = urllib.request.Request(api, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            data = self.fetch(api)
        if not data:
            return ""
        decoded = self._decode_packer(data)
        plain = decoded.replace("\\\\/", "/").replace("\\/", "/")
        m = re.search(r"(https?://[^\s\"']+\.m3u8[^\s\"']*)", plain)
        if m:
            return m.group(1)
        hm = re.search(r"([a-f0-9]{32})\.m3u8", plain)
        if hm:
            return f"{self.host}/api.php/m3u8/p/t/{hm.group(1)}.m3u8"
        hashes = re.findall(r"[a-f0-9]{32}", plain)
        if hashes:
            return f"{self.host}/api.php/m3u8/p/t/{hashes[0]}.m3u8"
        return ""

    def _get_authors(self, tid, pg="1"):
        if tid == "authors/latest":
            base = f"{self.host}/authors/latest/"
        else:
            base = f"{self.host}/authors/"
        url = base if pg == "1" else f"{base.rstrip('/')}/page/{pg}/"
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 20, "total": 0}

        items = []
        seen = set()

        # 带粉丝数的卡片
        for m in re.finditer(r'href="(/author/(\d+)/)"([\s\S]{0,600}?)粉丝', html):
            path, aid, chunk = m.group(1), m.group(2), m.group(3)
            if aid in seen:
                continue
            seen.add(aid)
            name = ""
            # 优先取明显的名字节点
            nm = re.search(r'>([一-龥A-Za-z][一-龥A-Za-z0-9_ ·\-]{1,24})<', chunk)
            if nm:
                name = nm.group(1).strip()
            if not name or name.isdigit():
                nm = re.search(r'"name"\s*:\s*"([^"]+)"[^}]*"/author/' + aid, html)
                name = nm.group(1) if nm else f"UP主 {aid}"
            pic = ""
            pm = re.search(r'data-src="(https?://[^"]+)"', chunk)
            if pm:
                pic = pm.group(1)
            if not pic:
                pm = re.search(r'src="(https?://[^"]+)"', chunk)
                if pm:
                    pic = pm.group(1)
            fans = ""
            fm = re.search(r'粉丝[^0-9]{0,10}([0-9,，]+)', m.group(0))
            if fm:
                fans = f"粉丝 {fm.group(1)}"
            else:
                # 数字可能在「粉丝」后面更远
                tail = html[m.end():m.end()+40]
                fm2 = re.search(r'^[^0-9]{0,5}([0-9,，]+)', tail)
                if fm2:
                    fans = f"粉丝 {fm2.group(1)}"
            items.append({
                "vod_id": f"author/{aid}",
                "vod_name": f"👤 {name}",
                "vod_pic": self._proxy_pic(pic),
                "vod_remarks": fans or "UP主",
                "vod_tag": "folder",
                "style": {"type": "list"},
            })

        # 兜底：schema / 纯链接
        if not items:
            for m in re.finditer(r'"name"\s*:\s*"([^"]+)"[^}]{0,80}"url"\s*:\s*"[^"]*/author/(\d+)/"', html):
                name, aid = m.group(1), m.group(2)
                if aid in seen:
                    continue
                seen.add(aid)
                items.append({
                    "vod_id": f"author/{aid}",
                    "vod_name": f"👤 {name}",
                    "vod_pic": "",
                    "vod_remarks": "UP主",
                    "vod_tag": "folder",
                    "style": {"type": "list"},
                })

        pagecount = 1
        pages = re.findall(r"/authors/(?:latest/)?page/(\d+)/", html)
        if pages:
            try:
                pagecount = max(int(p) for p in pages if p.isdigit())
            except Exception:
                pagecount = 10
        else:
            pagecount = 5 if items else 1

        return {
            "list": items,
            "page": int(pg),
            "pagecount": max(pagecount, 1),
            "limit": 24,
            "total": max(pagecount, 1) * 24,
        }

    def _get_tags(self, pg="1"):
        html = self.fetch(f"{self.host}/tags/")
        if not html:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 50, "total": 0}
        items = []
        seen = set()
        # 官网: <a class="dx-tag" href="/tag/xxx/"><p>名称</p></a>
        for m in re.finditer(r'href="(/tag/([^"]+)/)"[^>]*>\s*(?:<p>)?([^<]+)', html):
            path, slug, name = m.group(1), m.group(2), re.sub(r"\s+", " ", m.group(3)).strip()
            if not name or path in seen:
                continue
            seen.add(path)
            items.append({
                "vod_id": f"tag/{slug}",
                "vod_name": f"🏷 {name}",
                "vod_pic": "",
                "vod_remarks": "标签",
                "vod_tag": "folder",
                "style": {"type": "list"},
            })
        return {
            "list": items,
            "page": 1,
            "pagecount": 1,
            "limit": len(items) or 50,
            "total": len(items),
        }

    def _get_archives(self, pg="1"):
        # 往期页用 JSON-LD 列表，无 <article>
        url = f"{self.host}/archives/" if str(pg) == "1" else f"{self.host}/archives/page/{pg}/"
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 20, "total": 0}
        items = []
        seen = set()
        for m in re.finditer(
            r'"headline"\s*:\s*"([^"]+)"[\s\S]{0,160}?"url"\s*:\s*"[^"]*/archives/(\d+)/"',
            html,
        ):
            name, vid = m.group(1).strip(), m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": "往期",
            })
        if not items:
            for m in re.finditer(
                r'"@id"\s*:\s*"[^"]*/archives/(\d+)/"[\s\S]{0,200}?"headline"\s*:\s*"([^"]+)"',
                html,
            ):
                vid, name = m.group(1), m.group(2).strip()
                if vid in seen:
                    continue
                seen.add(vid)
                items.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": "",
                    "vod_remarks": "往期",
                })
        if not items:
            for m in re.finditer(r'href="(/archives/(\d+)/)"[\s\S]{0,240}?<h[23][^>]*>([^<]+)</h[23]>', html):
                vid, name = m.group(2), m.group(3).strip()
                if vid in seen:
                    continue
                seen.add(vid)
                items.append({"vod_id": vid, "vod_name": name, "vod_pic": "", "vod_remarks": "往期"})
        pagecount = 1
        pages = re.findall(r"/archives/page/(\d+)/", html)
        if pages:
            try:
                pagecount = max(int(p) for p in pages if p.isdigit())
            except Exception:
                pagecount = 10
        return {
            "list": items,
            "page": int(pg),
            "pagecount": max(pagecount, 1),
            "limit": 30,
            "total": max(pagecount, 1) * 30,
        }

    def _get_list(self, url, pg="1"):
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": int(pg), "pagecount": 1, "limit": 20, "total": 0}

        items = []
        seen = set()
        articles = re.findall(r"<article>([\s\S]*?)</article>", html)
        for b in articles:
            hm = re.search(r'href="(/archives/(\d+)/)"', b)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            tm = re.search(r"<h[23][^>]*>([^<]+)</h[23]>", b)
            if tm:
                name = tm.group(1).strip()
            if not name:
                tm = re.search(r'class="dx-title[^"]*"[^>]*>([^<]+)', b)
                if tm:
                    name = tm.group(1).strip()
            if not name:
                tm = re.search(r'title="([^"]+)"', b)
                if tm:
                    name = tm.group(1).strip()
            if not name:
                name = f"视频 {vid}"

            pic = ""
            pm = re.search(r'u5-cover-single[\s\S]{0,400}?data-src="(https?://[^"]+)"', b)
            if pm:
                pic = pm.group(1)
            if not pic:
                for cm in re.finditer(r'data-src="(https?://[^"]+)"', b):
                    u = cm.group(1)
                    if "avatar" in u or "/static/" in u:
                        continue
                    pic = u
                    break
            if not pic:
                cm = re.search(r'data-src="(https?://[^"]+)"', b)
                if cm:
                    pic = cm.group(1)

            views = ""
            vm = re.search(r"data-views-count[^>]*>([^<]+)", b)
            if vm:
                views = vm.group(1).strip() + " 播放"

            author = ""
            am = re.search(r'href="/author/\d+/"[\s\S]{0,200}?<span[^>]*>([^<]+)</span>', b)
            if am:
                author = am.group(1).strip()

            remarks = " · ".join(x for x in [author, views] if x)

            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._proxy_pic(pic),
                "vod_remarks": remarks,
            })

        # 补充：标签页等 article 很少时，继续用标题+链接扫
        for m in re.finditer(
            r'href="(/archives/(\d+)/)"[\s\S]{0,240}?<h[23][^>]*>([^<]+)</h[23]>',
            html,
        ):
            vid, name = m.group(2), re.sub(r"\s+", " ", m.group(3)).strip()
            if vid in seen or not name:
                continue
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": "",
            })
        for m in re.finditer(
            r'<h[23][^>]*>([^<]+)</h[23]>[\s\S]{0,200}?href="(/archives/(\d+)/)"',
            html,
        ):
            name, vid = re.sub(r"\s+", " ", m.group(1)).strip(), m.group(3)
            if vid in seen or not name:
                continue
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": "",
            })

        pagecount = 1
        pages = re.findall(r"/page/(\d+)/", html)
        if pages:
            try:
                pagecount = max(int(p) for p in pages if p.isdigit())
            except Exception:
                pagecount = 20
        elif "下一页" in html or 'rel="next"' in html:
            try:
                pagecount = max(int(pg) + 5, 10)
            except Exception:
                pagecount = 10

        return {
            "list": items,
            "page": int(pg),
            "pagecount": max(pagecount, 1),
            "limit": 24,
            "total": max(pagecount, 1) * 24,
        }


    def _proxy_pic(self, pic):
        """CloudFront 直链在部分客户端无法显示，走站点 og 图床"""
        if not pic:
            return ""
        pic = pic.strip()
        if "u5book.com/og/img" in pic:
            return pic
        # cloudfront / 其它 CDN → og 代理
        for mark in (".cloudfront.net/", "u5book.com/upload", "/upload_01/", "/upload/"):
            if mark in pic:
                # 取 /upload 开头的路径
                m = re.search(r"(/(?:upload_01|upload)/[^?\s]+)", pic)
                if m:
                    from urllib.parse import quote
                    return f"{self.host}/og/img/?p=" + quote(m.group(1), safe="")
                if ".cloudfront.net/" in pic:
                    from urllib.parse import quote
                    p = "/" + pic.split(".cloudfront.net/", 1)[1].split("?", 1)[0]
                    return f"{self.host}/og/img/?p=" + quote(p, safe="")
        return pic

    def _re(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ""
