# -*- coding: utf-8 -*-
"""
LTX 磁力表（FongMi / TVBox Py 源）——把 LTX 资源库的 CSV 表做成一个站
数据：ltx.csv（LTX 2026-11-21 导出，4146 条）
  番号 / 中文标题 / 原题 / 女优 / 发行日 / 厂牌 / 导演 /
  体积GB / 评分 / 评价数 / 链接类型 / 文件名 / 链接 / 封面 /
  截图 / 字幕 / 入库 / 状态 / javdb
做法：这个 py 文件本身不带数据，第一次打开时去 GitHub 上下载 ltx.csv，
  下载一次后缓存在内存里，之后翻页和搜索都不用再下载。
分类：全部 / 磁力 / ed2k / 女优 / 厂牌。
  女优 1097 位、厂牌 208 家，都按作品数从多到少排，一页 20 个，
  点进一个女优或厂牌，会列出她的作品（最多前 100 部），点一部就去取链接。

实话：
- 表里 4146 条，磁力只有 215 条，剩下 3931 条是 ed2k。
- 磁力有机会直接播（看 FongMi 的播放器支不支持磁力），
  ed2k 是下载链接，播放器播不了，只能拿链接去下载工具下。
- 所以分类里专门分了“磁力”和“ed2k”，想直接播就只看“磁力”那栏。
"""

# 数据文件地址（和这个 py 在同一个 GitHub 仓库里）
DATA_URL = "https://gh-proxy.org/https://raw.githubusercontent.com/qiubei000/ReinaOhara/main/ltx.csv"

import csv
import io
from urllib.parse import quote, unquote

try:
    import requests
except ImportError:
    requests = None

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass


class Spider(_BaseSpider):
    _ROWS = None      # 缓存：下载过的整张表
    _FAILED = False   # 缓存：下载失败过就不再反复试
    _ACTRESSES = None  # 缓存：女优索引（名字、部数、第一部封面）
    _MAKERS = None    # 缓存：厂牌索引（名字、部数、第一部封面）

    def __init__(self):
        self.page_size = 20

    # ---------- 数据 ----------
    def _fetch_text(self, url):
        if requests is not None:
            try:
                r = requests.get(url, timeout=30)
                r.encoding = "utf-8-sig"
                return r.text if r.status_code == 200 else ""
            except Exception:
                return ""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8-sig", "replace")
        except Exception:
            return ""

    def _load(self):
        if Spider._ROWS is not None:
            return Spider._ROWS
        if Spider._FAILED:
            return []
        text = self._fetch_text(DATA_URL)
        if not text:
            Spider._FAILED = True
            return []
        rows = []
        try:
            for r in csv.DictReader(io.StringIO(text)):
                link = (r.get("链接") or "").strip()
                if not link:
                    continue
                rows.append({
                    "code": (r.get("番号") or "").strip(),
                    "title": (r.get("中文标题") or r.get("原题") or "").strip(),
                    "orig": (r.get("原题") or "").strip(),
                    "actress": (r.get("女优") or "").strip(),
                    "date": (r.get("发行日") or "").strip(),
                    "maker": (r.get("厂牌") or "").strip(),
                    "director": (r.get("导演") or "").strip(),
                    "size": (r.get("体积GB") or "").strip(),
                    "score": (r.get("评分") or "").strip(),
                    "votes": (r.get("评价数") or "").strip(),
                    "ltype": (r.get("链接类型") or "").strip(),
                    "fname": (r.get("文件名") or "").strip(),
                    "link": link,
                    "cover": (r.get("封面") or "").strip(),
                    "shot": (r.get("截图") or "").strip(),
                    "sub": (r.get("字幕") or "").strip(),
                    "status": (r.get("状态") or "").strip(),
                    "javdb": (r.get("javdb") or "").strip(),
                })
        except Exception:
            Spider._FAILED = True
            return []
        Spider._ROWS = rows
        return rows

    def _filtered(self, tid):
        rows = self._load()
        if tid == "magnet":
            pairs = [(i, r) for i, r in enumerate(rows)
                     if r["link"].startswith("magnet:")]
        elif tid == "ed2k":
            pairs = [(i, r) for i, r in enumerate(rows)
                     if r["link"].startswith("ed2k:")]
        else:
            pairs = list(enumerate(rows))
        return pairs

    def _vod(self, idx, r):
        name = ((r["code"] + " ") if r["code"] else "") + r["title"]
        remarks = ""
        if r["score"]:
            remarks = "★" + r["score"]
        if r["size"] and r["size"] != "0.0":
            remarks = (remarks + " · " + r["size"] + "GB") if remarks else r["size"] + "GB"
        tag = "磁力" if r["link"].startswith("magnet:") else "ed2k"
        remarks = (remarks + " · " + tag) if remarks else tag
        return {
            "vod_id": str(idx),
            "vod_name": name,
            "vod_pic": r["cover"],
            "vod_remarks": remarks,
        }

    def _actress_index(self):
        """女优索引：按作品数从多到少排。女优栏里多个名字用 / 分开，要拆开算。
        每项是（名字，部数，第一部作品的封面）。"""
        if Spider._ACTRESSES is not None:
            return Spider._ACTRESSES
        rows = self._load()
        counts = {}
        first_cover = {}
        for i, r in enumerate(rows):
            for name in (r["actress"] or "").split("/"):
                name = name.strip()
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + 1
                if name not in first_cover:
                    first_cover[name] = r["cover"]
        Spider._ACTRESSES = [(name, c, first_cover[name])
                             for name, c in sorted(counts.items(), key=lambda kv: -kv[1])]
        return Spider._ACTRESSES

    def _maker_index(self):
        """厂牌索引：按作品数从多到少排。每项是（名字，部数，第一部作品的封面）。"""
        if Spider._MAKERS is not None:
            return Spider._MAKERS
        rows = self._load()
        counts = {}
        first_cover = {}
        for i, r in enumerate(rows):
            name = (r["maker"] or "").strip()
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
            if name not in first_cover:
                first_cover[name] = r["cover"]
        Spider._MAKERS = [(name, c, first_cover[name])
                          for name, c in sorted(counts.items(), key=lambda kv: -kv[1])]
        return Spider._MAKERS

    def _index_page(self, index, kind, pg):
        """女优 / 厂牌索引的分页：一页 20 个，封面用她的第一部作品的封面。"""
        pg = max(int(pg), 1)
        start = (pg - 1) * self.page_size
        chunk = index[start:start + self.page_size]
        items = []
        for name, count, cover in chunk:
            items.append({
                "vod_id": kind + ":" + quote(name, safe=""),
                "vod_name": name,
                "vod_pic": cover,
                "vod_remarks": "{} 部".format(count),
            })
        return {
            "list": items,
            "page": pg,
            "pagecount": (len(index) + self.page_size - 1) // self.page_size,
            "limit": self.page_size,
            "total": len(index),
        }

    def _page(self, pairs, pg):
        pg = max(int(pg), 1)
        start = (pg - 1) * self.page_size
        chunk = pairs[start:start + self.page_size]
        return {
            "list": [self._vod(i, r) for i, r in chunk],
            "page": pg,
            "pagecount": (len(pairs) + self.page_size - 1) // self.page_size,
            "limit": self.page_size,
            "total": len(pairs),
        }

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=None):
        rows = self._load()
        n_mag = sum(1 for r in rows if r["link"].startswith("magnet:"))
        n_ed2k = len(rows) - n_mag
        return {
            "class": [
                {"type_id": "all", "type_name": "全部 {} 条".format(len(rows))},
                {"type_id": "magnet", "type_name": "磁力 {} 条".format(n_mag)},
                {"type_id": "ed2k", "type_name": "ed2k {} 条".format(n_ed2k)},
                {"type_id": "actress", "type_name": "女优 {} 位".format(len(self._actress_index()))},
                {"type_id": "maker", "type_name": "厂牌 {} 家".format(len(self._maker_index()))},
            ],
            "filters": {},
        }

    def homeVideoContent(self):
        rows = self._load()
        if not rows:
            return {"list": [], "msg": "磁力表还没加载到，检查网络后下拉刷新再试"}
        return {"list": [self._vod(i, r) for i, r in enumerate(rows[:20])]}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        tid = (tid or "all").strip("/")
        # 女优 / 厂牌索引：按作品数排，一页 20 个
        if tid == "actress":
            return self._index_page(self._actress_index(), "actress", pg)
        if tid == "maker":
            return self._index_page(self._maker_index(), "maker", pg)
        pairs = self._filtered(tid)
        if not pairs and not self._load():
            return {"list": [], "msg": "磁力表还没加载到，检查网络后下拉刷新再试"}
        return self._page(pairs, pg)

    def searchContent(self, key, quick=False, pg=1):
        key = (key or "").strip().lower()
        rows = self._load()
        pairs = [(i, r) for i, r in enumerate(rows)
                 if key in r["code"].lower()
                 or key in r["title"].lower()
                 or key in r["orig"].lower()
                 or key in r["actress"].lower()
                 or key in r["maker"].lower()]
        return self._page(pairs, pg)

    def detailContent(self, ids):
        code = ids[0] if isinstance(ids, list) else str(ids)
        # 女优 / 厂牌详情：列出她（它）的作品，点一部就去取那部的链接
        if code.startswith("actress:") or code.startswith("maker:"):
            kind, name = code.split(":", 1)
            name = unquote(name)
            rows = self._load()
            if kind == "actress":
                label = "女优"
                pairs = [(i, r) for i, r in enumerate(rows)
                         if name in [n.strip() for n in (r["actress"] or "").split("/")]]
            else:
                label = "厂牌"
                pairs = [(i, r) for i, r in enumerate(rows)
                         if (r["maker"] or "").strip() == name]
            total = len(pairs)
            shown = pairs[:100]
            play_url = "#".join(
                "{}${}".format(self._vod(i, r)["vod_name"], "video:" + str(i))
                for i, r in shown)
            vod = {
                "vod_id": code,
                "vod_name": "{}：{}".format(label, name),
                "vod_pic": shown[0][1]["cover"] if shown else "",
                "vod_content": "{}：{}\n共 {} 部作品，这里列出前 {} 部，点一部就会去取它的链接。".format(
                    label, name, total, len(shown)),
                "vod_remarks": "共 {} 部".format(total),
                "vod_play_from": "作品" if shown else "",
                "vod_play_url": play_url,
            }
            return {"list": [vod]}
        idx = int(code)
        rows = self._load()
        if idx < 0 or idx >= len(rows):
            return {"list": []}
        r = rows[idx]
        name = ((r["code"] + " ") if r["code"] else "") + r["title"]
        lines = []
        lines.append("番号：" + r["code"])
        lines.append("标题：" + r["title"])
        if r["orig"] and r["orig"] != r["title"]:
            lines.append("原题：" + r["orig"])
        if r["actress"]:
            lines.append("女优：" + r["actress"])
        if r["date"]:
            lines.append("发行日：" + r["date"])
        if r["maker"]:
            lines.append("厂牌：" + r["maker"])
        if r["director"]:
            lines.append("导演：" + r["director"])
        if r["size"] and r["size"] != "0.0":
            lines.append("体积：" + r["size"] + " GB")
        if r["score"]:
            lines.append("评分：" + r["score"] + " 分" +
                         (("（" + r["votes"] + " 人评价）") if r["votes"] else ""))
        if r["status"]:
            lines.append("状态：" + r["status"])
        if r["fname"]:
            lines.append("文件名：" + r["fname"])
        if r["sub"]:
            lines.append("字幕：" + r["sub"])
        if r["javdb"]:
            lines.append("JavDB：" + r["javdb"])
        if r["link"].startswith("ed2k:"):
            lines.append("这是 ed2k 下载链接，播放器播不了，复制链接去下载工具下。")
        else:
            lines.append("这是磁力链接，点“磁力”播放源交给播放器播，能不能播看播放器支不支持磁力。")

        remarks = ""
        if r["score"]:
            remarks = "★" + r["score"]
        if r["size"] and r["size"] != "0.0":
            remarks = (remarks + " · " + r["size"] + "GB") if remarks else r["size"] + "GB"

        play_from = []
        play_url = []
        tag = "磁力" if r["link"].startswith("magnet:") else "ed2k"
        play_from.append(tag)
        play_url.append(tag + "$" + r["link"])
        if r["shot"]:
            play_from.append("截图")
            play_url.append("截图$pics://" + r["shot"])
            # 单张线路（WebHomeTV 兜底）：一集一张截图直链，不依赖 pics://
            # 表里每部作品只有一张截图，所以单张线路只有第 1 张
            play_from.append("单张")
            play_url.append("第1张$img:" + str(idx))

        vod = {
            "vod_id": str(idx),
            "vod_name": name,
            "vod_pic": r["cover"],
            "vod_year": r["date"][:4] if r["date"] else "",
            "vod_actor": r["actress"],
            "vod_director": r["director"],
            "vod_content": "\n".join(lines),
            "vod_remarks": remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        # 单张：img:<行号> -> 直接返回那部作品的截图直链
        if isinstance(id, str) and id.startswith("img:"):
            try:
                idx = int(id.split(":", 1)[1])
                rows = self._load()
                return {"parse": 0, "url": rows[idx]["shot"], "header": {}}
            except Exception:
                return {"parse": 0, "url": "", "header": {}}
        # 女优 / 厂牌里的作品：点开时按行号取那部的链接
        if isinstance(id, str) and id.startswith("video:"):
            try:
                idx = int(id.split(":", 1)[1])
                rows = self._load()
                return {"parse": 0, "url": rows[idx]["link"], "header": {}}
            except Exception:
                return {"parse": 0, "url": "", "header": {}}
        # 截图源：pics:// 开头的图串，直接交给播放器翻图
        if isinstance(id, str) and id.startswith("pics://"):
            return {"parse": 0, "url": id, "header": {}}
        # 磁力 / ed2k：id 本身就是链接，直接返回给播放器
        return {"parse": 0, "url": id, "header": {}}

    def isVideoFormat(self, url):
        u = str(url or "")
        return (u.startswith("magnet:") or u.startswith("pics://")
                or ".jpg" in u or ".jpeg" in u or ".png" in u or ".webp" in u
                or ".m3u8" in u or ".mp4" in u)

    def localProxy(self, param):
        return [200, "video/MP2T", None, ""]
