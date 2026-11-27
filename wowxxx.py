# -*- coding: utf-8 -*-
"""
WOWXXX.TO (ex WOW.XXX) - 免费高级片聚合站
Brazzers / Blacked / Team Skeet / MYLF / Adult Time / Tushy / Vixen 等
全片直链 mp4，多画质 (480p/720p/1080p/2160p 以实际为准)，无需登录，无票据
两级浏览：首页 7 个类（4 个排序 + 片商/女优/类别）；点开片商列出站上真正的片商
（/sites/ 索引动态取，如 Tushy、New Sensations、Girlsway 等 20 多个，带片量），
点开女优列出 250 位女优（带照片与片量，分页），点开类别列出全部 356 个分类（分页）；
点开某个片商/女优/类别，详情页以“第1页…第5页”为播放源、每页 24 条选集，点选集直接播最高画质
注意：Brazzers/Blacked/Team Skeet 等大牌并不在站上（片商页是空的，搜到的片子没有直链、播不了），
所以片商只列站上真实有的；BLACKED RAW 虽不在索引里但有片能播，手动保留
分类 356 个动态取，女优取 /models/ 前 10 页共 250 位（站上共 880 页约 2.2 万位，
全加分类栏会卡死；其他女优直接搜名字，站内搜索按女优匹配）
封面备注标最高画质（如 2160p · 27:16），片名带 [片商] - 前缀，和站点一致
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
    # 排序 + 片商是固定的；分类（356 个）与女优（/models/ 首页 25 位）
    # 是动态取的，见 homeContent / _categories / _models
    SORTS = [
        ('latest', '最新更新', '/latest-updates/'),
        ('popular', '最受欢迎', '/most-popular/'),
        ('week', '本周热门', '/most-popular/week/'),
        ('toprated', '好评最高', '/top-rated/'),
    ]
    # 站上真正的片商是 /sites/ 索引里的（动态取，见 _studios）；
    # Brazzers/Blacked/Team Skeet/MYLF/Adult Time/Vixen/Hard X/Pure Taboo
    # 并不在站上：/sites/<名>/ 是空的，走搜索只能搜到 35 条且片子没有直链
    # （0/24 有 <source>），播不了，所以不用；BLACKED RAW 不在索引里，
    # 但 /sites/blacked-raw/ 有片且能播，_studios() 里手动补上
    # 兜底：/sites/ 取不到时用的已知真片商
    STATIC_STUDIOS = [
        ('blacked-raw', 'BLACKED RAW', ''),
        ('tushy', 'Tushy', '685'),
        ('new-sensations', 'New Sensations', '1937'),
        ('girlsway', 'Girlsway', '629'),
        ('youngbusty', 'Young Busty', '423'),
        ('devils-film', "Devil's Film", '475'),
        ('cuckold-sessions', 'Cuckold Sessions', '321'),
        ('teens-love-anal', 'Teens Love Anal', '142'),
        ('ilovepov', 'I Love POV', '233'),
        ('wifey', 'Wifey', '94'),
        ('tomboyz', 'Tomboyz', '37'),
    ]
    _studios_cache = None
    # 常用分类（仅作动态取不到时的兜底）
    STATIC_CATS = [
        ('cat:amateur', 'Amateur'), ('cat:anal', 'Anal'),
        ('cat:asian', 'Asian'), ('cat:bbw', 'BBW'),
        ('cat:bdsm', 'BDSM'), ('cat:big-tits', 'Big Tits'),
        ('cat:blonde', 'Blonde'), ('cat:brunette', 'Brunette'),
        ('cat:creampie', 'Creampie'), ('cat:ebony', 'Ebony'),
        ('cat:hardcore', 'Hardcore'), ('cat:interracial', 'Interracial'),
        ('cat:lesbian', 'Lesbian'), ('cat:mature', 'Mature'),
        ('cat:milf', 'MILF'), ('cat:pov', 'POV'),
        ('cat:public', 'Public'), ('cat:teen', 'Teen'),
        ('cat:threesome', 'Threesome'),
    ]
    _cats_cache = None
    _models_cache = None
    MODEL_PAGES = 10  # 女优取 /models/ 前 10 页 = 250 位
    GROUP_PAGES = 5  # 大分类详情里展示前 5 页影片（每页 24 条，共 120 条选集）

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

    def _parse_list(self, html, enrich=True):
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
        # enrich=False 时跳过这一步（两级详情的选集列表用轻解析，快得多）
        if enrich and out:
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

    def _parse_list_light(self, html):
        # 轻解析：只取标题/封面/时长，不取详情页画质（两级详情的选集用）
        return self._parse_list(html, enrich=False)

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
        # 两级浏览：首页只有 7 个类（4 个排序 + 3 个大分类）；
        # 点开片商/女优/类别，在分类页里列出全部子项（见 categoryContent）
        cats = [{'type_id': t, 'type_name': n} for t, n, _ in self.SORTS]
        cats += [{'type_id': 'group:studios', 'type_name': '片商'},
                 {'type_id': 'group:models', 'type_name': '女优'},
                 {'type_id': 'group:cats', 'type_name': '类别'}]
        return {'class': cats}

    def _categories(self):
        # 站上全部 356 个分类，动态取，每次会话只取一次；取不到用常用分类兜底
        if Spider._cats_cache is not None:
            return Spider._cats_cache
        cats = []
        try:
            html = self._http(self.HOST + '/categories/').decode(
                'utf-8', 'ignore')
            seen = set()
            for slug, inner in re.findall(
                    r'href="https?://www\.wowxxx\.to/categories/([^/"]+)/"'
                    r'[^>]*>(.*?)</a>', html, re.S):
                name = self._clean(inner)
                if slug and name and slug not in seen:
                    seen.add(slug)
                    cats.append((slug, name))
        except Exception:
            cats = []
        if not cats:
            cats = [(t[4:], n) for t, n in self.STATIC_CATS]
        Spider._cats_cache = cats
        return cats

    def _models(self):
        # 女优（Pornstars）：/models/ 前 MODEL_PAGES 页（每页 25 位），并行取；
        # 返回 (slug, 名字, 照片, 片量)；站上女优共 880 页约 2.2 万位，
        # 只取最热门的前 250 位（第 10 页仍有 Eva Elfie、Brooklyn Chase、
        # Aidra Fox 这类热门女优）；想找其他的女优直接搜名字，站内搜索按女优匹配
        # 注意：/models/ 上还有国家/排序链接（/models/?country_id=…），
        # 只有带女优照片（data-original, contents/models/）的才是女优卡片
        if Spider._models_cache is not None:
            return Spider._models_cache
        models = []
        try:
            def _one(pg):
                html = self._http(self.HOST + '/models/'
                                  + ('%d/' % pg if pg > 1 else '')).decode(
                                      'utf-8', 'ignore')
                out = []
                for slug, title, inner in re.findall(
                        r'href="https?://www\.wowxxx\.to/models/([^/"]+)/"'
                        r'[^>]*title="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
                    if not slug or slug.isdigit():
                        continue
                    if 'contents/models/' not in inner:
                        continue
                    name = self._clean(title)
                    if not name:
                        name = re.sub(r'^\d+\s*', '', self._clean(inner))
                    photo = ''
                    pm = re.search(r'data-original="([^"]+)"', inner)
                    if pm:
                        photo = pm.group(1)
                    count = ''
                    cm = re.search(r'<div class="videos">(\d+)</div>', inner)
                    if cm:
                        count = cm.group(1)
                    if name:
                        out.append((slug, name, photo, count))
                return out
            with ThreadPoolExecutor(max_workers=8) as ex:
                pages = list(ex.map(_one, range(1, self.MODEL_PAGES + 1)))
            seen = set()
            for page in pages:
                for slug, name, photo, count in page:
                    if slug not in seen:
                        seen.add(slug)
                        models.append((slug, name, photo, count))
        except Exception:
            models = []
        Spider._models_cache = models
        return models

    def _studios(self):
        # 站上真正的片商：/sites/ 索引，动态取，每次会话只取一次；
        # 返回 (slug, 名字, 片量)。索引里有两种链接：带 <h2>名字</h2> 的大站
        # （名字在 h2 里，片量在 "See All N Videos" 里）和纯文字的小站；
        # title-az/title-za/top-rated/total-videos 是排序链接，不是片商，排除
        if Spider._studios_cache is not None:
            return Spider._studios_cache
        studios = []
        try:
            html = self._http(self.HOST + '/sites/').decode(
                'utf-8', 'ignore')
            seen = set()
            for name, slug, count in re.findall(
                    r'<h2>([^<]+)</h2>.*?<a class="more" '
                    r'href="https?://www\.wowxxx\.to/sites/([^/"]+)/"[^>]*>'
                    r'\s*<span>See All (\d+) Videos</span>', html, re.S):
                if slug and slug not in seen:
                    seen.add(slug)
                    studios.append((slug, self._clean(name), count))
            for slug, inner in re.findall(
                    r'href="https?://www\.wowxxx\.to/sites/([^/"]+)/"'
                    r'[^>]*>([^<]+)</a>', html):
                if (not slug or slug in ('title-az', 'title-za',
                                         'top-rated', 'total-videos')
                        or slug in seen):
                    continue
                name = self._clean(inner)
                if name and 'See All' not in name:
                    seen.add(slug)
                    studios.append((slug, name, ''))
            if 'blacked-raw' not in seen:
                studios.insert(0, ('blacked-raw', 'BLACKED RAW', ''))
        except Exception:
            studios = []
        if not studios:
            studios = list(self.STATIC_STUDIOS)
        Spider._studios_cache = studios
        return studios

    def homeVideoContent(self):
        html = self._http(self.HOST + '/latest-updates/').decode(
            'utf-8', 'ignore')
        return {'list': self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        # 大分类：点开后列出全部子项（片商 11 个 / 女优 250 位分页 / 类别 356 个分页）
        if tid == 'group:studios':
            return self._group_studios()
        if tid == 'group:models':
            return self._group_models(pg)
        if tid == 'group:cats':
            return self._group_cats(pg)
        path = None
        for t, _, p in self.SORTS:
            if t == tid:
                path = p
                break
        # 兼容旧版分类栏缓存下来的类（cat:/model: 直接当视频列表；
        # site: 按现在真实的片商解析，旧的搜索类如 Brazzers 已不在站上，返回空）
        if path is None and tid.startswith('site:'):
            slug = tid[5:]
            if any(s == slug for s, _n, _c in self._studios()):
                path = '/sites/%s/' % slug
        elif path is None and tid.startswith('cat:'):
            path = '/categories/%s/' % tid[4:]
        elif path is None and tid.startswith('model:'):
            path = '/models/%s/' % tid[6:]
        if path is None:
            return {'list': []}
        html = self._http(self._list_url(path, pg)).decode('utf-8', 'ignore')
        return {'list': self._parse_list(html), 'page': pg or 1,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    def _group_studios(self):
        # 站上真正的片商；封面取各片商第一条视频的封面（并行取）
        studios = self._studios()

        def _cover(slug):
            try:
                html = self._http(self._list_url('/sites/%s/' % slug, 1)
                                  ).decode('utf-8', 'ignore')
                items = self._parse_list_light(html)
                return items[0]['vod_pic'] if items else ''
            except Exception:
                return ''
        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                covers = list(ex.map(_cover, [s for s, _n, _c in studios]))
        except Exception:
            covers = [''] * len(studios)
        items = [{'vod_id': 'site:' + slug, 'vod_name': name,
                  'vod_pic': cover,
                  'vod_remarks': ('%s 部' % count) if count else ''}
                 for (slug, name, count), cover in zip(studios, covers)]
        return {'list': items, 'page': 1, 'pagecount': 1,
                'limit': 90, 'total': len(items)}

    def _group_models(self, pg):
        # 250 位女优，24 位一页，带照片与片量
        pg = int(pg or 1)
        all_m = self._models()
        per = 24
        start = (pg - 1) * per
        items = [{'vod_id': 'model:' + slug, 'vod_name': name,
                  'vod_pic': photo,
                  'vod_remarks': ('%s 部' % count) if count else ''}
                 for slug, name, photo, count
                 in all_m[start:start + per]]
        return {'list': items, 'page': pg,
                'pagecount': max(1, (len(all_m) + per - 1) // per),
                'limit': 90, 'total': len(all_m)}

    def _group_cats(self, pg):
        # 356 个分类，24 个一页；站上分类没有配图，封面留空
        pg = int(pg or 1)
        all_c = self._categories()
        per = 24
        start = (pg - 1) * per
        items = [{'vod_id': 'cat:' + slug, 'vod_name': name,
                  'vod_pic': '', 'vod_remarks': ''}
                 for slug, name in all_c[start:start + per]]
        return {'list': items, 'page': pg,
                'pagecount': max(1, (len(all_c) + per - 1) // per),
                'limit': 90, 'total': len(all_c)}

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
        raw = raw.strip()
        # 大分类里的子项（片商/女优/类别）：虚拟详情，影片做选集
        if raw.startswith(('site:', 'model:', 'cat:')):
            return self._group_detail(raw)
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

    def _group_info(self, gid):
        # 大分类子项 -> (名字, 列表页路径, 封面)；找不到返回 ('', None, '')
        if gid.startswith('site:'):
            slug = gid[5:]
            for s, n, _c in self._studios():
                if s == slug:
                    return n, '/sites/%s/' % slug, ''
            return '', None, ''
        if gid.startswith('model:'):
            slug = gid[6:]
            for s, n, photo, _c in self._models():
                if s == slug:
                    return n, '/models/%s/' % slug, photo
            return '', None, ''
        if gid.startswith('cat:'):
            slug = gid[4:]
            for s, n in self._categories():
                if s == slug:
                    return n, '/categories/%s/' % slug, ''
            return '', None, ''
        return '', None, ''

    def _group_detail(self, gid):
        # 虚拟详情：某个片商/女优/类别的影片，用“第1页…第N页”做播放源，
        # 每页 24 条选集（标题 + 时长），点选集直接播最高画质
        name, path, cover = self._group_info(gid)
        if not path:
            return {'list': []}

        def _one(p):
            try:
                html = self._http(self._list_url(path, p)).decode(
                    'utf-8', 'ignore')
                return self._parse_list_light(html)
            except Exception:
                return []
        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                pages = list(ex.map(_one, range(1, self.GROUP_PAGES + 1)))
        except Exception:
            pages = []
        if not cover and pages and pages[0]:
            cover = pages[0][0]['vod_pic']
        play_from, play_urls = [], []
        for i, items in enumerate(pages, 1):
            if not items:
                continue
            play_from.append('第%d页' % i)
            eps = []
            for it in items:
                t = it['vod_name']
                if it['vod_remarks']:
                    t = '%s (%s)' % (t, it['vod_remarks'])
                eps.append('%s$video:%s' % (t, it['vod_id']))
            play_urls.append('#'.join(eps))
        if not play_urls:
            return {'list': []}
        return {'list': [{'vod_id': gid, 'vod_name': name, 'vod_pic': cover,
                          'vod_remarks': '点选集直接播放（最高画质）',
                          'vod_play_from': '$$$'.join(play_from),
                          'vod_play_url': '$$$'.join(play_urls)}]}

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
        sid = str(id or '')
        m = re.match(r'play@@([^@]+)@@(.+)', sid)
        if m:
            slug, label = m.group(1), m.group(2)
            html = self._http(self.HOST + '/videos/%s/' % slug).decode(
                'utf-8', 'ignore')
            for lbl, url in self._sources(html):
                if lbl == label:
                    return {'parse': 0, 'url': url,
                            'header': {'User-Agent': self.UA,
                                       'Referer': self.HOST + '/videos/%s/' % slug}}
            return {'parse': 0, 'url': ''}
        # 大分类详情里的选集：video:<slug>，直接取该片最高画质
        m2 = re.match(r'video:([^@]+)$', sid)
        if m2:
            slug = m2.group(1)
            html = self._http(self.HOST + '/videos/%s/' % slug).decode(
                'utf-8', 'ignore')
            sources = self._sources(html)
            if sources:
                return {'parse': 0, 'url': sources[0][1],
                        'header': {'User-Agent': self.UA,
                                   'Referer': self.HOST + '/videos/%s/' % slug}}
        return {'parse': 0, 'url': ''}

    def isVideoFormat(self, url):
        return url.startswith('http') and ('.mp4' in url or '.m3u8' in url)

    def manualVideoCheck(self):
        return False
