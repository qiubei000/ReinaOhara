# -*- coding: utf-8 -*-
# JAVHD
#
# 真网站 javhd.com（Vue SSR + API），不是 App API。
# 模块 JAVHD解锁VIP 只改前端标志位（GUEST→MEMBER、藏试看文案、
# 去 blur、player_api/sources 改 premium 标志），播放本身是 B1：
# 游客态直接调 GET /zh/player_api?videoId=<playerId>（仅
# X-Requested-With 头）就拿到 4 档完整 mp4 直链，premium 标签
# 视频也一样（实测 131412 premium，1080p 3.64GB 完整全片）。
# 签名 token 形如 <base64>,<unix_ts>，ts 约取流后 +20 分钟过期，
# 所以播放一律现调 player_api 取新鲜地址，绝不缓存签名 URL。
#
# 两套 id 别混用：列表 id（content id，如 59152/88630）≠ playerId
# （cms_id，如 119105/131410）。content_block 的 studioUrl 末尾
# -<playerId> 可直接取；分类/搜索 fragment 的 link-content 需再拉
# 视频页从 player_api?videoId= 或 cms_id= 取 playerId。
# 坑：视频页请求别带 XHR 头（带了 500）；分页走
# pagination_params.next（…/justadded/all/<N>），?page=N 无效；
# content_block 的 video 字段是 5 秒预告，不是正片。

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    try:
        from base.spider import BaseSpider
    except ImportError:
        try:
            from spider import Spider as BaseSpider
        except ImportError:
            try:
                from spider import BaseSpider
            except ImportError:
                class BaseSpider:
                    pass


class Spider(BaseSpider):
    SITE_NAME = 'JAVHD'
    HOSTS = ['https://javhd.com',
             'https://www.javhd.com']
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
    # 注意：UA 决定服务端分页——移动端 UA 每页只给 18 条，桌面 UA 给 36 条
    # （2026-11-26 实测），所以用桌面 UA
    # 分类：部数前 30（2026-11-26 /zh/sex-categories 实站核对，共 382 个）；
    # 中文名有重复（口交/自慰/内射/巨乳各有多个 slug），type_id 一律用 slug。
    CATS = [
        ('all', '全部视频'),
        ('asian', '亚洲'),
        ('uncensored', '无码'),
        ('blowjob', '口交'),
        ('hardcore', '重口味'),
        ('missionary', '传教士式'),
        ('handjob', '手交'),
        ('doggystyle', '后入式'),
        ('fingering', '指交'),
        ('riding', '骑乘'),
        ('brunette', '黑发'),
        ('japanese', '日本'),
        ('masturbation', '自慰'),
        ('lingerie', '内衣'),
        ('cunnilingus', '口交'),
        ('small-tits', '小胸'),
        ('big-tits', '巨乳'),
        ('hairy-pussy', '毛茸茸的阴部'),
        ('creampie', '内射'),
        ('reverse-cowgirl', '反向女牛仔'),
        ('toys', '玩具'),
        ('shaved-pussy', '剃毛小穴'),
        ('masturbating', '自慰'),
        ('natural-tits', '天然巨乳'),
        ('cumshot', '射精'),
        ('kissing', '亲吻'),
        ('teen', '年轻女孩'),
        ('on-her-knees', '跪姿'),
        ('cum-in-pussy', '内射'),
        ('sucking', '口交'),
        ('vibrator', '震动棒'),
    ]
    PER_PAGE = 36

    def getName(self):
        return self.SITE_NAME

    def init(self, extend=""):
        self.extend = extend or ''
        self._host_ok = None
        self._cache = {}   # content id -> {player_id, link, title, pic, remarks}
        self._next = {}    # (kind, key) -> next page path
        host = ''
        if self.extend:
            try:
                cfg = json.loads(self.extend) if isinstance(
                    self.extend, str) else dict(self.extend)
                if isinstance(cfg, dict) and cfg.get('host'):
                    host = str(cfg['host']).rstrip('/')
            except Exception:
                if self.extend.strip().startswith('http'):
                    host = self.extend.strip().rstrip('/')
        if host:
            self.HOSTS = [host] + [h for h in self.HOSTS if h != host]

    def __init__(self):
        self.extend = ''
        self._host_ok = None
        self._cache = {}
        self._next = {}

    # ── 基础请求 ──────────────────────────────────────────
    def _gunzip(self, raw):
        if not raw:
            return b''
        if raw[:2] != b'\x1f\x8b':
            return raw
        try:
            return gzip.decompress(raw)
        except Exception:
            pass
        import zlib
        try:
            d = zlib.decompressobj(31)
            out = d.decompress(raw)
            out += d.flush()
            return out
        except Exception:
            return b''

    def _http(self, url, timeout=20, xhr=False, headers=None):
        """拉取并解码文本（失败为空串）；xhr=True 时带 XHR + JSON 头。"""
        h = {'User-Agent': self.UA,
             'Accept-Encoding': 'gzip',
             'Referer': (self._host_ok or self.HOSTS[0]) + '/zh/'}
        if xhr:
            h['X-Requested-With'] = 'XMLHttpRequest'
            h['Accept'] = 'application/json, text/javascript, */*; q=0.01'
        if headers:
            h.update(headers)
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers=h)
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        raw = r.read()
                except Exception as e:
                    raw = getattr(e, 'partial', None) or b''
                if raw:
                    txt = self._gunzip(raw).decode('utf-8', 'ignore')
                    if txt:
                        return txt
            except Exception:
                time.sleep(0.5)
                continue
        return ''

    def _get(self, path, xhr=False):
        """多 host 重试；path 可为绝对 URL。"""
        if path.startswith('http'):
            txt = self._http(path, xhr=xhr)
            return txt
        hosts = ([self._host_ok] if self._host_ok else []) + \
                [h for h in self.HOSTS if h != self._host_ok]
        for host in hosts:
            txt = self._http(host + path, xhr=xhr)
            if txt:
                self._host_ok = host
                return txt
            time.sleep(0.3)
        return ''

    # ── 解析 ──────────────────────────────────────────────
    def _parse_fragment(self, txt):
        """解析列表 JSON fragment：{status, template, results_count,
        per_page, pagination_params:{total_pages, next}}。
        template 是 thumb-component HTML，逐个取属性。"""
        if not txt:
            return [], 1, 0, '', None
        try:
            d = json.loads(txt)
        except Exception:
            return [], 1, 0, '', None
        tpl = d.get('template') or ''
        pp = d.get('pagination_params') or {}
        total = int(d.get('results_count') or 0)
        pages = int(pp.get('total_pages') or 1)
        per_page = int(d.get('per_page') or pp.get('per_page') or 0) or None
        nxt = pp.get('next') or ''
        items = []
        for m in re.finditer(r'<thumb-component\b.*?</thumb-component>',
                             tpl, re.S):
            tag = m.group(0)
            attrs = dict(re.findall(
                r'([\w-]+)="([^"]*)"', tag))
            cid = attrs.get('video-id') or ''
            if not cid:
                continue
            link = attrs.get('link-content') or ''
            pid = ''
            mm = re.search(r'-(\d+)\s*$', link)
            if mm:
                pid = mm.group(1)
            pic = attrs.get('url-thumb') or ''
            name = attrs.get('title') or ''
            label = attrs.get('has-label') or ''
            remarks = label if label in ('premium', 'premiumFree') else ''
            views = attrs.get('views') or ''
            if views and not remarks:
                remarks = views + ' 观看'
            self._cache[cid] = {'player_id': pid, 'link': link,
                                'title': name, 'pic': pic,
                                'remarks': remarks}
            # vod_id 里带上 link-content：冷缓存实例（detail 与 play 不在
            # 同一个 Spider 实例时）也能还原视频页 URL 取 playerId，
            # 否则 studio 视频（/zh/studio/room/...）无从取 playerId
            items.append({'vod_id': 'fr@@{}@@{}'.format(
                              cid, urllib.parse.quote(link, safe='')),
                          'vod_name': name,
                          'vod_pic': pic, 'vod_remarks': remarks,
                          'vod_actor': '', 'vod_content': ''})
        return items, pages, total, nxt, per_page

    def _player_id_from_page(self, cid, link=None):
        """拉视频页（不带 XHR 头），从 player_api?videoId= / cms_id= 取 playerId。"""
        cached = self._cache.get(cid) or {}
        link = link or cached.get('link') or ''
        url = link if link else '/zh/id/{}/'.format(cid)
        html = self._get(url, xhr=False)
        if not html:
            return ''
        m = re.search(r'player_api\?videoId=(\d+)', html)
        if m:
            return m.group(1)
        m = re.search(r'cms_id=(\d+)', html)
        if m:
            return m.group(1)
        return ''

    def _resolve_player_id(self, cid, link=None):
        cached = self._cache.get(cid) or {}
        pid = cached.get('player_id') or ''
        if pid:
            return pid
        pid = self._player_id_from_page(cid, link=link)
        if pid:
            self._cache[cid] = dict(cached, player_id=pid)
        return pid

    # ── 六接口 ────────────────────────────────────────────
    def homeContent(self, filter):
        return {'class': [{'type_id': i, 'type_name': n}
                          for i, n in self.CATS],
                'filters': {}}

    def homeVideoContent(self):
        """首页块：content_block custom，pgid 可省，offset 分页（块共 24 条）。"""
        txt = self._get('/zh/api/content_block?block=custom&isCasting=1'
                        '&count=21&offset=0', xhr=True)
        items = []
        try:
            d = json.loads(txt) if txt else {}
        except Exception:
            d = {}
        for v in (d.get('template') or []):
            cid = str(v.get('id') or '')
            if not cid:
                continue
            thumbs = v.get('thumbs') or {}
            pic = (thumbs.get('1130x706') or thumbs.get('940x530')
                   or thumbs.get('468x264') or '')
            link = v.get('studioUrl') or ''
            pid = ''
            mm = re.search(r'-(\d+)\s*$', link)
            if mm:
                pid = mm.group(1)
            if link and not link.startswith('http'):
                link = (self._host_ok or self.HOSTS[0]) + link
            remarks = str(v.get('length') or '')
            self._cache[cid] = {'player_id': pid, 'link': link,
                                'title': v.get('title') or '',
                                'pic': pic, 'remarks': remarks}
            # studioUrl 末尾 -<playerId> 可直接取，vod_id 里带上 pid，
            # detail 不用再拉视频页
            items.append({'vod_id': 'cb@@{}@@{}'.format(cid, pid),
                          'vod_name': v.get('title') or '',
                          'vod_pic': pic, 'vod_remarks': remarks,
                          'vod_actor': '', 'vod_content': ''})
        return {'list': items}

    def _list_url(self, tid, pg):
        """分类/全部列表 URL；pg>1 走 justadded/all/<N>（?page=N 无效）。"""
        if tid == 'all':
            base = '/zh/japanese-porn-videos'
        else:
            base = '/zh/japanese-porn-videos/category/' + tid
        if pg <= 1:
            return base
        return base + '/justadded/all/{}'.format(pg)

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = str(tid)
        txt = self._get(self._list_url(tid, pg), xhr=True)
        items, pages, total, nxt, per_page = self._parse_fragment(txt)
        return {'page': pg, 'pagecount': pages,
                'limit': per_page or self.PER_PAGE,
                'total': total, 'list': items}

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0]) if ids else ''
        else:
            raw = str(ids or '').split(',')[0].strip()
        if not raw:
            return {'list': []}
        # vod_id 形态：fr@@<cid>@@<quote(link)>（分类/搜索）、
        # cb@@<cid>@@<pid>（首页推荐块）、兼容裸 cid（旧缓存）
        cid, pid, link = '', '', ''
        if raw.startswith('fr@@'):
            parts = raw.split('@@')
            cid = parts[1] if len(parts) > 1 else ''
            link = urllib.parse.unquote(parts[2]) if len(parts) > 2 else ''
        elif raw.startswith('cb@@'):
            parts = raw.split('@@')
            cid = parts[1] if len(parts) > 1 else ''
            pid = parts[2] if len(parts) > 2 else ''
        else:
            cid = raw
        if not cid:
            return {'list': []}
        cached = self._cache.get(cid) or {}
        if link:
            cached = dict(cached, link=link)
            self._cache[cid] = cached
        if not pid:
            pid = self._resolve_player_id(cid, link or None)
        name = cached.get('title') or cid
        pic = cached.get('pic') or ''
        remarks = cached.get('remarks') or ''
        if pid:
            play = '第1集$play@@{}'.format(pid)
        else:
            # 播放器页 transient 失败时留 cid 入口，播放时再解析一次
            play = '第1集$play@@cid:{}'.format(cid)
        return {'list': [{'vod_id': raw, 'vod_name': name,
                          'vod_pic': pic, 'vod_remarks': remarks,
                          'vod_actor': '', 'vod_content': '',
                          'vod_play_from': 'JAVHD',
                          'vod_play_url': play}]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        q = urllib.parse.quote(key or '')
        if pg > 1:
            # ?page=N 已证实无效（返回的还是第 1 页），搜索只取第 1 页
            return {'list': []}
        txt = self._get('/zh/search?q=' + q, xhr=True)
        items, pages, total, nxt, per_page = self._parse_fragment(txt)
        return {'page': pg, 'pagecount': pages,
                'limit': per_page or self.PER_PAGE,
                'total': total, 'list': items}

    def playerContent(self, flag, id, vipFlags):
        # id 形态：play@@<playerId> 或 play@@cid:<contentId>
        raw = str(id or '')
        pid, cid = '', ''
        m = re.match(r'play@@cid:(\d+)', raw)
        if m:
            cid = m.group(1)
        else:
            m = re.match(r'play@@(\d+)', raw)
            if m:
                pid = m.group(1)
            elif raw.isdigit():
                pid = raw
        if not pid and cid:
            pid = self._resolve_player_id(cid)
        url = ''
        if pid:
            txt = self._get('/zh/player_api?videoId={}'.format(pid),
                            xhr=True)
            try:
                d = json.loads(txt) if txt else {}
            except Exception:
                d = {}
            srcs = d.get('sources') or []
            best = None
            for s in srcs:
                src = s.get('src') or ''
                if not src:
                    continue
                res = int(s.get('res') or 0)
                if best is None or res > best[0]:
                    best = (res, src)
            if best:
                url = best[1]
        host = self._host_ok or self.HOSTS[0]
        header = {'User-Agent': self.UA, 'Referer': host + '/zh/'}
        if url and (url.endswith('.mp4') or '.mp4?' in url
                    or url.endswith('.m3u8') or '.m3u8?' in url):
            # 签名地址现取现播，parse=0 直出，绝不缓存
            return {'parse': 0, 'url': url, 'header': header}
        # 取不到时交回视频页让壳子自己解析；优先用缓存的真实视频页链接，
        # 别拿 playerId 拼 /zh/id/（playerId 不是 contentId，会 404）
        cached = self._cache.get(cid) or {}
        link = cached.get('link') or ''
        if link.startswith('/'):
            fallback = host + link
        elif link:
            fallback = link
        else:
            fallback = '{}/zh/id/{}/'.format(host, cid or '')
        return {'parse': 1, 'url': fallback, 'header': header}

    def localProxy(self, params):
        """图片代理：封面直链防盗链时经本地代理取图。"""
        try:
            if isinstance(params, dict) and params.get('type') == 'pic':
                url = params.get('url', '') or ''
                if url:
                    req = urllib.request.Request(
                        url, headers={'User-Agent': self.UA,
                                      'Referer': self._host_ok or
                                      self.HOSTS[0] + '/zh/'})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        data = r.read()
                        if r.status == 200 and data:
                            mime = (r.headers.get('Content-Type')
                                    or 'image/jpeg').split(';')[0]
                            return [200, mime, data, '']
        except Exception:
            pass
        return [200, 'text/plain; charset=utf-8', b'', '']

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return (u.endswith('.m3u8') or '.m3u8?' in u
                or u.endswith('.mp4') or '.mp4?' in u)
