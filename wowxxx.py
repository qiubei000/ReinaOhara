# -*- coding: utf-8 -*-
"""
WOWXXX.TO (ex WOW.XXX) - 免费高级片聚合站
Brazzers / Blacked / Team Skeet / MYLF / Adult Time / Tushy / Vixen 等
全片直链 mp4，多画质 (480p/720p/1080p 以实际为准)，无需登录，无票据
分类 356 个，片商众多；爬虫取常用分类 + 大片商
"""
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = 'https://www.wowxxx.to'
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')
    TIMEOUT = 20

    # tid -> (name, path)；path 为列表页相对路径，分页在其后加 N/
    CLASSES = [
        ('latest', '最新更新', '/latest-updates/'),
        ('popular', '最受欢迎', '/most-popular/'),
        ('week', '本周热门', '/most-popular/week/'),
        ('toprated', '好评最高', '/top-rated/'),
        ('cat:amateur', 'Amateur', '/categories/amateur/'),
        ('cat:anal', 'Anal', '/categories/anal/'),
        ('cat:asian', 'Asian', '/categories/asian/'),
        ('cat:bbw', 'BBW', '/categories/bbw/'),
        ('cat:bdsm', 'BDSM', '/categories/bdsm/'),
        ('cat:big-tits', 'Big Tits', '/categories/big-tits/'),
        ('cat:blonde', 'Blonde', '/categories/blonde/'),
        ('cat:brunette', 'Brunette', '/categories/brunette/'),
        ('cat:creampie', 'Creampie', '/categories/creampie/'),
        ('cat:ebony', 'Ebony', '/categories/ebony/'),
        ('cat:hardcore', 'Hardcore', '/categories/hardcore/'),
        ('cat:interracial', 'Interracial', '/categories/interracial/'),
        ('cat:lesbian', 'Lesbian', '/categories/lesbian/'),
        ('cat:mature', 'Mature', '/categories/mature/'),
        ('cat:milf', 'MILF', '/categories/milf/'),
        ('cat:pov', 'POV', '/categories/pov/'),
        ('cat:public', 'Public', '/categories/public/'),
        ('cat:teen', 'Teen', '/categories/teen/'),
        ('cat:threesome', 'Threesome', '/categories/threesome/'),
        # 片商页 /sites/<slug>/ 在站上是空列表，改走站内搜索（站方自己也用
        # /search/<片商>/ 链片商视频），分页同为 /search/<词>/N/
        ('site:brazzers', 'Brazzers', '/search/Brazzers/'),
        ('site:blacked', 'Blacked', '/search/Blacked/'),
        ('site:teamskeet', 'Team Skeet', '/search/Team%20Skeet/'),
        ('site:mylf', 'MYLF', '/search/MYLF/'),
        ('site:adult-time', 'Adult Time', '/search/Adult%20Time/'),
        ('site:tushy', 'Tushy', '/search/Tushy/'),
        ('site:vixen', 'Vixen', '/search/Vixen/'),
        ('site:hardx', 'Hard X', '/search/Hard%20X/'),
        ('site:pure-taboo', 'Pure Taboo', '/search/Pure%20Taboo/'),
        ('site:new-sensations', 'New Sensations', '/search/New%20Sensations/'),
    ]

    def getName(self):
        return 'WOWXXX'

    def init(self, extend):
        pass

    # ── HTTP ──────────────────────────────────────────────────
    def _http(self, url, timeout=None):
        h = {'User-Agent': self.UA, 'Referer': self.HOST + '/',
              'Accept-Language': 'en-US,en;q=0.9'}
        best = b''
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers=h, method='GET')
                with urllib.request.urlopen(
                        req, timeout=timeout or self.TIMEOUT) as resp:
                    return resp.read()
            except Exception as e:
                partial = getattr(e, 'partial', None)
                if partial and len(partial) > len(best):
                    best = partial
                time.sleep(0.5)
        return best

    @staticmethod
    def _clean(s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', '', s)
        s = (s.replace('&amp;', '&').replace('&quot;', '"')
              .replace('&#39;', "'").replace('&nbsp;', ' '))
        return re.sub(r'\s+', ' ', s).strip()

    # ── 列表解析 ──────────────────────────────────────────────
    _CARD = re.compile(
        r'<a href="https?://www\.wowxxx\.to/videos/([^/"]+)/"[^>]*'
        r'title="([^"]*)"[^>]*class="thumb_img"[^>]*>'
        r'.*?(?:data-src="([^"]+)"|src="(https?://[^"]+)")'
        r'.*?<span class="duration">\s*([^<]*?)\s*</span>',
        re.S)

    def _parse_list(self, html):
        out, seen = [], set()
        for m in self._CARD.finditer(html):
            slug, title, cover, cover2, dur = m.groups()
            if slug in seen:
                continue
            seen.add(slug)
            title = self._clean(title)
            if not title:
                continue
            cover = cover or cover2 or ''
            dur = self._clean(dur).replace('Full Video', '').strip()
            out.append({'vod_id': slug, 'vod_name': title,
                        'vod_pic': cover, 'vod_remarks': dur})
        # 列表页本身没有画质信息，最高画质只在详情页的 <source> 里；
        # 并行取每条的详情页：拿最高画质标在封面备注最前面，如 2160p · 27:16，
        # 同时拿详情页 og:title 当片名（带 [片商] - 前缀，和站点一致）
        # 取不到就保留列表原标题/只留时长，不拖慢列表
        if out:
            try:
                with ThreadPoolExecutor(max_workers=8) as ex:
                    metas = list(ex.map(self._detail_meta,
                                        [o['vod_id'] for o in out]))
            except Exception:
                metas = [('', '')] * len(out)
            for o, (t, q) in zip(out, metas):
                if t:
                    o['vod_name'] = t
                if q:
                    o['vod_remarks'] = (q + ' · ' + o['vod_remarks']
                                        if o['vod_remarks'] else q)
        return out

    def _detail_meta(self, slug):
        # 返回详情页的 (片名, 最高画质)；片名取 og:title，保留 [片商] - 前缀
        # 如 [Pure Taboo] - Anne's Naughty Escape: Act 2；取不到返回 ('', '')
        try:
            html = self._http(self.HOST + '/videos/%s/' % slug,
                              timeout=8).decode('utf-8', 'ignore')
            title = ''
            m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
            if m:
                title = self._clean(m.group(1))
                title = re.sub(r'\s*\|\s*Free at WOWXXX.*$', '', title)
            sources = self._sources(html)
            return title, (sources[0][0] if sources else '')
        except Exception:
            return '', ''

    def _max_quality(self, slug):
        return self._detail_meta(slug)[1]

    def _list_url(self, path, pg):
        if pg and int(pg) > 1:
            return self.HOST + path + str(int(pg)) + '/'
        return self.HOST + path

    def homeContent(self, filter):
        cats = [{'type_id': t, 'type_name': n} for t, n, _ in self.CLASSES]
        return {'class': cats}

    def homeVideoContent(self):
        html = self._http(self.HOST + '/latest-updates/').decode(
            'utf-8', 'ignore')
        return {'list': self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        path = None
        for t, _, p in self.CLASSES:
            if t == tid:
                path = p
                break
        if path is None:
            return {'list': []}
        html = self._http(self._list_url(path, pg)).decode('utf-8', 'ignore')
        return {'list': self._parse_list(html), 'page': pg or 1,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg):
        q = urllib.parse.quote(key.strip())
        base = '/search/%s/' % q
        html = self._http(self._list_url(base, pg)).decode('utf-8', 'ignore')
        return {'list': self._parse_list(html), 'page': pg or 1,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ── 详情 / 播放 ───────────────────────────────────────────
    _SOURCE = re.compile(
        r"<source\s+src='([^']+)'[^>]*label=\"([^\"]+)\""
        r"(?:\s+selected=\"true\")?", re.S)

    def detailContent(self, ids):
        raw = str(ids[0]) if isinstance(ids, (list, tuple)) else str(ids or '')
        slug = raw.split('/')[-1].strip()
        if not slug:
            return {'list': []}
        html = self._http(self.HOST + '/videos/%s/' % slug).decode(
            'utf-8', 'ignore')
        if not html:
            return {'list': []}
        title = ''
        m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if m:
            title = self._clean(m.group(1))
            title = re.sub(r'\s*\|\s*Free at WOWXXX.*$', '', title)
            # 保留 [片商] - 前缀，和站点详情页标题一致
        if not title:
            m = re.search(r'<title>([^<]*)</title>', html)
            title = self._clean(m.group(1)) if m else slug
        cover = ''
        m = re.search(r'<meta property="og:image" content="([^"]*)"', html)
        if m:
            cover = m.group(1)
        actor = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            parts = [self._clean(p) for p in
                     self._clean(m.group(1)).split(' - ')]
            # 第一项是片商，最后一项是标题/日期，中间是演员
            if len(parts) > 2:
                actor = ', '.join(parts[1:-1])
        sources = self._sources(html)
        eps = []
        for label, _url in sources:
            eps.append('%s$play@@%s@@%s' % (label, slug, label))
        remarks = ''
        if sources:
            remarks = ' · '.join(lbl for lbl, _ in sources)
        return {'list': [{'vod_id': slug, 'vod_name': title,
                          'vod_pic': cover, 'vod_actor': actor,
                          'vod_remarks': remarks,
                          'vod_play_from': 'WOWXXX',
                          'vod_play_url': '#'.join(eps)}]}

    def _sources(self, html):
        found = []
        for url, label in self._SOURCE.findall(html):
            label = label.strip()
            if not url.startswith('http'):
                continue
            found.append((label, url))
        # 按画质数字从高到低
        def _res(lbl):
            mm = re.search(r'(\d+)', lbl)
            return int(mm.group(1)) if mm else 0
        found.sort(key=lambda x: _res(x[0]), reverse=True)
        out, seen = [], set()
        for lbl, url in found:
            if lbl in seen:
                continue
            seen.add(lbl)
            out.append((lbl, url))
        return out

    def playerContent(self, flag, id, vipFlags):
        m = re.match(r'play@@([^@]+)@@(.+)', str(id or ''))
        if not m:
            return {'parse': 0, 'url': ''}
        slug, label = m.group(1), m.group(2)
        html = self._http(self.HOST + '/videos/%s/' % slug).decode(
            'utf-8', 'ignore')
        for lbl, url in self._sources(html):
            if lbl == label:
                return {'parse': 0, 'url': url,
                        'header': {'User-Agent': self.UA,
                                   'Referer': self.HOST + '/videos/%s/' % slug}}
        return {'parse': 0, 'url': ''}

    def isVideoFormat(self, url):
        return url.startswith('http') and ('.mp4' in url or '.m3u8' in url)

    def manualVideoCheck(self):
        return False
