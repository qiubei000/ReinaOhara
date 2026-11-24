# coding=utf-8
# !/usr/bin/python

"""
花都影院 (huaduys.org) —— TVBox / 默影视 / 影视仓 / OK影视 / PickTV 通用 Spider

站点实际结构（2026-11 复核，苹果CMS V10 系 stui 模板）：
  首页       /
  导航分类   /vodtype/{slug}.html        (中文字幕/无字幕/国产/欧美/动漫)
  列表筛选   /vodshow/{tid}-{area}-{by}-{class}-{lang}-{letter}-{level}-{order}-{page}-{state}-{tag}-{year}.html
  详情页     /voddetail{id}.html         (注意：id 前面没有斜杠)
  播放页     /vodplay/{id}-{线路}-{集数}.html
  搜索页     /vodsearch/-------------.html?wd={关键词}
  搜索分页   /vodsearch/{关键词}----------{页码}---.html

播放地址：播放页内 var player_data={"encrypt":2,...,"url":"..."}，
url 为 base64(percent-encoded)，先 base64 解码再 unquote 得到 m3u8。
站点有"请不要频繁操作"限流页，遇到时等待后重试。

筛选说明（站点真实支持的能力）：
  - 类型：子频道（糖心Vlog / 国产精品 / 中字无码 ...），用子频道 slug 作为 tid；
  - 剧情：标签筛选（player_data 页面无标签，列表页标签来自 vod_class/tag，走 URL 第 10 段）；
  - 字母：A-Z；
  - 排序：按时间 / 按人气 / 按点赞。
  站点没有年代、地区、语言字段（详情页、筛选页均无对应数据，vodshow 的
  area/lang/year 段传值一律无结果），因此不提供这些无效筛选项。

多地址轮换：默认 7 个域名，任一失效自动切换；
extend 可用 {"host": "https://a.com,https://b.com"} 或 {"hosts": ["https://a.com"]} 覆盖。
"""

import base64
import html
import json
import re
import time
from urllib.parse import quote, unquote

import requests

DEFAULT_HOSTS = [
    "https://rb.huaduys.org",
    "https://www.huaduys.org",
    "https://long.huaduys.org",
    "https://ww.huaduys.org",
    "https://rb1.huaduys.org",
    "https://rb2.huaduys.org",
    "https://rb3.huaduys.org",
]

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0")

PLAY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
}

HOSTS_FILE = "huaduys_hosts.txt"

# 顶级分类：type_id(slug) -> (显示名, 子频道[(名称, 子频道slug)])
TOP_TYPES = [
    ("zhongwenzimu", "中文字幕", [
        ("中字有码", "zhongziyouma"),
        ("中字无码", "zhongziwuma"),
    ]),
    ("wuzimu", "无字幕", [
        ("骑兵有码", "qibingyouma"),
        ("步兵无码", "bubingwuma"),
    ]),
    ("guochan", "国产", [
        ("糖心Vlog", "tangxinVlog"),
        ("国产精品", "guochanjingpin"),
        ("国产传媒", "guochanchuanmei"),
    ]),
    ("oumei", "欧美", [
        ("欧美中字", "oumeizhongzi"),
    ]),
    ("dongman", "动漫", [
        ("中字里番", "zhongzilifan"),
        ("3D动漫", "3Ddongman"),
        ("AI短剧", "AIduanju"),
    ]),
]

# 站点真实存在的剧情标签（已在分类页逐个验证有数据）
TAGS = [
    "剧情", "中文字幕", "有字幕", "无码", "有码", "高清", "激情",
    "人妻", "巨乳", "制服", "学生", "熟女", "美女", "网红", "主播",
    "探花", "传媒", "明星", "黑人", "丝袜", "口交", "后入", "中出",
    "内射", "群交", "3P", "双飞", "调教", "乱伦", "情侣", "户外",
    "车震", "按摩", "自慰", "颜射", "巨根", "萝莉", "少女", "百合",
    "麻豆", "糖心", "星空传媒", "Vlog", "三级", "伦理", "短剧",
    "长腿", "舞蹈", "偷拍", "自拍",
]

LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]

SORTS = [("最新", "time"), ("最热", "hits"), ("点赞", "up")]

ANTI_BOT_WAIT = 10  # 站点提示"请不要频繁操作，请等待10秒再搜索"

# 封面图床：站点所有封面都在 a.7976.top。该图床对国内部分网络（含本机）
# 的 443/80 直接被拒，图片地址本身是好的（境外可访问），所以这里做
# "直连优先、不通就自动走图片代理"的处理，避免封面一片空白。
IMG_HOSTS = ("a.7976.top",)
IMG_PROXY_CANDIDATES = ("https://i0.wp.com/", "https://i2.wp.com/")
_IMG_MODE_CACHE = {}  # key -> "direct" 或 代理前缀（跨实例缓存，避免重复探测）

ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S)


class Spider:
    def __init__(self):
        self.hosts = list(DEFAULT_HOSTS)
        self.host = self.hosts[0]
        self.sess = None
        # 封面代理：None=自动探测（直连优先，失败走图片代理）
        #            ""/"off"=只用直连     "https://..."=固定使用该代理
        self.img_proxy = None

    # ---------------- 基础 ----------------
    def getName(self):
        return "花都影院"

    def init(self, extend=""):
        if extend:
            try:
                o = json.loads(extend)
            except Exception:
                o = None
            if isinstance(o, dict):
                if "imgProxy" in o or "img_proxy" in o:
                    val = o.get("imgProxy", o.get("img_proxy"))
                    self.img_proxy = "" if val is None else str(val).strip()
                raw = o.get("hosts") or o.get("host") or o.get("url")
                if isinstance(raw, list):
                    picked = [str(x).strip().rstrip("/") for x in raw if str(x).strip()]
                    if picked:
                        self.hosts = picked
                elif isinstance(raw, str) and raw.strip():
                    picked = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
                    if picked:
                        self.hosts = picked
        else:
            try:
                with open(HOSTS_FILE, "r", encoding="utf-8") as f:
                    lines = [x.strip().rstrip("/") for x in f
                             if x.strip() and not x.startswith("#")]
                if lines:
                    self.hosts = lines
            except Exception:
                pass
        self.host = self.hosts[0]
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": UA_PC,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._warm()

    def _warm(self):
        for _ in range(len(self.hosts)):
            try:
                self.sess.get(self.host, timeout=10)
                return
            except Exception:
                self._rotate()

    def _rotate(self):
        if not self.hosts:
            return self.host
        if self.host in self.hosts and len(self.hosts) > 1:
            self.host = self.hosts[(self.hosts.index(self.host) + 1) % len(self.hosts)]
        else:
            self.host = self.hosts[0]
        return self.host

    @staticmethod
    def _rate_limited(text):
        return "系统提示" in text and "频繁" in text

    def _get(self, path, timeout=15, min_len=0, attempts=3):
        """按当前域名抓取；正文过短/限流页视为无效，等待或换域名后重试。"""
        absolute = path.startswith("http")
        last = ""
        waited = False
        for _ in range(len(self.hosts)):
            for i in range(attempts):
                url = path if absolute else self.host + path
                try:
                    r = self.sess.get(url, timeout=timeout)
                    r.encoding = "utf-8"
                    text = r.text or ""
                    last = text
                    if r.status_code == 200 and text:
                        if self._rate_limited(text):
                            # 站点限流：只等一次，仍被限就交给下一个域名/上层
                            if not waited:
                                waited = True
                                time.sleep(ANTI_BOT_WAIT)
                                continue
                            break
                        if (len(text) >= min_len
                                and "System Error" not in text
                                and "File not found." not in text):
                            return text
                except Exception:
                    pass
                if absolute:
                    break
                if i + 1 < attempts:
                    time.sleep(0.6)
            if absolute:
                break
            self._rotate()
        return last

    def _abs(self, u):
        u = str(u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    @staticmethod
    def _attr(fragment, key):
        m = re.search(key + r'="([^"]*)"', fragment or "")
        return html.unescape(m.group(1)).strip() if m else ""

    # ---------------- 封面图处理 ----------------
    @staticmethod
    def _is_img_host(u):
        host = re.sub(r"^https?://", "", u or "").split("/")[0].split(":")[0].lower()
        return any(host == h or host.endswith("." + h) for h in IMG_HOSTS)

    @staticmethod
    def _tcp_ok(host, port=443, timeout=2.0):
        """快速判断能否连通（只建 TCP，不下载内容）。"""
        import socket
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except Exception:
            return False

    def _img_get_ok(self, url, timeout=5):
        if not self.sess:
            return False
        try:
            r = self.sess.get(url, timeout=timeout, stream=True, headers={
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"})
            ok = (r.status_code == 200
                  and (r.headers.get("Content-Type") or "").lower().startswith("image"))
            r.close()
            return ok
        except Exception:
            return False

    def _img_mode(self, sample):
        """
        决定封面走直连还是图片代理。
        a.7976.top 对国内部分网络/非浏览器 UA 会直接拒连或断流，所以默认优先
        图片代理（TCP 通 + 真能取到图才用），代理都不行时退回直连。
        结论缓存，后续不再探测。
        """
        if not self._is_img_host(sample):
            return "direct"
        override = self.img_proxy
        if override is not None and str(override).strip().lower() in ("", "off", "none", "false", "0"):
            return "direct"
        key = "__auto__" if not override else str(override).strip()
        if key in _IMG_MODE_CACHE:
            return _IMG_MODE_CACHE[key]
        sample = sample.replace("http://", "https://", 1)
        tail = sample.split("://", 1)[-1]
        if override:
            candidates = [str(override).strip()]
        else:
            candidates = list(IMG_PROXY_CANDIDATES)
        for base in candidates:
            base = base if base.endswith("/") else base + "/"
            host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
            if not self._tcp_ok(host):
                continue
            if self._img_get_ok(base + tail, timeout=5):
                _IMG_MODE_CACHE[key] = base
                return base
        _IMG_MODE_CACHE[key] = "direct"
        return "direct"

    def _pic(self, u):
        """封面 URL：站内相对地址转绝对地址；图床不通时改走图片代理。"""
        u = self._abs(u)
        if not u:
            return ""
        if u.endswith("/hdys/img/load.gif"):
            return ""
        if not self._is_img_host(u):
            return u
        mode = self._img_mode(u)
        if mode != "direct":
            return mode + re.sub(r"^https?://", "", u)
        return u

    # ---------------- 列表解析 ----------------
    @staticmethod
    def _remarks(tags):
        """从卡片角标里挑一个可用的备注：优先时长，其次频道名。"""
        for t in tags:
            if re.search(r"\d+\s*分钟|^\d{1,2}:\d{2}(:\d{2})?$", t):
                return t
        for t in tags:
            if t and not t.isdigit() and "👍" not in t and "次" not in t:
                return t
        return ""

    def _cards(self, text):
        out = []
        seen = set()
        if not text:
            return out
        text = html.unescape(text)
        for m in ANCHOR_RE.finditer(text):
            attrs = m.group(1)
            if "stui-vodlist__thumb" not in attrs:
                continue
            hm = re.search(r'href="([^"]*?/voddetail(\d+)\.html)"', attrs)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            inner = m.group(2)
            # 顺序：优先锚点 title，其次 img alt
            title = self._attr(attrs, "title") or self._attr(inner, "alt")
            name = re.sub(r"\s+", " ", title).strip()
            if not name:
                continue
            pic = self._pic(self._attr(inner, "data-original") or self._attr(inner, "src"))
            tags = [re.sub(r"<[^>]+>", "", t).strip() for t in
                    re.findall(r'<span class="pic-tag[^"]*"[^>]*>(.*?)</span>', inner, re.S)]
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": self._remarks(tags),
            })
        return out

    # ---------------- 页面统计 ----------------
    @staticmethod
    def _page_info(text):
        """返回 (总页数, 总条数)。站点分页统计：共 N 条数据，当前第 X / Y 页。"""
        pagecount = 0
        total = 0
        m = re.search(r'max="(\d+)"', text or "")
        if m:
            pagecount = int(m.group(1))
        if not pagecount:
            m = re.search(r"/\s*(\d+)\s*页", text or "")
            if m:
                pagecount = int(m.group(1))
        m = re.search(r"共\s*(?:&nbsp;|\s)*<strong[^>]*>(\d+)</strong>", text or "")
        if m:
            total = int(m.group(1))
        return pagecount, total

    # ---------------- 筛选 URL ----------------
    @staticmethod
    def _show_path(tid, page=1, cls="", letter="", by="", tag="", page_token=None):
        """
        vodshow 12 段：tid-area-by-class-lang-letter-level-order-page-state-tag-year
        page_token 仅用于解析总页数（把页码位置换成占位符）。
        """
        page_value = page_token if page_token is not None else (
            "" if (not page or int(page) <= 1) else str(int(page)))
        fields = [
            "",                 # area    (站点无地区数据)
            by or "",           # by      排序 (time/hits/up)
            cls or "",          # class   保留
            "",                 # lang
            letter or "",       # letter
            "",                 # level
            "",                 # order
            page_value,         # page
            "",                 # state
            tag or "",          # tag     剧情标签
            "",                 # year    (站点无年代数据)
        ]
        return "/vodshow/%s-%s.html" % (tid, "-".join(fields))

    def _filter_url(self, tid, pg, extend):
        ext = extend or {}
        return self._show_path(
            str(tid),
            page=pg,
            cls=str(ext.get("class") or "").strip(),
            letter=str(ext.get("letter") or "").strip(),
            by=str(ext.get("by") or "").strip(),
            tag=str(ext.get("tag") or "").strip(),
        )

    def _page_count(self, text, tid, pg, extend):
        """优先用站点统计，其次用尾页链接推算。"""
        pagecount, total = self._page_info(text)
        if pagecount:
            return pagecount, total
        ext = extend or {}
        marker = self._show_path(
            str(tid), cls=str(ext.get("class") or ""),
            letter=str(ext.get("letter") or ""), by=str(ext.get("by") or ""),
            tag=str(ext.get("tag") or ""), page_token="@@P@@")
        prefix, suffix = marker.split("@@P@@")
        m = re.search(r'href="([^"]+)"[^>]*title="跳转到尾页"', text or "")
        if m:
            tail = unquote(m.group(1))
            pm = re.search(re.escape(prefix) + r"(\d+)" + re.escape(suffix), tail)
            if pm:
                return int(pm.group(1)), 0
        try:
            return max(int(pg or 1), 1), 0
        except Exception:
            return 1, 0

    # ---------------- 主接口 ----------------
    def homeContent(self, filter):
        text = html.unescape(self._get("/") or "")
        classes = []
        seen = set()
        for m in re.finditer(r'<a[^>]*href="/vodtype/([A-Za-z0-9]+)\.html"[^>]*>(.*?)</a>',
                             text, re.S):
            slug = m.group(1)
            name = re.sub(r"<[^>]+>", "", m.group(2))
            name = re.sub(r"\s+", " ", html.unescape(name)).strip()
            if not name or len(name) > 8 or name == "更多" or name.startswith("最新"):
                continue
            if slug in seen:
                continue
            seen.add(slug)
            classes.append({"type_id": slug, "type_name": name})
        # 兜底：首页导航结构异常时使用内置分类
        if not classes:
            classes = [{"type_id": t[0], "type_name": t[1]} for t in TOP_TYPES]
        return {
            "class": classes,
            "list": self._cards(text),
            "filters": self._filters(),
        }

    def _filters(self):
        common_tail = [
            {"key": "tag", "name": "剧情", "value":
                [{"n": "全部", "v": ""}] + [{"n": t, "v": t} for t in TAGS]},
            {"key": "letter", "name": "字母", "value":
                [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in LETTERS]},
            {"key": "by", "name": "排序", "value":
                [{"n": n, "v": v} for n, v in SORTS]},
        ]
        filters = {}
        for slug, _name, subs in TOP_TYPES:
            group = [{"key": "type", "name": "类型", "value":
                      [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for n, v in subs]}]
            filters[slug] = group + common_tail
        return filters

    def homeVideoContent(self):
        return {"list": self._cards(self._get("/"))}

    def categoryContent(self, tid, pg, filter, extend):
        ext = extend or {}
        # "类型"筛选：子频道把 tid 换成自己的 slug
        sub = str(ext.get("type") or "").strip()
        real_tid = sub or str(tid or "")
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        path = self._filter_url(real_tid, page, ext)
        text = self._get(path, min_len=2000)
        items = self._cards(text)
        pagecount, total = self._page_count(text, real_tid, page, ext)
        limit = 40
        return {
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": limit,
            "total": total or max(pagecount, 1) * limit,
            "list": items,
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ""
        if not vid:
            return {"list": []}
        text = html.unescape(self._get("/voddetail%s.html" % vid, min_len=6000) or "")
        if not text or "/voddetail%s.html" % vid not in text:
            return {"list": []}

        def label(*keys):
            for key in keys:
                m = re.search(
                    r'<strong[^>]*class="[^"]*label-width[^"]*"[^>]*>\s*'
                    + re.escape(key) + r'[：:]?\s*</strong>\s*'
                    r'<span[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</span>',
                    text, re.S)
                if m:
                    v = re.sub(r"<[^>]+>", " ", m.group(1))
                    v = re.sub(r"\s+", " ", html.unescape(v)).strip()
                    if v:
                        return v
            return ""

        tags = []
        m = re.search(
            r'<strong[^>]*class="[^"]*label-width[^"]*"[^>]*>\s*类别[：:]?\s*</strong>\s*'
            r'<span[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</span>', text, re.S)
        if m:
            tags = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
                    for x in re.findall(r"<a[^>]*>(.*?)</a>", m.group(1), re.S)]
            tags = [x for x in tags if x]

        name = label("名称") or label("标题")
        if not name:
            m = re.search(r"<title>\s*《(.*?)》", text, re.S)
            name = html.unescape(m.group(1)).strip() if m else vid

        pic = ""
        thumb_inner = ""
        for am in ANCHOR_RE.finditer(text):
            attrs = am.group(1)
            if "stui-vodlist__thumb" not in attrs:
                continue
            href = self._attr(attrs, "href")
            if ("/vodplay/%s-" % vid in href) or ("/voddetail%s.html" % vid in href):
                thumb_inner = am.group(2)
                break
            if not thumb_inner:
                thumb_inner = am.group(2)
        if thumb_inner:
            pic = self._pic(self._attr(thumb_inner, "data-original")
                            or self._attr(thumb_inner, "src"))

        # 播放列表：/vodplay/{id}-{线路}-{集数}.html
        plays = []
        seen = set()
        for m in re.finditer(r"/vodplay/%s-(\d+)-(\d+)\.html" % re.escape(vid), text):
            sid, nid = m.group(1), m.group(2)
            if (sid, nid) in seen:
                continue
            seen.add((sid, nid))
            plays.append((sid, nid))
        lines = {}
        for sid, nid in plays:
            lines.setdefault(sid, []).append(nid)

        play_from = []
        play_url_list = []
        for sid in sorted(lines, key=lambda x: int(x)):
            eps = sorted(lines[sid], key=lambda x: int(x))
            play_from.append("花都" if len(lines) == 1 else "线路%s" % sid)
            parts = []
            for nid in eps:
                ename = "正片" if len(eps) == 1 else "第%s集" % nid
                parts.append("%s$%s" % (ename,
                                        self._abs("/vodplay/%s-%s-%s.html" % (vid, sid, nid))))
            play_url_list.append("#".join(parts))

        desc = ""
        m = re.search(r'<meta name="description" content="([^"]*)"', text)
        if m:
            desc = html.unescape(m.group(1)).strip()

        date = label("日期")
        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": label("演员"),
            "vod_director": label("导演"),
            "vod_year": (date[:4] if date else ""),
            "vod_area": label("分类"),
            "vod_remarks": label("时长") or "、".join(tags[:3]),
            "vod_content": desc or "、".join(tags),
            "vod_play_from": "$$$".join(play_from) if play_from else "花都",
            "vod_play_url": "$$$".join(play_url_list) if play_url_list else "正片$",
        }]}

    # ---------------- 播放 ----------------
    @staticmethod
    def _decode_url(raw):
        """播放页 url 的还原：base64(percent-encoded) -> percent-encoded -> 明文。"""
        raw = str(raw or "").strip()
        if not raw:
            return ""
        candidates = []

        def add(u):
            u = (u or "").strip()
            if u and u not in candidates:
                candidates.append(u)

        add(raw)
        cur = raw
        for _ in range(2):
            if not re.fullmatch(r"[A-Za-z0-9+/=_-]{12,}", cur):
                break
            try:
                dec = base64.b64decode(cur + "=" * (-len(cur) % 4),
                                       altchars=b"-_").decode("utf-8", "ignore")
            except Exception:
                break
            dec = dec.strip()
            if not dec or dec == cur:
                break
            add(dec)
            cur = dec

        for cand in reversed(candidates):
            for text in (unquote(cand), cand):
                text = text.replace("\\/", "/").strip()
                if text.lower().startswith(("http://", "https://")):
                    return text
        return ""

    def playerContent(self, flag, id, vipFlags):
        pid = str(id or "").strip()
        if "$" in pid:
            pid = pid.split("$")[-1].strip()
        if not pid:
            return {"parse": 0, "url": ""}
        if not pid.startswith("http"):
            pid = self._abs(pid)
        text = self._get(pid, min_len=1500) or ""
        url = ""
        m = re.search(r"var\s+player_data\s*=\s*(\{.*?\})\s*</script>", text, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
            except Exception:
                data = None
            if isinstance(data, dict):
                url = self._decode_url(data.get("url"))
        if not url:
            m = re.search(r'"url"\s*:\s*"([A-Za-z0-9+/=%_\-]{16,})"', text)
            if m:
                url = self._decode_url(m.group(1))
        if not url:
            m = re.search(r'(https?[^"\'\s\\]+?\.(?:m3u8|mp4|flv)[^"\'\s\\]*)', text)
            url = m.group(1).replace("\\/", "/") if m else ""
        if not url:
            return {"parse": 1, "url": pid, "header": PLAY_HEADERS}
        if re.search(r"\.(?:m3u8|mp4|flv|ts|m4v)(?:\?|$)", url, re.I):
            return {"parse": 0, "playUrl": "", "url": url, "header": PLAY_HEADERS}
        return {"parse": 1, "url": url, "header": PLAY_HEADERS}

    # ---------------- 搜索 ----------------
    @staticmethod
    def _search_path(key, page):
        kw = quote(str(key or ""))
        if page and int(page) > 1:
            return "/vodsearch/%s----------%d---.html" % (kw, int(page))
        return "/vodsearch/-------------.html?wd=" + kw

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        path = self._search_path(key, page)
        text = self._get(path, min_len=2000, attempts=2)
        items = self._cards(text)
        pagecount, total = self._page_info(text)
        return {
            "list": items,
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": 40,
            "total": total or max(pagecount, 1) * 40,
        }

    def isVideoFormat(self, url):
        u = (url or "").lower().split("?")[0]
        return u.endswith((".m3u8", ".mp4", ".flv", ".ts", ".m4v", ".webm", ".mov"))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def getDependence(self):
        return []

    def destroy(self):
        try:
            if self.sess:
                self.sess.close()
        except Exception:
            pass
        return None
