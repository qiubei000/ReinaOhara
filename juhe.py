# -*- coding: utf-8 -*-
"""
亚洲视频合集（五站合一）爬虫（TVBox / FongMi / OK影视 等）
================================================
合并了五个成人视频站，一个文件当五个源用：
- 6chua.com（图片 CDN：pic.6chua.com）
- newasiantube.com（图片 CDN：public.newasiantube.com）
- homejavp.com（图片 CDN：gallery.homejavp.com）
- jiajianjian.com（图片 CDN：pics.jiajianjian.com）
- megapsite.com（图片 CDN：i.megapsite.com；和前四站同后端）

用法：像以前一样导入 OK影视即可。分类名前带站名区分，
如「6chua·亚洲」「新亚·亚洲」「HJAVP·亚洲」「JJJ·亚洲」「MEGA·亚洲」；搜索会同时搜
五个站并合并结果；点进详情、播放时按 vod_id 里的站名前缀
自动走对应站点的解析。

标题中文：四个站都有自带的中文版（/zh/），列表标题直接取中文版
的机翻标题；中文版打不开时（6chua 的 /zh/ 有时会 403）自动退回
英文版。视频页本身没有中文版，所以详情页标题用的是列表里的
中文标题（编在 vod_id 里带过去）。机翻质量一般，番号、代码类
标题翻不出来，会保持原样。

各站页面结构（2026-11-24 实测）：
- 卡片：6chua 是 <div class=ugu>，newasiantube 是 <ul class="thumbs"><li>，
  homejavp 是 <div class=uos>，jiajianjian 是 <div class=yc>；首页/分类卡片 href 是 /c/?g=...&t=...&i=...&c=...
  （302 跳到视频页），搜索卡片 href 是直链 /?video= 或 /?v= 或 /?content=。
- 前四站视频页都有 <video poster="..."> 和
  <source src="https://<图床>/hls/v1/p/<vid>/<签名>/master.m3u8">，
  m3u8 带签名、带时效，播放时必须现取现播（实测 480p/720p 可播）。
- 前四站首页/分类的 ?page= 是假的：第 2 页起内容和第 1 页完全相同，
  所以分类只返回第 1 页；搜索的翻页是真的。
- newasiantube 有排序：/<分类>/、/<分类>/newest-videos/、/<分类>/longest-videos/。
- 注意：newasiantube 少量卡片是外站链接，/c/ 会跳到合作站
  asianpornone.com 的分类页而不是视频页，那种播不了，会退回网页打开。
- megapsite.com 和前四站同后端：卡片是 <div class=xjy>，href 是 /c/?g=...&t=...&i=...&c=...
  （302 跳到 /<分类>/?content=<vid>），搜索卡片直接就是 /<分类>/?content=<vid>，
  封面是 //i.megapsite.com/a/cache1869/...（分类）或 /t2/...jpg（搜索）；
  视频页有 <video poster="//i.megapsite.com/vs/<vid>.jpg"> 和签名的 m3u8，
  时长在 knownDuration（秒）。有中文版（/zh/，机翻）；首页是分类索引、没有视频，
  所以推荐取 /asian/。分类的 ?page= 是假的（第 2 页和第 1 页相同），
  搜索的翻页是真的（/?q=关键词&page=N）。

vod_id 格式：<站名>|<卡片 href>，如 6chua|/c/?g=...、nat|/?v=...。
"""
import re
import time
from html import unescape
from urllib.parse import quote

try:
    from base.spider import Spider
except Exception:  # 本地测试用的桩
    class Spider(object):
        pass

try:
    import requests
except Exception:
    requests = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ---------------- 站点配置 ----------------
# dur_kind: "mmss" = 直接取 118:49；"sec" = knownDuration 秒数，需换算
SITES = {
    "6chua": {
        "name": "6chua",
        "host": "https://www.6chua.com",
        "search_param": "search",
        "sorts": None,
        "block": r"<div class=ugu>(.*?)(?=<div class=ugu>|$)",
        "href": r"<a href='((?:/zh)?/c/\?[^']+|(?:/zh)?/\?video=[^']+)'",
        "img": r"""<img[^>]+src=["']([^"']+)["']""",
        "title": r"<div class=shv>([^<]+)</div>",
        "title_alt": None,
        "dur": r"<i class='nwj bps'></i><div>(\d+:\d+)</div>",
        "detail_title": [r"<title>([^<]+)</title>"],
        "detail_poster": r'<video[^>]+poster="([^"]+)"',
        "detail_dur": [(r"<div class=ptd>.*?<span>(\d+:\d+)</span>", "mmss")],
        "detail_tags": None,
        "cats": [
            ("latest", "最新"), ("asian", "亚洲"), ("amateur", "业余"),
            ("anal", "肛交"), ("ass", "臀部"), ("babes", "美女"),
            ("bbw", "丰满"), ("bdsm", "SM"), ("big-tits", "大胸"),
            ("blonde", "金发"), ("blowjob", "口交"), ("brunette", "棕发"),
            ("bukkake", "颜射"), ("celebrities", "名人"), ("college", "大学"),
            ("couple", "情侣"), ("creampie", "内射"), ("cumshot", "射精"),
            ("deep-throat", "深喉"), ("erotic", "情色"), ("facial", "颜面"),
            ("fetish", "恋物"), ("gangbang", "群交"), ("glamour", "写真"),
            ("group", "群体"), ("hairy", "毛发"), ("handjob", "手淫"),
            ("hardcore", "硬核"), ("homemade", "自拍"), ("interracial", "跨种族"),
            ("lesbian", "女同"), ("lingerie", "内衣"), ("massage", "按摩"),
            ("masturbation", "自慰"), ("mature", "成熟"), ("milf", "熟女"),
            ("nurse", "护士"), ("office", "办公室"), ("orgy", "群交派对"),
            ("outdoor", "户外"), ("pov", "主观视角"), ("public", "公共"),
            ("pussy", "阴部"), ("schoolgirl", "女学生"), ("secretary", "秘书"),
            ("shemale", "人妖"), ("solo", "独自"), ("stockings", "丝袜"),
            ("teacher", "老师"), ("teen", "青少年"), ("threesome", "三人"),
            ("toys", "玩具"), ("uniform", "制服"), ("voyeur", "偷窥"),
            ("webcam", "摄像头"), ("wife", "人妻"),
        ],
    },
    "nat": {
        "name": "新亚",
        "host": "https://www.newasiantube.com",
        "search_param": "k",
        "sorts": [("最热门", ""), ("最新", "newest-videos"), ("最长", "longest-videos")],
        # 2026-11-24 实测：这站带 Referer 请求必断流/403，不带 Referer 才正常
        "no_referer": True,
        "block": r"<li>(.*?)</li>",
        "href": r'<a class=thumba href="((?:/zh)?/c/\?[^"]+|(?:/zh)?/\?v=[^"]+)"',
        "img": r'<img[^>]+src="([^"]+)"',
        "title": r"""<div class="wrap"><p>([^<]+)</p></div>""",
        "title_alt": r'<img[^>]+alt="([^"]+)"',
        "dur": r"<strong>(\d+:\d+)</strong>",
        "detail_title": [r"<h1[^>]*>([^<]+)</h1>", r"<title>([^<]+)</title>"],
        "detail_poster": r'<video[^>]+poster="([^"]+)"',
        "detail_dur": [(r"knownDuration:(\d+)", "sec")],
        "detail_tags": r"Tags:</span><div>(.*?)</div>",
        "cats": [
            ("latest", "最新"), ("asian", "亚洲"), ("amateur", "业余"),
            ("anal", "肛交"), ("ass", "臀部"), ("babes", "美女"),
            ("bbw", "丰满"), ("bdsm", "SM"), ("big-tits", "大胸"),
            ("blonde", "金发"), ("blowjob", "口交"), ("brunette", "棕发"),
            ("bukkake", "颜射"), ("celebrities", "名人"), ("college", "大学"),
            ("couple", "情侣"), ("creampie", "内射"), ("cumshot", "射精"),
            ("deep-throat", "深喉"), ("erotic", "情色"), ("facial", "颜面"),
            ("fetish", "恋物"), ("gangbang", "群交"), ("glamour", "写真"),
            ("group", "群体"), ("hairy", "毛发"), ("handjob", "手淫"),
            ("hardcore", "硬核"), ("hentai", "H漫"), ("homemade", "自拍"),
            ("interracial", "跨种族"), ("lesbian", "女同"), ("lingerie", "内衣"),
            ("massage", "按摩"), ("masturbation", "自慰"), ("mature", "成熟"),
            ("milf", "熟女"), ("nurse", "护士"), ("office", "办公室"),
            ("orgy", "群交派对"), ("outdoor", "户外"), ("pov", "主观视角"),
            ("public", "公共"), ("pussy", "阴部"), ("schoolgirl", "女学生"),
            ("secretary", "秘书"), ("shemale", "人妖"), ("solo", "独自"),
            ("stockings", "丝袜"), ("teacher", "老师"), ("teen", "青少年"),
            ("threesome", "三人"), ("toys", "玩具"), ("uniform", "制服"),
            ("voyeur", "偷窥"), ("webcam", "摄像头"), ("wife", "人妻"),
        ],
    },
    "hjavp": {
        "name": "HJAVP",
        "host": "https://www.homejavp.com",
        "search_param": "k",
        "sorts": None,
        "block": r"<div class=uos>(.*?)(?=<div class=uos>|$)",
        "href": r"<a href='((?:/zh)?/c/\?[^']+|(?:/zh)?/\?v=[^']+)'",
        "img": r"""<img[^>]+src=["']([^"']+)["']""",
        "title": r"<div class=bix>([^<]+)</div>",
        "title_alt": None,
        "dur": r"<i class='yys eto'></i><div>(\d+:\d+)</div>",
        "detail_title": [r"<title>([^<]+)</title>"],
        "detail_poster": r'<video[^>]+poster="([^"]+)"',
        "detail_dur": [(r"<div class=per>.*?<span>(\d+:\d+)</span>", "mmss"),
                       (r"knownDuration:(\d+)", "sec")],
        "detail_tags": None,
        "cats": [
            ("latest", "最新"), ("asian", "亚洲"), ("amateur", "业余"),
            ("anal", "肛交"), ("ass", "臀部"), ("babes", "美女"),
            ("bbw", "丰满"), ("bdsm", "SM"), ("big-tits", "大胸"),
            ("blonde", "金发"), ("blowjob", "口交"), ("brunette", "棕发"),
            ("bukkake", "颜射"), ("celebrities", "名人"), ("college", "大学"),
            ("couple", "情侣"), ("creampie", "内射"), ("cumshot", "射精"),
            ("deep-throat", "深喉"), ("erotic", "情色"), ("facial", "颜面"),
            ("fetish", "恋物"), ("gangbang", "群交"), ("group", "群体"),
            ("hairy", "毛发"), ("handjob", "手淫"), ("hardcore", "硬核"),
            ("homemade", "自拍"), ("interracial", "跨种族"), ("lesbian", "女同"),
            ("lingerie", "内衣"), ("massage", "按摩"), ("masturbation", "自慰"),
            ("mature", "成熟"), ("milf", "熟女"), ("nurse", "护士"),
            ("office", "办公室"), ("orgy", "群交派对"), ("outdoor", "户外"),
            ("pov", "主观视角"), ("public", "公共"), ("pussy", "阴部"),
            ("schoolgirl", "女学生"), ("secretary", "秘书"), ("shemale", "人妖"),
            ("solo", "独自"), ("stockings", "丝袜"), ("teacher", "老师"),
            ("teen", "青少年"), ("threesome", "三人"), ("toys", "玩具"),
            ("uniform", "制服"), ("voyeur", "偷窥"), ("webcam", "摄像头"),
            ("wife", "人妻"),
        ],
    },
    "jjj": {
        "name": "JJJ",
        "host": "https://www.jiajianjian.com",
        "search_param": "query",
        "sorts": None,
        "block": r"<div class=yc>(.*?)(?=<div class=yc>|$)",
        "href": r"<a href='((?:/zh)?/c/\?[^']+|(?:/zh)?/\?content=[^']+)'",
        "img": r"""<img[^>]+src=["']([^"']+)["']""",
        "title": r"<div class=dci>([^<]+)</div>",
        "title_alt": None,
        "dur": r"<i class='jlz eqw'></i><div>(\d+:\d+)</div>",
        "detail_title": [r"<title>([^<]+)</title>"],
        "detail_poster": r'<video[^>]+poster="([^"]+)"',
        "detail_dur": [(r"<div class=zs>.*?<span>(\d+:\d+)</span>", "mmss"),
                       (r"knownDuration:(\d+)", "sec")],
        "detail_tags": None,
        "cats": [
            ("latest", "最新"), ("asian", "亚洲"), ("amateur", "业余"),
            ("anal", "肛交"), ("ass", "臀部"), ("babes", "美女"),
            ("bbw", "丰满"), ("bdsm", "SM"), ("big-tits", "大胸"),
            ("blonde", "金发"), ("blowjob", "口交"), ("brunette", "棕发"),
            ("bukkake", "颜射"), ("celebrities", "名人"), ("college", "大学"),
            ("couple", "情侣"), ("creampie", "内射"), ("cumshot", "射精"),
            ("deep-throat", "深喉"), ("erotic", "情色"), ("facial", "颜面"),
            ("fetish", "恋物"), ("gangbang", "群交"), ("glamour", "写真"),
            ("group", "群体"), ("hairy", "毛发"), ("handjob", "手淫"),
            ("hardcore", "硬核"), ("homemade", "自拍"), ("interracial", "跨种族"),
            ("lesbian", "女同"), ("lingerie", "内衣"), ("massage", "按摩"),
            ("masturbation", "自慰"), ("mature", "成熟"), ("milf", "熟女"),
            ("nurse", "护士"), ("office", "办公室"), ("orgy", "群交派对"),
            ("outdoor", "户外"), ("pov", "主观视角"), ("public", "公共"),
            ("pussy", "阴部"), ("schoolgirl", "女学生"), ("secretary", "秘书"),
            ("shemale", "人妖"), ("solo", "独自"), ("stockings", "丝袜"),
            ("teacher", "老师"), ("teen", "青少年"), ("threesome", "三人"),
            ("toys", "玩具"), ("uniform", "制服"), ("voyeur", "偷窥"),
            ("webcam", "摄像头"), ("wife", "人妻"),
        ],
    },
    "mega": {
        "name": "MEGA",
        "host": "https://www.megapsite.com",
        "search_param": "q",
        "sorts": None,
        # 和前四站同后端；首页是分类索引、没有视频卡片，推荐取 /asian/。
        "home_video": "/asian/",
        "block": r"<div class=xjy>(.*?)(?=<div class=xjy>|$)",
        "href": r"<a href='((?:/zh)?/c/\?[^']+|(?:/zh)?/[a-z0-9-]+/\?content=[^']+)'",
        "img": r"""<img[^>]+src=["']([^"']+)["']""",
        "title": r"<div class=jvb>([^<]+)</div>",
        "title_alt": None,
        "dur": r"<i class='sds uja'></i><div>(\d+:\d+(?::\d+)?)</div>",
        "detail_title": [r"<title>([^<]+)</title>"],
        "detail_poster": r'<video[^>]+poster="([^"]+)"',
        "detail_dur": [(r"knownDuration:(\d+)", "sec")],
        "detail_tags": None,
        "cats": [
            ("asian", "亚洲"), ("amateur", "业余"), ("anal", "肛交"),
            ("ass", "臀部"), ("babes", "美女"), ("bbw", "丰满"),
            ("bdsm", "SM"), ("big-tits", "大胸"), ("blonde", "金发"),
            ("blowjob", "口交"), ("brunette", "棕发"), ("bukkake", "颜射"),
            ("college", "大学"), ("couple", "情侣"), ("creampie", "内射"),
            ("cumshot", "射精"), ("deep-throat", "深喉"), ("erotic", "情色"),
            ("facial", "颜面"), ("fetish", "恋物"), ("gangbang", "群交"),
            ("group", "群体"), ("hairy", "毛发"), ("handjob", "手淫"),
            ("hardcore", "硬核"), ("homemade", "自拍"),
            ("interracial", "跨种族"), ("lesbian", "女同"),
            ("lingerie", "内衣"), ("massage", "按摩"),
            ("masturbation", "自慰"), ("mature", "成熟"), ("milf", "熟女"),
            ("nurse", "护士"), ("office", "办公室"), ("orgy", "群交派对"),
            ("outdoor", "户外"), ("pov", "主观视角"), ("public", "公共"),
            ("pussy", "阴部"), ("schoolgirl", "女学生"),
            ("secretary", "秘书"), ("shemale", "人妖"), ("solo", "独自"),
            ("stockings", "丝袜"), ("teacher", "老师"), ("teen", "青少年"),
            ("threesome", "三人"), ("toys", "玩具"), ("uniform", "制服"),
            ("voyeur", "偷窥"), ("webcam", "摄像头"), ("wife", "人妻"),
            ("tits", "胸部"), ("titfuck", "乳交"), ("squirting", "潮吹"),
            ("romantic", "浪漫"), ("pornstar", "女优"),
            ("russian", "俄罗斯"), ("redhead", "红发"),
            ("small-tits", "小胸"), ("tattoo", "纹身"),
            ("softcore", "软色情"), ("double-penetration", "双插"),
            ("ebony", "黑人"), ("big-cock", "大屌"), ("69", "69"),
            ("swallow", "吞精"), ("strapon", "假阳具"),
        ],
    },

}

SITE_ORDER = ["6chua", "nat", "hjavp", "jjj", "mega"]
_PAGE_SIZE_HINT = 20

class Spider(Spider):
    def __init__(self):
        self._sess = None
        self._last = 0.0

    def getName(self):
        return "亚洲合集"

    def init(self, extend=""):
        return

    # ---------- 网络 ----------
    def _fetch(self, url, host, referer=True):
        now = time.time()
        if now - self._last < 0.5:
            time.sleep(0.5 - (now - self._last))
        self._last = time.time()
        headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
        # 有的站必须带 Referer（如 6chua，不带就 403），有的站带了 Referer
        # 反而会断流/403（如 newasiantube），所以按站配置（no_referer）。
        if referer:
            headers["Referer"] = host + "/"
        # 站方偶尔会抽风（连续请求时 429/5xx），失败一次后等 2 秒重试一次
        last_err = None
        for _ in range(2):
            try:
                if requests is not None:
                    if self._sess is None:
                        self._sess = requests.Session()
                    r = self._sess.get(url, headers=headers, timeout=25)
                    r.raise_for_status()
                    return r.text
                import urllib.request
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=25) as resp:
                    return resp.read().decode("utf-8", "ignore")
            except Exception as e:
                last_err = e
                time.sleep(2)
        raise last_err

    # ---------- 解析 ----------
    def _abs_pic(self, pic, host):
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return host + pic
        return pic

    def _parse_cards(self, cfg, html):
        out = []
        seen = set()
        for block in re.findall(cfg["block"], html, re.S):
            m = re.search(cfg["href"], block)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            im = re.search(cfg["img"], block)
            pic = self._abs_pic(im.group(1), cfg["host"]) if im else ""
            tm = re.search(cfg["title"], block)
            title = tm.group(1).strip() if tm else ""
            if not title and cfg["title_alt"]:
                am = re.search(cfg["title_alt"], block)
                title = am.group(1).strip() if am else ""
            title = unescape(title)
            if not title:
                continue
            dm = re.search(cfg["dur"], block)
            dur = dm.group(1) if dm else ""
            out.append({"vod_id": href, "vod_name": title,
                        "vod_pic": pic, "vod_remarks": dur})
        return out

    def _fetch_list(self, cfg, url_zh, url_en):
        """列表页优先走站方的中文版（/zh/，标题是机翻中文），
        中文版打不开（6chua 的 /zh/ 有时会 403）再退回英文版。
        两版都打不开（比如网络抽风）时返回空串，调用方按空列表处理，
        不让一次网络抖动把整个分类页拖垮。"""
        try:
            return self._fetch(url_zh, cfg["host"],
                               referer=not cfg.get("no_referer"))
        except Exception:
            try:
                return self._fetch(url_en, cfg["host"],
                                   referer=not cfg.get("no_referer"))
            except Exception:
                return ""

    def _tag_vod(self, key, vod):
        # 把列表里已翻译好的中文标题编进 vod_id，这样详情页也能
        # 显示中文标题（视频页本身没有中文版，标题只能是英文）。
        # quote(safe="") 后只剩字母数字和 %_.-~，不会和分隔符冲突。
        vod = dict(vod)
        vod["vod_id"] = "%s|%s|%s" % (key, quote(vod["vod_name"], safe=""),
                                      vod["vod_id"])
        return vod

    def _split_vod_id(self, vid):
        # vod_id 形如 6chua|<中文标题url编码>|/c/?g=...（新版）
        # 或 6chua|/c/?g=...（旧版，无标题）
        parts = vid.split("|", 2)
        if len(parts) == 3 and parts[0] in SITES:
            from urllib.parse import unquote
            return parts[0], parts[2], unquote(parts[1])
        if len(parts) == 2 and parts[0] in SITES:
            return parts[0], parts[1], ""
        return "6chua", vid, ""

    def _page_url(self, cfg, tid, pg, sort="", zh=True):
        pg = int(pg) if str(pg).isdigit() else 1
        host = cfg["host"]
        prefix = host + ("/zh" if zh else "")
        if tid in ("", "latest"):
            return prefix + "/" if pg == 1 else "%s/?page=%d" % (prefix, pg)
        base = "%s/%s/" % (prefix, tid.strip("/"))
        if sort:
            base += sort.strip("/") + "/"
        return base if pg == 1 else "%s?page=%d" % (base, pg)

    def _search_url(self, cfg, key, pg, zh=True):
        pg = int(pg) if str(pg).isdigit() else 1
        host = cfg["host"]
        prefix = host + ("/zh" if zh else "")
        return "%s/?%s=%s&page=%d" % (prefix, cfg["search_param"],
                                      quote(key), pg)

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter):
        classes = []
        filters = {}
        for key in SITE_ORDER:
            cfg = SITES[key]
            for slug, name in cfg["cats"]:
                tid = "%s:%s" % (key, slug)
                classes.append({"type_id": tid,
                                "type_name": "%s·%s" % (cfg["name"], name)})
                if cfg["sorts"]:
                    filters[tid] = [{"key": "排序", "name": "排序",
                                     "value": [{"n": n, "v": v}
                                               for n, v in cfg["sorts"]]}]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 各站首页各取 6 条拼成推荐（中文版标题）；
        # megapsite 首页是分类索引、没有视频卡片，改取 /asian/。
        # 七个站并行抓，省时间（原来一个一个串行抓，慢）。
        def _one(key):
            cfg = SITES[key]
            try:
                if cfg.get("home_video"):
                    hv = cfg["home_video"]
                    html = self._fetch_list(
                        cfg, cfg["host"] + "/zh" + hv,
                        cfg["host"] + hv)
                else:
                    html = self._fetch_list(cfg, cfg["host"] + "/zh/",
                                            cfg["host"] + "/")
                return [self._tag_vod(key, v)
                        for v in self._parse_cards(cfg, html)[:6]]
            except Exception:
                return []

        out = []
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=7) as ex:
                results = list(ex.map(_one, SITE_ORDER))
            for lst in results:
                out.extend(lst)
        except Exception:
            for key in SITE_ORDER:
                out.extend(_one(key))
        return {"list": out}

    def categoryContent(self, tid, pg, filter, extend):
        # tid 形如 6chua:asian / nat:asian / hjavp:asian
        if ":" in tid:
            key, slug = tid.split(":", 1)
        else:
            key, slug = "6chua", tid
        cfg = SITES.get(key) or SITES["6chua"]
        sort = ""
        if isinstance(extend, dict):
            sort = extend.get("排序", "") or ""
        pg = int(pg) if str(pg).isdigit() else 1
        # 首页/分类的 ?page= 是假的：第 2 页起内容和第 1 页完全相同
        if pg > 1:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": 90, "total": 999999}
        html = self._fetch_list(cfg,
                                self._page_url(cfg, slug, pg, sort, zh=True),
                                self._page_url(cfg, slug, pg, sort, zh=False))
        lst = [self._tag_vod(key, v) for v in self._parse_cards(cfg, html)]
        return {"list": lst, "page": pg, "pagecount": 1,
                "limit": 90, "total": 999999}

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        key, href, zh_title = self._split_vod_id(vid)
        cfg = SITES[key]
        vod = {"vod_id": vid, "vod_name": "", "vod_pic": "",
               "vod_remarks": "", "vod_content": "",
               "vod_play_from": cfg["name"], "vod_play_url": ""}
        try:
            url = href if href.startswith("http") else cfg["host"] + href
            html = self._fetch(url, cfg["host"], referer=not cfg.get("no_referer"))
            title = ""
            for pat in cfg["detail_title"]:
                tm = re.search(pat, html)
                if tm and tm.group(1).strip():
                    title = tm.group(1).strip()
                    break
            pm = re.search(cfg["detail_poster"], html)
            pic = self._abs_pic(pm.group(1), cfg["host"]) if pm else ""
            dur = ""
            for pat, kind in cfg["detail_dur"]:
                dm = re.search(pat, html, re.S)
                if dm:
                    if kind == "sec":
                        sec = int(dm.group(1))
                        dur = "%d:%02d" % (sec // 60, sec % 60)
                    else:
                        dur = dm.group(1)
                    break
            tags = []
            if cfg["detail_tags"]:
                tg = re.search(cfg["detail_tags"], html, re.S)
                if tg:
                    tags = [t.strip() for t in
                            re.findall(r"<a[^>]*>([^<]+)</a>", tg.group(1))
                            if t.strip()]
            # 标题优先用列表里的中文翻译（视频页本身没有中文版）；
            # 旧版 vod_id 里没带标题时才用视频页的英文标题。
            vod["vod_name"] = zh_title or unescape(title)
            vod["vod_pic"] = pic
            vod["vod_remarks"] = dur
            vod["vod_content"] = " / ".join(tags)
            vod["vod_play_url"] = "正片$%s" % vid
        except Exception:
            if not vod["vod_play_url"]:
                vod["vod_play_url"] = "正片$%s" % vid
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        # 五个站一起搜，合并结果（每站取 20 条，总上限 100）
        pg = int(pg) if str(pg).isdigit() else 1
        out = []
        more = False
        for skey in SITE_ORDER:
            cfg = SITES[skey]
            try:
                html = self._fetch_list(cfg,
                                        self._search_url(cfg, key, pg, zh=True),
                                        self._search_url(cfg, key, pg, zh=False))
                lst = self._parse_cards(cfg, html)
                if len(lst) >= _PAGE_SIZE_HINT:
                    more = True
                for v in lst[:20]:
                    out.append(self._tag_vod(skey, v))
            except Exception:
                continue
        return {"list": out[:100], "page": pg,
                "pagecount": pg + 1 if more else pg,
                "limit": 90, "total": 999999}

    def playerContent(self, flag, id, vipFlags=None):
        key, href, _zh_title = self._split_vod_id(id)
        cfg = SITES[key]
        try:
            url = href if href.startswith("http") else cfg["host"] + href
            html = self._fetch(url, cfg["host"], referer=not cfg.get("no_referer"))
            m = re.search(r'<source[^>]+src="(https?://[^"]+\.m3u8[^"]*)"', html)
            if not m:
                m = re.search(r"(https?://[^\"' ]+\.m3u8[^\"' ]*)", html)
            if m:
                return {"parse": 0, "url": m.group(1),
                        "header": {"User-Agent": UA,
                                   "Referer": cfg["host"] + "/"}}
        except Exception:
            pass
        # 兜底：让客户端打开视频页解析
        page = href if href.startswith("http") else cfg["host"] + href
        return {"parse": 1, "url": page, "header": {"User-Agent": UA}}

    def localProxy(self, param):
        return [200, "video/2", None, ""]


if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    hc = sp.homeContent(None)
    print("classes:", len(hc["class"]))
    hv = sp.homeVideoContent()
    print("homeVideo:", len(hv["list"]),
          "sites:", sorted({v["vod_id"].split("|")[0] for v in hv["list"]}))
    for tid in ("6chua:asian", "nat:asian", "hjavp:asian", "jjj:asian",
                "mega:asian"):
        cc = sp.categoryContent(tid, "1", None, None)
        print(tid, "->", len(cc["list"]), "pagecount:", cc["pagecount"],
              "first:", cc["list"][0]["vod_name"][:40] if cc["list"] else None)
    cn = sp.categoryContent("nat:asian", "1", None, {"排序": "newest-videos"})
    print("nat newest:", len(cn["list"]))
    sc = sp.searchContent("Japanese", False, "1")
    print("search merged:", len(sc["list"]),
          "sites:", sorted({v["vod_id"].split("|")[0] for v in sc["list"]}))
    for tid in ("6chua:asian", "nat:asian", "hjavp:asian", "mega:asian"):
        cc = sp.categoryContent(tid, "1", None, None)
        if not cc["list"]:
            print(tid, "-> EMPTY, skip")
            continue
        d = sp.detailContent([cc["list"][0]["vod_id"]])["list"][0]
        p = sp.playerContent("", cc["list"][0]["vod_id"])
        print(tid, "| detail:", d["vod_name"][:40], "| dur:", d["vod_remarks"],
              "| tags:", d["vod_content"][:40],
              "| player:", p["parse"], "| url:", p["url"][:70])
