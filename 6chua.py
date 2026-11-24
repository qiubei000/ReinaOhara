# -*- coding: utf-8 -*-
import re
import time
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

HOST = "https://www.6chua.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 分类：slug -> 中文名（站方共 139 个分类，这里放常用的）
CATS = [
    ("latest", "最新"),
    ("asian", "亚洲"),
    ("amateur", "业余"),
    ("anal", "肛交"),
    ("ass", "臀部"),
    ("babes", "美女"),
    ("bbw", "丰满"),
    ("bdsm", "SM"),
    ("big-tits", "大胸"),
    ("blonde", "金发"),
    ("blowjob", "口交"),
    ("brunette", "棕发"),
    ("bukkake", "颜射"),
    ("celebrities", "名人"),
    ("college", "大学"),
    ("couple", "情侣"),
    ("creampie", "内射"),
    ("cumshot", "射精"),
    ("deep-throat", "深喉"),
    ("erotic", "情色"),
    ("facial", "颜面"),
    ("fetish", "恋物"),
    ("gangbang", "群交"),
    ("glamour", "写真"),
    ("group", "群体"),
    ("hairy", "毛发"),
    ("handjob", "手淫"),
    ("hardcore", "硬核"),
    ("homemade", "自拍"),
    ("interracial", "跨种族"),
    ("lesbian", "女同"),
    ("lingerie", "内衣"),
    ("massage", "按摩"),
    ("masturbation", "自慰"),
    ("mature", "成熟"),
    ("milf", "熟女"),
    ("nurse", "护士"),
    ("office", "办公室"),
    ("orgy", "群交派对"),
    ("outdoor", "户外"),
    ("pov", "主观视角"),
    ("public", "公共"),
    ("pussy", "阴部"),
    ("schoolgirl", "女学生"),
    ("secretary", "秘书"),
    ("shemale", "人妖"),
    ("solo", "独自"),
    ("stockings", "丝袜"),
    ("teacher", "老师"),
    ("teen", "青少年"),
    ("threesome", "三人"),
    ("toys", "玩具"),
    ("uniform", "制服"),
    ("voyeur", "偷窥"),
    ("webcam", "摄像头"),
    ("wife", "人妻"),
]

_PAGE_SIZE_HINT = 20  # 一页卡片很多（约 94 条），满页即认为还有下一页


class Spider(Spider):
    def __init__(self):
        self._sess = None
        self._last = 0.0

    def init(self, extend=""):
        return

    # ---------- 网络 ----------
    def _fetch(self, url, referer=None):
        now = time.time()
        if now - self._last < 0.5:
            time.sleep(0.5 - (now - self._last))
        self._last = time.time()
        headers = {"User-Agent": UA, "Referer": referer or (HOST + "/"),
                   "Accept-Language": "en-US,en;q=0.9"}
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

    # ---------- 解析 ----------
    def _parse_cards(self, html):
        """解析一页的视频卡片 -> vod 列表。

        两种卡片格式：
        - 首页/分类：<a href='/c/?g=...&t=<图id>&i=<视频id>&c=<分类>'>
          <img id="<图id>" src="//pic.6chua.com/a/cache1698/...jpg">
        - 搜索：<a href='/?video=<vid>&cat=<分类>'>
          <img src='//pic.6chua.com/t2/<n>.jpg' >
        """
        out = []
        seen = set()
        # 每张卡片以 <div class=ugu> 开头
        for block in re.findall(r'<div class=ugu>(.*?)(?=<div class=ugu>|$)',
                                html, re.S):
            m = re.search(r"<a href='(/c/\?[^']+|/\?video=[^']+)'", block)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            im = re.search(r'''<img[^>]+src=["']([^"']+)["']''', block)
            pic = im.group(1) if im else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = HOST + pic
            tm = re.search(r"<div class=shv>([^<]+)</div>", block)
            title = tm.group(1).strip() if tm else ""
            if not title:
                continue
            dm = re.search(r"<i class='nwj bps'></i><div>(\d+:\d+)</div>", block)
            dur = dm.group(1) if dm else ""
            out.append({"vod_id": href, "vod_name": title,
                        "vod_pic": pic, "vod_remarks": dur})
        return out

    def _page_url(self, tid, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        if pg < 1:
            pg = 1
        if tid in ("", "latest"):
            return "%s/?page=%d" % (HOST, pg)
        return "%s/%s/?page=%d" % (HOST, tid.strip("/"), pg)

    def _page_result(self, html, pg, paginates=True):
        lst = self._parse_cards(html)
        pg = int(pg) if str(pg).isdigit() else 1
        if not paginates:
            # 首页/分类的 ?page= 参数是假的：第 2 页起内容和第 1 页完全相同
            if pg > 1:
                lst = []
            pagecount = 1
        else:
            pagecount = pg + 1 if len(lst) >= _PAGE_SIZE_HINT else pg
        return {"list": lst, "page": pg, "pagecount": pagecount,
                "limit": 90, "total": 999999}

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter):
        classes = [{"type_id": slug, "type_name": name} for slug, name in CATS]
        return {"class": classes}

    def homeVideoContent(self):
        try:
            html = self._fetch(HOST + "/")
            return {"list": self._parse_cards(html)[:24]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        html = self._fetch(self._page_url(tid, pg))
        return self._page_result(html, pg, paginates=False)

    def detailContent(self, ids):
        href = ids[0] if ids else ""
        vod = {"vod_id": href, "vod_name": "", "vod_pic": "",
               "vod_remarks": "", "vod_play_from": "6chua",
               "vod_play_url": ""}
        try:
            url = href if href.startswith("http") else HOST + href
            html = self._fetch(url)
            tm = re.search(r"<title>([^<]+)</title>", html)
            title = tm.group(1).strip() if tm else ""
            pm = re.search(r'<video[^>]+poster="([^"]+)"', html)
            pic = pm.group(1) if pm else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = HOST + pic
            # 时长：视频自己的时长在 <div class=ptd>...<span>118:49</span>
            # （页面里还有广告尺寸、cookie 哈希里的数字，不能用 \d+:\d+ 全扫）
            dm = re.search(r"<div class=ptd>.*?<span>(\d+:\d+)</span>", html, re.S)
            dur = dm.group(1) if dm else ""
            vod["vod_name"] = title
            vod["vod_pic"] = pic
            vod["vod_remarks"] = dur
            vod["vod_play_url"] = "正片$%s" % href
        except Exception:
            if not vod["vod_play_url"]:
                vod["vod_play_url"] = "正片$%s" % href
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = "%s/?search=%s&page=%d" % (HOST, quote(key), pg)
        html = self._fetch(url)
        return self._page_result(html, pg)

    def playerContent(self, flag, id, vipFlags=None):
        # id 是 /c/ 链接（或直接是 /?video= 链接），跟随 302 到视频页
        try:
            url = id if id.startswith("http") else HOST + id
            html = self._fetch(url)
            m = re.search(r'<source[^>]+src="(https?://[^"]+\.m3u8[^"]*)"', html)
            if not m:
                m = re.search(r"(https?://[^\"' ]+\.m3u8[^\"' ]*)", html)
            if m:
                return {"parse": 0, "url": m.group(1),
                        "header": {"User-Agent": UA,
                                   "Referer": HOST + "/"}}
        except Exception:
            pass
        # 兜底：让客户端打开视频页解析
        page = id if id.startswith("http") else HOST + id
        return {"parse": 1, "url": page, "header": {"User-Agent": UA}}

    def localProxy(self, param):
        return [200, "video/2", None, ""]


if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    hc = sp.homeContent(None)
    print("classes:", len(hc["class"]))
    cc = sp.categoryContent("asian", "1", None, None)
    print("asian p1:", len(cc["list"]), "first:", cc["list"][0])
    sc = sp.searchContent("Japanese", False, "1")
    print("search:", len(sc["list"]))
    dc = sp.detailContent([cc["list"][0]["vod_id"]])
    print("detail:", dc["list"][0]["vod_name"][:60], "|",
          dc["list"][0]["vod_pic"][:60], "|", dc["list"][0]["vod_remarks"])
    pc = sp.playerContent("", cc["list"][0]["vod_id"])
    print("player parse:", pc["parse"], "| url:", pc["url"][:110])
