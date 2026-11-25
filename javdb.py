# -*- coding: utf-8 -*-
"""
JavDB TVBox Py 源（浏览 / 搜索 / 详情）v3 —— 2026-11-25 按实测重写
来源：https://javdb.com

实测结论（2026-11-25，手机浏览器 + 用户自己的网络）：
- 分类（homeContent）：全部、有码、欧美、无码、FC2、动漫、热播、TOP250，
  加上女优（推荐 / 有码 / 无码 / 欧美四个子页）和类别（标签索引）。
  名字里用短的“·登录”标记需要登录的分类，之前“（需登录）”太长，
  在 FongMi 里排得不好看。
- 女优页实测（2026-11-25 18:07）：
  /actors 就是推荐页：新人 9 张、月榜 9 张、Fanza 推薦 25 张，共 43 张卡片，
  每张卡只有头像 + 名字，没有作品数和评分，链接形如 /actors/0R0O7（短 ID），
  本页没有翻页。真正的分页列表在子页签：/actors/censored（有码，50 张/页）、
  /actors/uncensored（无码）、/actors/western（欧美），翻页 ?page=N。
  /actors/recommend 不存在，打开是 404。
  女优个人页 /actors/{短ID}：头像、名字、作品总数（“4 部影片”“236 部影片”）、
  别名，作品列表 40 部/页，?page=N，每部作品有封面、番号、标题、评分、日期。
- 类别页实测：/tags 和一切 /tags?cX=N 列表页都要登录，未登录会 302 到 /login。
  标签链接格式是 /tags?c{分类号}={标签ID}，例如“單體作品”→ /tags?c7=28。
  /tags 索引页本身的结构没有实测到（未登录看不到），所以类别索引解析是
  按常规写法尽力抠 /tags?cN=M 链接，抠不到会提示，不会编假标签。
  有 Cookie 的情况下在 FongMi 里应该能用。
- 详情页实测（作品 https://javdb.com/v/WwA47g，番号 112226-001）：
  番号、标题、日期 2026-11-22、时长 29 分钟、片商、系列、演员、
  类别（页面叫“类别”，不是“标签”）、评分 4.33 分（17 人评价）、
  45 人想看 / 17 人看过，这些都能抓到。导演字段有的作品有、有的没有，
  有就抓，没有就不写，不编。视频卡片结构：<a class="box"> 里番号在
  <strong> 内，评分在 <span class="score"> 内，日期在 <span class="meta"> 内。
- 剧情简介：JavDB 详情页根本没有简介栏目，全文搜“简介”无结果。
  所以这个源不会凭空编剧情。详情简介区用本页真实信息拼成：
  标题 + 日期 / 时长 / 片商 / 系列 / 演员 / 类别 / 评分，
  再加一条用户短评（如果页面有的话，会标明是“短评”不是简介）。
- 剧照：有，封面 1 张 + 剧照 5 张，地址规律已核验：
  封面 https://c0.jdbstatic.com/covers/ww/WwA47g.jpg
  剧照 https://c0.jdbstatic.com/samples/ww/WwA47g_s_0.jpg … _s_4.jpg
  （ww 是详情页编码 WwA47g 的前两位小写，剧照序号从 0 开始）。
  剧照放在“剧照”播放源里，点开用 pics:// 翻图。
- 预告片：详情页没有预告片，全文搜“预告”无结果，也没有播放器。
  “下载”按钮只是跳到本页磁链区的锚点（#magnet-links）。
  所以这个源没有预告片可抓，不会造一个假的预告片地址。
  登录后有个站内播放页 /v/{编码}/play，playerContent 里留了
  登录后去播放页找 m3u8 / mp4 的探针，找不到就返回空，不猜地址。
- 磁力：实测 2 条，带大小和日期（例：112226-001-CARIB，1.33GB）。
- 登录：匿名点详情会被跳到 /login（实测就是这样，提示
  “此内容需要登入才能查看或操作”）。无码 / FC2 / 动漫 / 热播
  本来就要登录；有码 / 欧美匿名一般能看，但个别作品也可能跳登录。
  想看全站就填 Cookie，填法见下面 COOKIE 注释。

登录用法（可选，不填也能用公开区）：
  把你自己的 JavDB 登录 Cookie 填到下面 COOKIE = "" 里，只填在你自己
  本地这份文件里，不要把填好 Cookie 的文件发给别人。
  本文件里不保存任何真实 Cookie。
"""

# 填你自己的登录 Cookie，例如 "over18=1; _jdb_session=...; ..."
# 留空 = 匿名访问，只能看公开区。
COOKIE = ""

import html as _html
import re

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
    def __init__(self):
        self.host = "https://javdb.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://javdb.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if COOKIE:
            self.headers["Cookie"] = COOKIE

    # ---------- 通用 ----------
    def _get(self, url):
        if requests is not None:
            try:
                r = requests.get(url, headers=self.headers, timeout=15)
                r.encoding = "utf-8"
                return r.text if r.status_code == 200 else ""
            except Exception:
                return ""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _clean(text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = _html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _first(pattern, html, default=""):
        m = re.search(pattern, html, re.S)
        return m.group(1).strip() if m else default

    @staticmethod
    def _is_login_page(html):
        if not html:
            return False
        head = html[:4000]
        return ("此內容需要登入" in head or "此内容需要登入" in head
                or "您可能還未登入" in head or "您可能还未登入" in head
                or 'action="/login"' in head or 'action="https://javdb.com/login"' in head)

    def _parse_list(self, html):
        """从列表页解析作品卡片。卡片结构：<a class="box" href="/v/CODE">，
        番号在 <strong> 内，评分在 <span class="score"> 内，
        日期在 <span class="meta"> 内。按首次出现去重。"""
        vods = []
        seen = set()
        for m in re.finditer(r'<a\s[^>]*href="/v/([A-Za-z0-9]+)"[^>]*>(.*?)</a>', html, re.S):
            code = m.group(1)
            if code in seen:
                continue
            seen.add(code)
            inner = m.group(2)
            code_no = self._clean(self._first(r"<strong[^>]*>([^<]+)</strong>", inner))
            name = self._clean(inner)
            score = self._first(r"(\d\.\d{1,2})\s*分", inner)
            date = self._first(r"(\d{4}-\d{2}-\d{2})", inner)
            # 评分和日期已经放进备注了，就从名字里去掉，名字只留番号和标题
            if score:
                name = re.sub(r"\s*\d\.\d{1,2}\s*分", "", name).strip()
            if date:
                name = name.replace(date, "").strip()
            name = re.sub(r"\s+", " ", name).strip()
            if code_no and not name.startswith(code_no):
                name = (code_no + " " + name).strip()
            remarks = ""
            if score:
                remarks = "★" + score
            if date:
                remarks = (remarks + " · " + date) if remarks else date
            if "磁" in inner or "magnet" in inner.lower():
                remarks = (remarks + " · 磁链") if remarks else "磁链"
            # 封面优先用卡片里真实的 img 地址，拿不到再按规律拼
            img = self._first(r'<img[^>]+src="([^"]+)"', inner)
            if img.startswith("//"):
                img = "https:" + img
            if not img.startswith("http"):
                img = "https://c0.jdbstatic.com/covers/{}/{}.jpg".format(
                    code[:2].lower(), code)
            vods.append({
                "vod_id": code,
                "vod_name": name,
                "vod_pic": img,
                "vod_remarks": remarks,
            })
        return vods

    def _parse_actors(self, html):
        """从女优列表页解析女优卡片：<a href="/actors/短ID"> 头像 + 名字。
        子页签 /actors/censored、/actors/western 之类的链接不是短 ID，
        不会误抓进来。"""
        vods = []
        seen = set()
        for m in re.finditer(r'<a\s[^>]*href="/actors/([A-Za-z0-9]{4,6})"[^>]*>(.*?)</a>', html, re.S):
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            inner = m.group(2)
            name = self._clean(inner)
            if not name:
                continue
            img = self._first(r'<img[^>]+src="([^"]+)"', inner)
            if img.startswith("//"):
                img = "https:" + img
            vods.append({
                "vod_id": "actor:" + aid,
                "vod_name": name,
                "vod_pic": img if img.startswith("http") else "",
                "vod_remarks": "",
            })
        return vods

    def _parse_tags(self, html):
        """从 /tags 索引页解析标签：链接形如 /tags?c7=28。
        /tags 页结构没有实测到，按常规写法尽力抠，抠不到返回空。"""
        vods = []
        seen = set()
        for m in re.finditer(r'<a\s[^>]*href="/tags\?(c\d+=\d+)"[^>]*>(.*?)</a>', html, re.S):
            param = m.group(1)
            if param in seen:
                continue
            seen.add(param)
            inner = m.group(2)
            name = self._clean(inner)
            count = self._first(r"\(?\s*(\d+)\s*\)?\s*$", name)
            if count:
                name = re.sub(r"\(?\s*\d+\s*\)?\s*$", "", name).strip()
            if not name:
                continue
            vods.append({
                "vod_id": "tag:" + param,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": (count + " 部") if count else "",
            })
        return vods

    def _first_magnet(self, html):
        m = re.search(r'(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^"\'\s<>]*)', html or "")
        if not m:
            return ""
        return m.group(1).replace("&amp;", "&")

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=None):
        # 分类按 2026-11-25 实测的站内导航写；“·登录”是短标记，
        # 之前“（需登录）”太长，在 FongMi 里排得不好看。
        classes = [
            {"type_id": "all", "type_name": "全部"},
            {"type_id": "censored", "type_name": "有码"},
            {"type_id": "western", "type_name": "欧美"},
            {"type_id": "uncensored", "type_name": "无码·登录"},
            {"type_id": "fc2", "type_name": "FC2·登录"},
            {"type_id": "anime", "type_name": "动漫·登录"},
            {"type_id": "rankings/playback", "type_name": "热播·登录"},
            {"type_id": "rankings/top250", "type_name": "TOP250·登录"},
            {"type_id": "actors", "type_name": "女优·推荐"},
            {"type_id": "actors/censored", "type_name": "女优·有码"},
            {"type_id": "actors/uncensored", "type_name": "女优·无码·登录"},
            {"type_id": "actors/western", "type_name": "女优·欧美"},
            {"type_id": "tags", "type_name": "类别·登录"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._parse_list(html)}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        tid = (tid or "all").strip("/")
        pg = int(pg)
        # 女优列表：/actors 是推荐页（43 张，无翻页），
        # 子页签 /actors/censored 等 50 张/页，?page=N
        if tid == "actors":
            if pg > 1:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 50, "total": 43}
            html = self._get(self.host + "/actors")
            vods = self._parse_actors(html)
            return {"list": vods, "page": 1, "pagecount": 1, "limit": 50, "total": len(vods)}
        if tid.startswith("actors/"):
            html = self._get("{}/{}?page={}".format(self.host, tid, pg))
            if self._is_login_page(html):
                return {"list": [], "msg": "这个女优分类需要登录，请在文件里填 Cookie 后再试"}
            return {"list": self._parse_actors(html), "page": pg,
                    "pagecount": 9999, "limit": 50, "total": 999999}
        # 类别索引：/tags 需要登录，未登录会跳登录页
        if tid == "tags":
            html = self._get(self.host + "/tags")
            if self._is_login_page(html):
                return {"list": [], "msg": "类别页需要登录，请在文件里填 Cookie 后再试"}
            tags = self._parse_tags(html)
            if not tags:
                return {"list": [], "msg": "没抓到标签，可能是页面结构变了"}
            return {"list": tags, "page": 1, "pagecount": 1,
                    "limit": 100, "total": len(tags)}
        # 作品列表
        if tid == "all":
            url = "{}/?page={}".format(self.host, pg)
        else:
            url = "{}/{}?page={}".format(self.host, tid, pg)
        html = self._get(url)
        if self._is_login_page(html):
            return {"list": [], "msg": "这个分类需要登录，请在文件里填 Cookie 后再试"}
        return {"list": self._parse_list(html), "page": pg,
                "pagecount": 9999, "limit": 20, "total": 999999}

    def searchContent(self, key, quick=False, pg=1):
        from urllib.parse import quote
        url = "{}/search?q={}&f=all&page={}".format(self.host, quote(key), pg)
        html = self._get(url)
        if self._is_login_page(html):
            return {"list": [], "msg": "搜索需要登录，请在文件里填 Cookie 后再试"}
        return {"list": self._parse_list(html)}

    def detailContent(self, ids):
        code = ids[0] if isinstance(ids, list) else str(ids)
        # 女优个人页：/actors/{短ID}，作品当作“作品”播放源列出，
        # 每部作品点开时再去详情页取磁力（playerContent 的 video: 分支）。
        if code.startswith("actor:"):
            aid = code.split(":", 1)[1]
            html = self._get("{}/actors/{}".format(self.host, aid))
            if self._is_login_page(html):
                return {"list": [], "msg": "这位女优的页面需要登录，请在文件里填 Cookie 后再试"}
            if not html:
                return {"list": []}
            name = self._clean(self._first(r"<title>([^<]+)</title>", html))
            name = re.sub(r"\s*[-–—]\s*JavDB\s*$", "", name).strip() or aid
            total = self._first(r"(\d+)\s*部影片", html)
            avatar = self._first(r'<img[^>]+src="(https?://[^"]+)"', html)
            works = self._parse_list(html)
            lines = ["女优：" + name]
            if total:
                lines.append("作品总数：" + total + " 部（这里列出第 1 页前 {} 部）。".format(len(works)))
            lines.append("点一部作品，就会去它的详情页取磁力；没有磁力的作品点开是空的。")
            play_url = "#".join(
                "{}${}".format(w["vod_name"], "video:" + w["vod_id"]) for w in works)
            vod = {
                "vod_id": code,
                "vod_name": name,
                "vod_pic": avatar,
                "vod_actor": name,
                "vod_content": "\n".join(lines),
                "vod_remarks": (total + " 部") if total else "",
                "vod_play_from": "作品" if works else "",
                "vod_play_url": play_url,
            }
            return {"list": [vod]}
        # 标签页：/tags?c7=28，第一页作品当作“作品”播放源列出
        if code.startswith("tag:"):
            param = code.split(":", 1)[1]
            html = self._get("{}/tags?{}".format(self.host, param))
            if self._is_login_page(html):
                return {"list": [], "msg": "这个类别需要登录，请在文件里填 Cookie 后再试"}
            if not html:
                return {"list": []}
            works = self._parse_list(html)
            name = self._clean(self._first(r"<title>([^<]+)</title>", html))
            name = re.sub(r"\s*[-–—]\s*JavDB\s*$", "", name).strip() or param
            play_url = "#".join(
                "{}${}".format(w["vod_name"], "video:" + w["vod_id"]) for w in works)
            vod = {
                "vod_id": code,
                "vod_name": "类别：" + name,
                "vod_pic": works[0]["vod_pic"] if works else "",
                "vod_content": "类别：" + name + "\n这里列出第 1 页前 {} 部作品，点一部就会去它的详情页取磁力。".format(len(works)),
                "vod_remarks": "共 {} 部".format(len(works)) if works else "",
                "vod_play_from": "作品" if works else "",
                "vod_play_url": play_url,
            }
            return {"list": [vod]}
        # 作品详情页
        html = self._get("{}/v/{}".format(self.host, code))
        if not html:
            return {"list": []}
        if self._is_login_page(html):
            return {"list": [], "msg": "这部需要登录才能看详情，请在文件里填 Cookie 后再试"}

        def find(pattern, default=""):
            return self._clean(self._first(pattern, html, default))

        # 番号一般形如 HOKS-240 / 112226-001，取页面里第一次出现的
        code_no = find(r"([A-Z0-9]{2,6}-\d{3,5})")
        pic = "https://c0.jdbstatic.com/covers/{}/{}.jpg".format(
            code[:2].lower(), code)
        title = find(r"<title>([^<]+)</title>")
        title = re.sub(r"\s*-\s*JavDB\s*$", "", title).strip() or (code_no or code)

        # 女优：详情页 /actors/xxxx 链接的文字
        actors = []
        for m in re.finditer(r'href="/actors/[^"]+"[^>]*>([^<]+)</a>', html):
            name = self._clean(m.group(1))
            if name and name not in actors:
                actors.append(name)

        # 类别：页面里叫“类别”，链接形如 /tags?c7=28
        tags = []
        for m in re.finditer(r'href="/tags\?[^"]*"[^>]*>([^<]+)</a>', html):
            name = self._clean(m.group(1))
            if name and name not in tags:
                tags.append(name)

        # 片商 / 系列 / 导演（导演有的作品有、有的没有，有就抓）
        maker = find(r'href="/makers/[^"]+"[^>]*>([^<]+)</a>')
        series = find(r'href="/series/[^"]+"[^>]*>([^<]+)</a>')
        director = find(r'href="/directors/[^"]+"[^>]*>([^<]+)</a>')
        date = find(r"(\d{4}-\d{2}-\d{2})")
        duration = find(r"(\d+)\s*分钟")
        score = find(r"(\d\.\d{1,2})\s*分")
        want = find(r"(\d+)\s*人想看")
        seen_n = find(r"(\d+)\s*人看过")

        # 剧照：页面里的 samples 地址，实测形如
        # https://c0.jdbstatic.com/samples/ww/WwA47g_s_0.jpg
        stills = []
        for m in re.finditer(
                r'https://c0\.jdbstatic\.com/samples/[A-Za-z0-9/_.\-]+\.jpg', html):
            url = m.group(0)
            if url not in stills:
                stills.append(url)

        def _still_key(u):
            mm = re.search(r"_s_(\d+)\.jpg", u)
            return int(mm.group(1)) if mm else 999
        stills.sort(key=_still_key)

        # 短评：页面“短评”区第一条用户评论（标明是短评，不是官方简介）
        comment = ""
        cm = re.search(r"短評.{0,200}?<[^>]+>([^<]{4,300})</", html, re.S)
        if not cm:
            cm = re.search(r"短评.{0,200}?<[^>]+>([^<]{4,300})</", html, re.S)
        if cm:
            comment = self._clean(cm.group(1))

        # 磁力：页面里所有 magnet:? 链接，去重，保留顺序
        magnets = []
        for m in re.finditer(r'(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^"\'\s<>]*)', html):
            mag = m.group(1).replace("&amp;", "&")
            if mag not in magnets:
                magnets.append(mag)

        # 简介区：JavDB 没有官方剧情简介，这里只拼本页真实信息，
        # 并写明没有简介，不编剧情。
        lines = []
        lines.append("【简介】JavDB 本身没有剧情简介，下面是这部作品的真实信息。")
        lines.append("番号：" + (code_no or code))
        lines.append("标题：" + title)
        if date:
            lines.append("日期：" + date + ((" · 时长 " + duration + " 分钟") if duration else ""))
        if maker:
            lines.append("片商：" + maker)
        if series:
            lines.append("系列：" + series)
        if director:
            lines.append("导演：" + director)
        if actors:
            lines.append("演员：" + ", ".join(actors))
        if tags:
            lines.append("类别：" + " / ".join(tags))
        if score:
            lines.append("评分：" + score + " 分" +
                         (("（" + want + " 人想看 · " + seen_n + " 人看过）") if want else ""))
        if comment:
            lines.append("短评（用户评论，不是简介）：" + comment)
        lines.append("剧照：共 {} 张，点“剧照”播放源翻看。".format(len(stills)))
        lines.append("预告片：JavDB 详情页没有预告片，磁力在“磁力”播放源里。")

        remarks = ""
        if score:
            remarks = "★" + score
        if duration:
            remarks = (remarks + " · " + duration + "分钟") if remarks else duration + "分钟"
        if magnets:
            remarks = (remarks + " · 磁力{}条".format(len(magnets))) if remarks else "磁力{}条".format(len(magnets))
        if stills:
            remarks = (remarks + " · 剧照{}张".format(len(stills))) if remarks else "剧照{}张".format(len(stills))

        play_from = []
        play_url = []
        if magnets:
            play_from.append("磁力")
            play_url.append("#".join(
                "磁力{0}${1}".format(i + 1, mag)
                for i, mag in enumerate(magnets)))
        if stills:
            play_from.append("剧照")
            play_url.append("剧照$pics://" + "&&".join(stills))

        vod = {
            "vod_id": code,
            "vod_name": title if title.startswith(code_no) else ((code_no + " " + title) if code_no else title),
            "vod_pic": pic,
            "type_name": " / ".join(tags[:4]),
            "vod_year": date[:4] if date else "",
            "vod_area": "",
            "vod_actor": ", ".join(actors),
            "vod_director": director or maker,
            "vod_content": "\n".join(lines),
            "vod_remarks": remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        # 剧照源：id 就是 pics:// 开头的图串，直接交给播放器翻图
        if isinstance(id, str) and id.startswith("pics://"):
            return {"parse": 0, "url": id, "header": self.headers}
        # 磁力源：id 本身就是 magnet:? 链接，直接返回给播放器，
        # 能不能播取决于播放器是否支持磁力。
        if isinstance(id, str) and id.startswith("magnet:"):
            return {"parse": 0, "url": id, "header": self.headers}
        # 女优 / 类别里的作品：点开时才去详情页取第一条磁力
        if isinstance(id, str) and id.startswith("video:"):
            code = id.split(":", 1)[1]
            html = self._get("{}/v/{}".format(self.host, code))
            mag = self._first_magnet(html)
            return {"parse": 0, "url": mag, "header": self.headers}
        # 其他：只有填了 COOKIE 后才去站内播放页找 m3u8 / mp4；
        # JavDB 详情页没有预告片，这个播放页也未核验过，
        # 找不到就返回空，不猜地址。
        url = ""
        if COOKIE:
            html = self._get("{}/v/{}/play?from_ranking=0".format(self.host, id))
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
            if m:
                url = m.group(1)
        return {"parse": 0, "url": url, "header": self.headers}

    def localProxy(self, param):
        return [200, "video/MP2T", None, ""]
