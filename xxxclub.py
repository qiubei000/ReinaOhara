# coding=utf-8
# XXXClub https://xxxclub.to/ — 成人种子站（视频 + 图集 + VR + 合集）
# 纯 HTML 站：列表是种子表（分类/标题/封面/大小/做种/下载/上传者），
# 详情页给磁力链接 + .torrent 下载 + 截图；没有直链视频，
# 播放靠把磁力交给播放器（和 LTX磁力 一样，能不能播看播放器支不支持磁力）。
# 分页是游标 token：翻页链接在 browsepagination 里，取带 data-no-instant
# 的那条（隐藏的 839183183190101 是占位，无效）；token 按 (base, 页)
# 缓存，翻到第 N 页时逐页取 token。
# 双壳：截图给“截图 pics:// + 单张直链”两条线（FongMi / WebHomeTV 通用模板）。

import html as _html
import re
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object


class Spider(BaseSpider):
    host = "https://xxxclub.to"
    DUMMY_TOKEN = "839183183190101"

    cate_list = [
        {"type_id": "browse/all", "type_name": "🆕 最新"},
        {"type_id": "browse/0", "type_name": "480p/SD"},
        {"type_id": "browse/1", "type_name": "720p/HD"},
        {"type_id": "browse/2", "type_name": "1080p/FullHD"},
        {"type_id": "browse/4", "type_name": "2160p/UHD/4K"},
        {"type_id": "browse/3", "type_name": "🎬 Movies/DVD/WEB"},
        {"type_id": "browse/5", "type_name": "🖼 IMAGESET"},
        {"type_id": "browse/6", "type_name": "🥽 VR"},
        {"type_id": "browse/7", "type_name": "📦 Pack合集"},
        {"type_id": "top100", "type_name": "🔥 Top 100"},
        {"type_id": "topten", "type_name": "⭐ Top 10"},
    ]

    def init(self, extend=""):
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self._tokens = {}

    def homeContent(self, filter):
        return {"class": self.cate_list}

    def homeVideoContent(self):
        return self._get_list("browse/all", "1")

    def categoryContent(self, tid, pg, filter, extend):
        if not pg or str(pg) in ("0", "None"):
            pg = "1"
        return self._get_list(str(tid).strip(), str(pg))

    def searchContent(self, key, quick, pg="1"):
        if not pg or str(pg) in ("0", "None"):
            pg = "1"
        return self._get_list("search/all/" + quote(key), str(pg))

    def detailContent(self, ids):
        vid = str(ids[0]).strip()
        url = f"{self.host}/torrents/details/{quote(vid, safe='~-')}"
        html = self.fetch(url)
        if not html:
            return {"list": []}
        title = ""
        tm = re.search(r"<title>(.*?)</title>", html, re.S)
        if tm:
            title = self._clean(tm.group(1)).replace(" - XXXClub", "")
        if not title:
            return {"list": []}
        # 封面：详情页 /p/ 大图
        pic = ""
        pm = re.search(r'src="(https://imgxclub\.com/p/[^"]+\.jpeg)"', html)
        if pm:
            pic = pm.group(1)
        if not pic:
            pm = re.search(r'src="(https://imgxclub\.com/ps/[^"]+\.jpeg)"', html)
            if pm:
                pic = pm.group(1)
        magnet = ""
        mm = re.search(r'href="(magnet:\?xt=urn:btih:[^"]+)"', html)
        if mm:
            magnet = _html.unescape(mm.group(1))
        # 信息：Size / Added / Peers / Uploader / Downloads
        txt = re.sub(r"<[^>]+>", " ", html)
        txt = re.sub(r"\s+", " ", txt)
        info = []
        for pat in (r"Size\s*:\s*([^\s]+(?:\s*[KMGT]B)?)",
                    r"Added Date\s*:\s*([0-9]{1,2} [A-Za-z]{3} [0-9]{4}[^A-Za-z]{0,12})",
                    r"Peers\s*:\s*([0-9]+)\s*seeders\s*,\s*([0-9]+)",
                    r"Uploader\s*:\s*(\S+)",
                    r"Downloads\s*:\s*([0-9]+)"):
            m = re.search(pat, txt)
            if m:
                info.append(" ".join(m.groups()) if len(m.groups()) > 1 else m.group(1))
        # 简介：description 块里的 Release Year / Genre / Duration / Studio / Cast
        desc = ""
        dm = re.search(r'<div class="description">(.*?)</div>', html, re.S)
        if dm:
            desc = self._clean(re.sub(r"<br\s*/?>", "\n", dm.group(1)))
            desc = "\n".join(l.strip() for l in desc.splitlines() if l.strip())[:800]
        shots = self._extract_shots(html)
        remarks = " · ".join(x for x in info[:3] if x)
        if shots:
            remarks = (remarks + f" · {len(shots)}张截图") if remarks else f"{len(shots)}张截图"
        content_parts = []
        if desc:
            content_parts.append(desc)
        if magnet:
            content_parts.append("磁力链接在播放线路里，点开即交给播放器；能不能直接播看播放器支不支持磁力。")
            content_parts.append("种子文件：站内 /torrents/download/<hash>，可另存下载。")
        play_from, play_url = [], []
        if magnet:
            play_from.append("磁力")
            play_url.append(f"磁力链接$magnet:{vid}")
        if shots:
            play_from.append("截图")
            play_url.append("#".join(
                f"截图 {s + 1}-{min(s + 20, len(shots))}$shots:{vid}:{s}:{min(20, len(shots) - s)}"
                for s in range(0, len(shots), 20)))
            play_from.append("单张")
            play_url.append("#".join(f"第{i + 1}张$shot:{vid}:{i}" for i in range(len(shots))))
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": "XXXClub",
            "vod_year": (re.search(r"Release Year:\s*(\d{4})", desc).group(1) if re.search(r"Release Year:\s*(\d{4})", desc) else ""),
            "vod_area": "",
            "vod_remarks": remarks,
            "vod_actor": (re.search(r"Cast:\s*([^\n]+)", desc).group(1).strip() if re.search(r"Cast:\s*([^\n]+)", desc) else ""),
            "vod_director": (re.search(r"Studio:\s*([^\n]+)", desc).group(1).strip() if re.search(r"Studio:\s*([^\n]+)", desc) else ""),
            "vod_content": "\n".join(content_parts),
            "vod_play_from": "$$$".join(play_from) if play_from else "磁力",
            "vod_play_url": "$$$".join(play_url) if play_url else f"磁力链接$magnet:{vid}",
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        mid = str(id or "").strip()
        header = {
            "User-Agent": self.header["User-Agent"],
            "Referer": self.host + "/",
        }
        if mid.startswith("magnet:"):
            vid = mid[len("magnet:"):]
            magnet = self._get_magnet(vid)
            if not magnet:
                return {"parse": 0, "url": "", "msg": "没有解析到磁力链接"}
            return {"parse": 0, "url": magnet, "header": header}
        if mid.startswith("shots:") or mid.startswith("shot:"):
            parts = mid.split(":")
            vid = parts[1] if len(parts) > 1 else ""
            shots = self._get_shots(vid)
            if not shots:
                return {"parse": 0, "url": "", "msg": "没有解析到截图"}
            if mid.startswith("shot:"):
                try:
                    idx = int(parts[2]) if len(parts) > 2 else 0
                except Exception:
                    idx = 0
                if idx >= len(shots):
                    return {"parse": 0, "url": "", "msg": "没有解析到截图"}
                return {"parse": 0, "url": shots[idx], "header": header}
            try:
                start = int(parts[2]) if len(parts) > 2 else 0
                count = int(parts[3]) if len(parts) > 3 else 20
            except Exception:
                start, count = 0, 20
            chunk = shots[start:start + count] or shots[:20]
            return {"parse": 0, "url": "pics://" + "&&".join(chunk), "header": header}
        return {"parse": 0, "url": "", "msg": "未知播放地址"}

    def isVideoFormat(self, url):
        u = str(url or "")
        return u.startswith("pics://") or u.startswith("magnet:") or ".jpg" in u or ".jpeg" in u or ".webp" in u or ".png" in u or ".m3u8" in u or ".mp4" in u

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

    def _clean(self, s):
        s = re.sub(r"<[^>]+>", "", s or "")
        return _html.unescape(s).strip()

    def _next_token(self, html):
        """取带 data-no-instant 的翻页链接 token，占位 token 视为无下一页。
        注意 href 在 data-no-instant 前面，先取整条 <a> 再提 href。"""
        for tag in re.findall(r"<a[^>]*data-no-instant[^>]*>", html or ""):
            m = re.search(r'href="([^"]+)"', tag)
            if not m:
                continue
            tok = m.group(1).rstrip("/").split("/")[-1]
            if tok != self.DUMMY_TOKEN:
                return tok
        return None

    def _list_url(self, base, pg):
        """base 如 browse/all；pg=1 用 base，pg>1 用缓存的游标 token 逐页推进。"""
        pg = int(pg)
        if pg <= 1:
            return f"{self.host}/torrents/{base}/"
        # 逐页取 token
        cur_pg, cur_url = 1, f"{self.host}/torrents/{base}/"
        while cur_pg < pg:
            key = (base, cur_pg)
            tok = self._tokens.get(key)
            if not tok:
                html = self.fetch(cur_url)
                if not html:
                    return None
                tok = self._next_token(html)
                if not tok:
                    return None
                self._tokens[key] = tok
            cur_url = f"{self.host}/torrents/{base}/{tok}"
            cur_pg += 1
        return cur_url

    def _parse_table(self, html):
        """种子表 <li>：分类/标题/小封面/日期/大小/做种/下载/上传者。"""
        items, seen = [], set()
        for block in re.findall(r"<li>([\s\S]*?)</li>", html):
            dm = re.search(r'href="/torrents/details/([^"]+)"[^>]*>(.*?)</a>', block, re.S)
            if not dm:
                continue
            vid, title = dm.group(1).strip(), self._clean(dm.group(2))
            if not title or vid in seen:
                continue
            seen.add(vid)
            pic = ""
            pm = re.search(r"""src=['"](https://imgxclub\.com/ps/[^'"]+\.jpeg)['"]""", block)
            if pm:
                pic = pm.group(1)
            spans = re.findall(r'<span[^>]*>([^<]*)</span>', block)
            # spans: [分类?, 标题区, Added, Size, S, L, Uploader] 位置不固定，按内容认
            date, size, seeds, leech = "", "", "", ""
            for s in spans:
                s = s.strip()
                if re.match(r"\d{1,2} [A-Za-z]{3} \d{4}", s):
                    date = s[:11]
                elif re.match(r"[\d.]+ (?:MB|GB|KB)", s):
                    size = s
            nums = re.findall(r'<span class="(?:see|lee)[^>]*>([^<]*)</span>', block)
            if len(nums) >= 2:
                seeds, leech = nums[0].strip(), nums[1].strip()
            cat = ""
            cm = re.search(r"<lable[^>]*>(?:<i[^>]*></i>)?([^<]+)</lable>", block)
            if cm:
                cat = self._clean(cm.group(1))
            remarks = " · ".join(x for x in [cat, size, f"S{seeds}/L{leech}" if seeds else "", date] if x)
            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return items

    def _parse_cards(self, html):
        """Top 10 卡片：file-card + /p/ 大封面。"""
        items, seen = [], set()
        for m in re.finditer(r'<a href="/torrents/details/([^"]+)" class="file-card">([\s\S]*?)</a>', html):
            vid = m.group(1).strip()
            body = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            title = ""
            tm = re.search(r'alt="([^"]+)"', body)
            if tm:
                title = self._clean(tm.group(1))
            pic = ""
            pm = re.search(r'src="(https://imgxclub\.com/p/[^"]+\.jpeg)"', body)
            if pm:
                pic = pm.group(1)
            if not title:
                continue
            items.append({"vod_id": vid, "vod_name": title, "vod_pic": pic, "vod_remarks": ""})
        return items

    def _get_list(self, base, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = self._list_url(base, pg)
        if not url:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 40, "total": 0}
        html = self.fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": pg, "limit": 40, "total": 0}
        if base == "topten":
            items = self._parse_cards(html)
        else:
            items = self._parse_table(html)
        tok = self._next_token(html)
        has_next = bool(tok)
        if has_next:
            self._tokens[(base, pg)] = tok
        return {
            "list": items,
            "page": pg,
            "pagecount": pg + 1 if has_next else pg,
            "limit": 40,
            "total": (pg + 1 if has_next else pg) * 40,
        }

    def _detail_html(self, vid):
        return self.fetch(f"{self.host}/torrents/details/{quote(vid, safe='~-')}")

    def _get_magnet(self, vid):
        html = self._detail_html(vid)
        if not html:
            return ""
        m = re.search(r'href="(magnet:\?xt=urn:btih:[^"]+)"', html)
        return _html.unescape(m.group(1)) if m else ""

    def _extract_shots(self, html):
        """截图：rintor 全尺寸图（去掉 .th），或图集站的 xxxwebdl 小图。"""
        shots, seen = [], set()
        for u in re.findall(r'https://rintor\.space/images/[^"\']+?\.th\.jpg', html or ""):
            full = u.replace(".th.jpg", ".jpg")
            if full not in seen:
                seen.add(full)
                shots.append(full)
        for u in re.findall(r'https://xxxwebdlxxx\.top/upload/small/[^"\']+?\.jpg', html or ""):
            if u not in seen:
                seen.add(u)
                shots.append(u)
        return shots

    def _get_shots(self, vid):
        return self._extract_shots(self._detail_html(vid))
