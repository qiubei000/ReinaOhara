# -*- coding: utf-8 -*-
"""
91热爆 91RB (91rb.com) - 免费区 Python 爬虫
只读检查 2026-11-28：首页/列表/详情均可直接打开，无 Cloudflare、无年龄门、无登录墙
列表：KVS 模板，20 条/页，封面 data-original 320x180，备注 观看量 · 时长 · HD
详情：站内 HTML5 播放器，<source> 给 m3u8 直链（现取现用，带 k/t 签名），
  如 97819 有原画 + 720P 两档；另有 /get_file/0/...mp4 直链作备用
分页：/latest-updates/2、/most-popular/2、/categories/<slug>/2
搜索：GET /search/?q=<词>&page=<页>
范围说明（不破 VIP）：
- VIP 片在列表里带 class "private" + VIP 角标，爬虫直接跳过不收；
  详情页无 <source>、含 login-required，playerContent 也不绕过，返回空
- 偷拍 / 摄像头（/categories/tp/、/categories/cctv/）两个分类不收；
  列表里标题含 偷拍 / 厕拍 / 偷窥 / 针孔 的条目也直接跳过
"""
import re
import urllib.parse
import urllib.request

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = 'https://91rb.com'
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
    TIMEOUT = 20

    # (tid, name, path) — tp 偷拍、cctv 摄像头两个分类不收
    CLASSES = [
        ('home', '首页推荐', '/'),
        ('latest', '最新上传', '/latest-updates/'),
        ('popular', '热门视频', '/most-popular/'),
        ('fav', '收藏最多', '/most-favourited/'),
        ('tan-hua', '探花', '/categories/tan-hua/'),
        ('chi-gua', '今日吃瓜', '/categories/chi-gua/'),
        ('gouchang', '国产', '/categories/gouchang/'),
        ('wm', '无码', '/categories/wm/'),
        ('cnav', 'AV中字', '/categories/cnav/'),
        ('zb', '主播', '/categories/zb/'),
        ('ry', '人妖', '/categories/ry/'),
        ('oumei', '欧美', '/categories/58ad36b63f0a78230c2aba5ef5aa3c47/'),
        ('dm', '动漫', '/categories/dm/'),
    ]
    _PATH = {t: p for t, _n, p in CLASSES}

    def getName(self):
        return '91热爆'

    def init(self, extend):
        pass

    # ── HTTP ──────────────────────────────────────────────────
    def _http(self, url):
        h = {'User-Agent': self.UA, 'Referer': self.HOST + '/',
             'Accept-Language': 'zh-CN,zh;q=0.9'}
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return resp.read().decode('utf-8', 'ignore'), resp.geturl()
            except Exception:
                continue
        return '', url

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
    _ITEM = re.compile(
        r'<div class="thumb thumb_rel item([^"]*)">.*?'
        r'<a href="https://91rb\.com/videos/([^"]+)" title="([^"]+)".*?'
        r'data-original="([^"]+)".*?'
        r'<div class="views">.*?([\d\.,Kk]+)</div>.*?'
        r'<div class="time">.*?([\d:]+)</div>',
        re.S)

    _BLOCKED = ('偷拍', '厕拍', '偷窥', '针孔')

    def _parse_list(self, html):
        out, seen = [], set()
        for m in self._ITEM.finditer(html):
            cls, path, title, pic, views, dur = m.groups()
            # VIP 片：class 含 private，跳过，不破 VIP
            if 'private' in (cls or '') or 'VIP' in (cls or ''):
                continue
            if any(k in (title or '') for k in self._BLOCKED):
                continue
            path = path.strip().rstrip('/')
            if path in seen:
                continue
            seen.add(path)
            title = self._clean(title)
            if not title:
                continue
            remarks = ' · '.join(x for x in
                                 [self._clean(views), self._clean(dur), 'HD']
                                 if x)
            out.append({'vod_id': path, 'vod_name': title,
                        'vod_pic': pic or '',
                        'vod_remarks': remarks})
        return out

    # ── 首页 / 分类 ───────────────────────────────────────────
    def homeContent(self, filter):
        return {'class': [{'type_id': t, 'type_name': n}
                          for t, n, _p in self.CLASSES]}

    def homeVideoContent(self):
        html, _u = self._http(self.HOST + '/')
        return {'list': self._parse_list(html)}

    @staticmethod
    def _list_url(path, pg):
        if pg <= 1:
            return 'https://91rb.com' + path
        return 'https://91rb.com' + path.rstrip('/') + '/%d/' % pg

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        path = self._PATH.get(tid)
        if not path:
            return {'list': [], 'page': pg, 'pagecount': 1,
                    'limit': 90, 'total': 0}
        html, _u = self._http(self._list_url(path, pg))
        return {'list': self._parse_list(html), 'page': pg,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ── 详情 ──────────────────────────────────────────────────
    _SOURCE = re.compile(
        r'<source src="([^"]+\.m3u8[^"]*)"[^>]*label="([^"]*)"', re.S)

    def _sources(self, html):
        out = []
        for src, label in self._SOURCE.findall(html):
            label = self._clean(label) or '原画'
            out.append((label, src))
        return out

    def _detail_url(self, path):
        return self.HOST + '/videos/' + path.strip('/') + '/'

    def detailContent(self, ids):
        sid = str(ids[0]) if ids else ''
        path = sid.split(':', 1)[1] if sid.startswith('video:') else sid
        url = self._detail_url(path)
        html, _u = self._http(url)
        title = ''
        m = re.search(r'property="og:title" content="([^"]+)"', html)
        if m:
            title = self._clean(m.group(1))
        if not title:
            m = re.search(r'<title>([^<]+)</title>', html)
            title = self._clean(m.group(1)).rsplit(' - 91热爆', 1)[0] if m else path
        pic = ''
        m = re.search(r'property="og:image" content="([^"]+)"', html)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r"poster:'([^']+)'", html)
            pic = m.group(1) if m else ''
        dur = ''
        m = re.search(r'duration" content="(\d+)"', html)
        if m:
            dur = self._fmt_dur(m.group(1))
        tags = [self._clean(t) for t in
                re.findall(r'href="/tags/[^"]+"[^>]*>([^<]+)</a>', html)]
        tags = [t for t in dict.fromkeys(tags) if t][:12]
        sources = self._sources(html)
        play_from, play_url = [], []
        remarks = dur
        if sources:
            eps = '#'.join('%s$play@@%s@@%d' % (label, path, i)
                           for i, (label, _src) in enumerate(sources))
            play_from.append('91RB')
            play_url.append(eps)
            remarks = ' · '.join(x for x in [dur, '%d 档画质' % len(sources)] if x)
        else:
            # 无 <source>：VIP 专享，需登录，不绕过
            remarks = ' · '.join(x for x in [dur, 'VIP专享'] if x)
        return {'list': [{'vod_id': path, 'vod_name': title or path,
                          'vod_pic': pic, 'type_name': '视频',
                          'vod_remarks': remarks,
                          'vod_content': '、'.join(tags),
                          'vod_play_from': '$$$'.join(play_from),
                          'vod_play_url': '$$$'.join(play_url)}]}

    # ── 搜索 ──────────────────────────────────────────────────
    def searchContent(self, key, quick, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        key = (key or '').strip()
        q = urllib.parse.urlencode({'q': key})
        url = self.HOST + '/search/?' + q
        if pg > 1:
            url += '&page=%d' % pg
        html, _u = self._http(url)
        return {'list': self._parse_list(html), 'page': pg,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ── 播放 ──────────────────────────────────────────────────
    def playerContent(self, flag, id, vipFlags):
        sid = str(id or '')
        m = re.match(r'play@@(.+)@@(\d+)$', sid)
        if m:
            path, idx = m.group(1), int(m.group(2))
            html, _u = self._http(self._detail_url(path))
            sources = self._sources(html)
            if 0 <= idx < len(sources):
                return {'parse': 0, 'url': sources[idx][1],
                        'header': {'User-Agent': self.UA,
                                   'Referer': self._detail_url(path)}}
            return {'parse': 0, 'url': ''}
        if sid.startswith('video:'):
            path = sid.split(':', 1)[1]
            html, _u = self._http(self._detail_url(path))
            sources = self._sources(html)
            if sources:
                return {'parse': 0, 'url': sources[0][1],
                        'header': {'User-Agent': self.UA,
                                   'Referer': self._detail_url(path)}}
        return {'parse': 0, 'url': ''}

    def isVideoFormat(self, url):
        return isinstance(url, str) and url.startswith('http') and (
            '.m3u8' in url or '.mp4' in url)

    def manualVideoCheck(self):
        return False
