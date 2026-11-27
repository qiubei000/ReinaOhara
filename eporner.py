# -*- coding: utf-8 -*-
"""
EPORNER (eporner.com) - 免费高清视频站，无需登录，无 Cloudflare
500 多万部，720p/1080p/4K 直链 mp4（/dload/ 跳转到 CDN，有效期现取现用）
列表页：首页 65 条（39 + 26 hdy），分类页约 59 条/页，分页 /N/
详情页 dload 链接含全部画质（240/360/480/720/1080/2160，以实际为准），
播放入口直接给 dload 链接 + Referer，播放器跟随 302 到 CDN 直链
搜索是 POST /search/（字段名 search），301 跳到 /tag/<词>-<hash>/，翻页 /N/
分类 87 个（/cats/ 动态取，带封面），首页 8 个类：推荐/最佳/评分/4K/1080p/60FPS/VR/类别
类别用两级浏览：点开类别列出全部 87 个分类，点分类进虚拟详情，第1-5页选集点播最高画质
"""
import re
import time
import urllib.parse
import urllib.request

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = 'https://www.eporner.com'
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')
    TIMEOUT = 20

    SORTS = [
        ('home', '首页推荐', '/'),
        ('best', '最佳视频', '/best-videos/'),
        ('top', '最高评分', '/top-rated/'),
        ('4k', '4K', '/cat/4k-porn/'),
        ('hd1080', '1080p', '/cat/hd-1080p/'),
        ('fps60', '60FPS', '/cat/60fps/'),
        ('vr', 'VR', '/cat/vr-porn/'),
        ('cats', '类别', 'group:cats'),
    ]
    GROUP_PAGES = 5  # 类别虚拟详情里展示前 5 页影片
    PAGE_SIZE = 24   # 类别分组列表每页条数
    _cats_cache = None
    _search_url = None

    def getName(self):
        return 'EPORNER'

    def init(self, extend):
        pass

    # ── HTTP ──────────────────────────────────────────────────
    def _http(self, url, data=None, timeout=None):
        """返回 (body_bytes, final_url)；失败返回 (b'', url)"""
        h = {'User-Agent': self.UA, 'Referer': self.HOST + '/',
               'Accept-Language': 'en-US,en;q=0.9'}
        body = b''
        final = url
        if data is not None:
            body_data = urllib.parse.urlencode(data).encode('utf-8')
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body_data = None
        for _ in range(3):
            try:
                req = urllib.request.Request(url, data=body_data,
                                             headers=h, method='POST' if body_data else 'GET')
                with urllib.request.urlopen(
                        req, timeout=timeout or self.TIMEOUT) as resp:
                    return resp.read(), resp.geturl()
            except Exception as e:
                partial = getattr(e, 'partial', None)
                if partial and len(partial) > len(body):
                    body = partial
                final = getattr(e, 'url', url) or url
                time.sleep(0.5)
        return body, final

    @staticmethod
    def _clean(s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', '', s)
        s = (s.replace('&amp;', '&').replace('&quot;', '"')
              .replace('&#39;', "'").replace('&nbsp;', ' '))
        return re.sub(r'\s+', ' ', s).strip()

    @staticmethod
    def _fmt_dur(sec):
        try:
            sec = int(sec)
        except Exception:
            return ''
        h, m = divmod(sec, 3600)
        m, s = divmod(m, 60)
        return '%d:%02d:%02d' % (h, m, s) if h else '%d:%02d' % (m, s)

    # ── 列表解析 ──────────────────────────────────────────────
    _CARD = re.compile(
        r'<div class="mb(?: hdy)?" data-id="(\d+)".*?'
        r'<a href="/video-([^/"]+)/[^"]*">.*?'
        r'<img[^>]+?(?:data-src="([^"]+)"|src="([^"]+)")'
        r'[^>]*alt="([^"]*)".*?'
        r'<div class="mvhdico"[^>]*><span>([^<]*)</span></div>.*?'
        r'<span class="mbtim"[^>]*>([^<]*)</span>',
        re.S)

    def _parse_list(self, html):
        out, seen = [], set()
        for m in self._CARD.finditer(html):
            _vid, code, cover, cover2, title, qual, dur = m.groups()
            if code in seen:
                continue
            seen.add(code)
            title = self._clean(title)
            if not title:
                continue
            remarks = ' · '.join(x for x in
                                 [self._clean(qual), self._clean(dur)] if x)
            out.append({'vod_id': 'video:' + code, 'vod_name': title,
                        'vod_pic': cover or cover2 or '',
                        'vod_remarks': remarks})
        return out

    # ── 首页 ──────────────────────────────────────────────────
    def homeContent(self, filter):
        return {'class': [{'type_id': t, 'type_name': n}
                          for t, n, _p in self.SORTS]}

    def homeVideoContent(self):
        html, _u = self._http(self.HOST + '/')
        return {'list': self._parse_list(html.decode('utf-8', 'ignore'))}

    def _list_url(self, path, pg):
        if pg <= 1:
            return self.HOST + path
        return self.HOST + path.rstrip('/') + '/%d/' % pg

    # ── 分类 ──────────────────────────────────────────────────
    def _categories(self):
        if self._cats_cache is not None:
            return self._cats_cache
        html, _u = self._http(self.HOST + '/cats/')
        html = html.decode('utf-8', 'ignore')
        # 封面：导航 Popular 区的 listcatbig 条目带 catimg
        pics = {}
        for m in re.finditer(
                r'<a[^>]*href="/cat/([^/"]+)/"[^>]*>'
                r'<img[^>]+?data-src="([^"]+)"', html):
            pics.setdefault(m.group(1), m.group(2))
        # 全量 87 个分类：整页所有带 title="X Porn" 的 /cat/ 链接，去重
        cats, seen = [], set()
        for m in re.finditer(
                r'href="/cat/([^/"]+)/" title="([^"]+?)(?: Porn)?"', html):
            slug, name = m.groups()
            if slug in seen or slug in ('all',):
                continue
            seen.add(slug)
            cats.append({'slug': slug, 'name': self._clean(name),
                         'pic': pics.get(slug, '')})
        self._cats_cache = cats
        return cats

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        # 类别大组：两级浏览，列出全部 87 个分类（带封面），本地分页
        if tid == 'cats':
            cats = self._categories()
            start = (pg - 1) * self.PAGE_SIZE
            page = cats[start:start + self.PAGE_SIZE]
            out = [{'vod_id': 'catgroup:' + c['slug'],
                    'vod_name': c['name'], 'vod_pic': c['pic'],
                    'vod_remarks': '分类'} for c in page]
            return {'list': out, 'page': pg,
                    'pagecount': max(1, -(-len(cats) // self.PAGE_SIZE)),
                    'limit': 90, 'total': len(cats)}
        for t, _n, path in self.SORTS:
            if t == tid and path != 'group:cats':
                html, _u = self._http(self._list_url(path, pg))
                return {'list': self._parse_list(html.decode('utf-8', 'ignore')),
                        'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 90, 'total': 0}

    # ── 详情 ──────────────────────────────────────────────────
    _DLOAD = re.compile(
        r'dload/([A-Za-z0-9]+)/(\d+)/(\d+)-(\d+)p\.mp4')

    def _dloads(self, html):
        """详情页全部画质：{quality: (code, vid)}，画质从高到低"""
        best = {}
        for code, q, vid, qp in self._DLOAD.findall(html):
            q = int(qp)
            if q not in best:
                best[q] = (code, vid)
        return sorted(best.items(), key=lambda kv: -kv[0])

    def _detail_url(self, code):
        return self.HOST + '/video-%s/' % code

    def detailContent(self, ids):
        sid = str(ids[0]) if ids else ''
        # 类别虚拟详情：第1-5页为播放源，每页是该分类的视频选集
        if sid.startswith('catgroup:'):
            slug = sid.split(':', 1)[1]
            name = slug
            for c in self._categories():
                if c['slug'] == slug:
                    name = c['name']
                    break
            play_from, play_url = [], []
            for p in range(1, self.GROUP_PAGES + 1):
                html, _u = self._http(
                    self._list_url('/cat/%s/' % slug, p))
                items = self._parse_list(html.decode('utf-8', 'ignore'))
                if not items:
                    break
                eps = '#'.join('%s$%s' % (v['vod_name'], v['vod_id'])
                               for v in items)
                play_from.append('第%d页' % p)
                play_url.append(eps)
            return {'list': [{'vod_id': sid, 'vod_name': name,
                              'vod_pic': '', 'type_name': '类别',
                              'vod_remarks': '共 %d 个视频分类' % len(self._categories()),
                              'vod_play_from': '$$$'.join(play_from),
                              'vod_play_url': '$$$'.join(play_url)}]}
        # 真实视频详情
        code = sid.split(':', 1)[1] if ':' in sid else sid
        url = self._detail_url(code)
        html, _u = self._http(url)
        html = html.decode('utf-8', 'ignore')
        title = self._clean(
            re.search(r'property="og:title" content="([^"]+)"', html).group(1)
            .rsplit(' - EPORNER', 1)[0]
            if re.search(r'property="og:title" content="([^"]+)"', html)
            else '')
        pic = (re.search(r'property="og:image" content="([^"]+)"', html).group(1)
               if re.search(r'property="og:image" content="([^"]+)"', html)
               else '')
        dur = ''
        m = re.search(r'duration" content="(\d+)"', html)
        if m:
            dur = self._fmt_dur(m.group(1))
        ups = re.findall(r'href="/profile/[^"]+"[^>]*>([^<]+)</a>', html)
        tags = [self._clean(t) for t in
                re.findall(r'href="/tag/[^"]+"[^>]*>([^<]+)</a>', html)]
        # 详情页标签里混着标题拆出来的单个词（About/After 这类），只留词组
        tags = [t for t in dict.fromkeys(tags) if ' ' in t][:12]
        dloads = self._dloads(html)
        play_from, play_url = [], []
        if dloads:
            eps = '#'.join('%dp$play@@%s@@%d@@%s' % (q, c, q, v)
                           for q, (c, v) in dloads)
            play_from.append('EPORNER画质')
            play_url.append(eps)
        remarks = ' · '.join(x for x in
                             [('%dp' % dloads[0][0]) if dloads else '', dur] if x)
        return {'list': [{'vod_id': sid, 'vod_name': title or code,
                          'vod_pic': pic, 'type_name': '视频',
                          'vod_actor': ups[0] if ups else '',
                          'vod_remarks': remarks,
                          'vod_content': '、'.join(tags),
                          'vod_play_from': '$$$'.join(play_from),
                          'vod_play_url': '$$$'.join(play_url)}]}

    # ── 搜索 ──────────────────────────────────────────────────
    def searchContent(self, key, quick, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        key = (key or '').strip()
        if pg == 1 or not self._search_url:
            html, final = self._http(self.HOST + '/search/',
                                     data={'search': key})
            self._search_url = final
        else:
            base = self._search_url.rstrip('/')
            html, _u = self._http(base + '/%d/' % pg)
        return {'list': self._parse_list(html.decode('utf-8', 'ignore')),
                'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ── 播放 ──────────────────────────────────────────────────
    def playerContent(self, flag, id, vipFlags):
        sid = str(id or '')
        # 画质选集：play@@<code>@@<q>@@<vid>，dload 链接现取现跳转，不用重取详情页
        m = re.match(r'play@@([^@]+)@@(\d+)@@(\d+)$', sid)
        if m:
            code, q, vid = m.groups()
            url = '%s/dload/%s/%s/%s-%sp.mp4' % (self.HOST, code, q, vid, q)
            return {'parse': 0, 'url': url,
                    'header': {'User-Agent': self.UA,
                               'Referer': self._detail_url(code)}}
        # 类别选集：video:<code>，取详情页最高画质直链
        m2 = re.match(r'video:([^@]+)$', sid)
        if m2:
            code = m2.group(1)
            html, _u = self._http(self._detail_url(code))
            dloads = self._dloads(html.decode('utf-8', 'ignore'))
            if dloads:
                q, (c, v) = dloads[0]
                url = '%s/dload/%s/%s/%s-%sp.mp4' % (self.HOST, c, q, v, q)
                return {'parse': 0, 'url': url,
                        'header': {'User-Agent': self.UA,
                                   'Referer': self._detail_url(code)}}
        return {'parse': 0, 'url': ''}

    def isVideoFormat(self, url):
        return url.startswith('http') and ('.mp4' in url or '.m3u8' in url)

    def manualVideoCheck(self):
        return False
