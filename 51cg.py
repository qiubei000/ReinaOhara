# -*- coding: utf-8 -*-
"""
51吃瓜 (51cg1.com) - 吃瓜爆料资讯站，Typecho + Mirages 主题，无登录，无 Cloudflare
列表：首页 / (45 条)，翻页 /page/N/；分类 /category/<slug>/ (31 条/页)，翻页 /category/<slug>/N/
搜索 /search/<词>/，翻页 /search/<词>/N/
详情页 DPlayer 配置里有直链 m3u8： "video":{"url":"https://hls.ksfwni.cn/videos5/...m3u8?auth_key=..."}
m3u8 是 AES-128 加密（EXT-X-KEY），FongMi 播放器原生支持；auth_key 有时效，
所以 playerContent 每次现取详情页再返回，详情页给的链接只作展示
合集帖（瓜友求瓜合集）本身没视频，正文是 8 条 /archives/ 链接，详情页把它们做成选集
纯图文帖（吃瓜新闻等）没视频，详情页给正文图片 pics:// 图集 + 单张直链兜底
镜像多，HOSTS 按顺序回退：51cg1.com（海外）-> 51cg61.cc -> t0.51cg61.cc
"""
import re
import urllib.parse
import urllib.request

from base.spider import Spider as BaseSpider

# 诊断版：列表为空时返回一张诊断卡，点开看失败原因；修好后换回正常版
_DIAG = {'fetch': '', 'parse': ''}


class Spider(BaseSpider):
    HOSTS = ['https://51cg1.com', 'https://www.51cg61.cc', 'https://t0.51cg61.cc']
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')
    TIMEOUT = 20

    CATS = [
        ('home', '首页推荐', '/'),
        ('mrds', '每日大赛', '/category/mrds/'),
        ('whhj', '网黄合集', '/category/whhj/'),
        ('mrdg', '吃瓜榜单', '/category/mrdg/'),
        ('qghj', '瓜友点播', '/category/qghj/'),
        ('rdsj', '热门大瓜', '/category/rdsj/'),
        ('bkdg', '必看大瓜', '/category/bkdg/'),
        ('ysyl', '成人视频', '/category/ysyl/'),
        ('lldd', '伦理道德', '/category/lldd/'),
        ('gcjq', '国产视频', '/category/gcjq/'),
        ('thjx', '探花精选', '/category/thjx/'),
        ('xsxy', '学生校园', '/category/xsxy/'),
        ('whhl', '网红黑料', '/category/whhl/'),
        ('snsn', '骚男骚女', '/category/snsn/'),
        ('whmx', '明星爆料', '/category/whmx/'),
        ('hwcg', '海外吃瓜', '/category/hwcg/'),
        ('rrcg', '人人吃瓜', '/category/rrcg/'),
        ('ldcg', '领导干部', '/category/ldcg/'),
        ('jpll', '软萌甜妹', '/category/jpll/'),
        ('sjb', '竞技吃瓜', '/category/sjb/'),
        ('qubk', '吃瓜看戏', '/category/qubk/'),
        ('dcbq', '擦边撩骚', '/category/dcbq/'),
        ('zzs', '性爱技巧', '/category/zzs/'),
        ('cgxw', '吃瓜新闻', '/category/cgxw/'),
        ('51djc', '51原创短剧', '/category/51djc/'),
        ('yczq', '原创博主', '/category/yczq/'),
    ]

    def getName(self):
        return '51吃瓜'

    def init(self, extend):
        pass

    # ── HTTP ──────────────────────────────────────────────────
    def _http(self, path):
        """按 HOSTS 顺序回退；返回 (html, host)；失败返回 ('', HOSTS[0])"""
        if path.startswith('http'):
            urls = [path]
        else:
            urls = [h + path for h in self.HOSTS]
        notes = []
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': self.UA,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Referer': self.HOSTS[0] + '/',
                })
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as r:
                    if r.status == 200:
                        body = r.read().decode('utf-8', 'ignore')
                        host = re.match(r'(https?://[^/]+)', url).group(1)
                        notes.append('%s: HTTP 200, %d bytes' % (url, len(body)))
                        _DIAG['fetch'] = ' | '.join(notes)
                        return body, host
                    notes.append('%s: HTTP %s' % (url, r.status))
            except Exception as e:
                notes.append('%s: %s: %s' % (url, type(e).__name__, str(e)[:200]))
        _DIAG['fetch'] = ' | '.join(notes)
        return '', self.HOSTS[0]

    def _diag_item(self, where):
        txt = '位置: %s\n拉取: %s\n解析: %s' % (where, _DIAG.get('fetch', ''),
                                             _DIAG.get('parse', ''))
        _DIAG['text'] = txt
        short = _DIAG.get('fetch', '')[:60]
        return [{'vod_id': 'diag', 'vod_name': '诊断：列表为空（点开看原因）',
                 'vod_pic': '', 'vod_remarks': short}]

    @staticmethod
    def _clean(s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', ' ', s)
        s = (s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#58;', ':')
             .replace('&quot;', '"').replace('&#39;', "'").replace('&lt;', '<')
             .replace('&gt;', '>'))
        return re.sub(r'\s+', ' ', s).strip()

    # ── 列表 ──────────────────────────────────────────────────
    def _parse_list(self, html):
        items = []
        seen = set()
        arts = re.findall(r'<article.*?</article>', html, re.S)
        for art in arts:
            m = re.search(r'href="/archives/(\d+)/"', art)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            t = re.search(r'<h2[^>]*class="post-card-title"[^>]*>(.*?)</h2>', art, re.S)
            title = self._clean(t.group(1)) if t else ''
            if not title:
                continue
            pic = ''
            pm = re.search(r'x-bg-loader-url="([^"]+)"', art)
            if pm:
                pic = pm.group(1)
            if not pic:
                im = re.search(r'<img[^>]*src="([^"]+)"', art)
                if im:
                    pic = im.group(1)
            meta = re.search(r'<span itemprop="datePublished"[^>]*>([^<]+)</span>', art)
            date = meta.group(1).strip() if meta else ''
            cats = re.findall(r'<span>([^<]{2,12})</span>', art)
            remarks = ' · '.join([x for x in [date, ' '.join(cats[:2])] if x])
            if 'post-card-info--hot' in art:
                remarks = ('热门 · ' + remarks) if remarks else '热门'
            items.append({
                'vod_id': 'post:' + pid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        _DIAG['parse'] = 'html %d bytes, article %d 个, 解析出 %d 条' % (
            len(html), len(arts), len(items))
        return items

    def homeContent(self, filter):
        return {'class': [{'type_id': t, 'type_name': n} for t, n, _ in self.CATS]}

    def homeVideoContent(self):
        html, _ = self._http('/')
        items = self._parse_list(html)
        if not items:
            return {'list': self._diag_item('homeVideoContent /')}
        return {'list': items}

    def _list_path(self, tid, pg):
        for t, _, path in self.CATS:
            if t == tid:
                if pg <= 1:
                    return path
                if t == 'home':
                    return '/page/%d/' % pg
                return path.rstrip('/') + '/%d/' % pg
        return '/'

    def categoryContent(self, tid, pg, filter, extend):
        html, _ = self._http(self._list_path(tid, pg))
        items = self._parse_list(html)
        if not items:
            return {'list': self._diag_item('categoryContent %s p%d' % (tid, pg)),
                    'page': pg, 'pagecount': 1, 'limit': 90, 'total': 1}
        return {'list': items, 'page': pg,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    def searchContent(self, key, quick, pg):
        q = urllib.parse.quote(key)
        path = '/search/%s/' % q if pg <= 1 else '/search/%s/%d/' % (q, pg)
        html, _ = self._http(path)
        return {'list': self._parse_list(html), 'page': pg,
                'pagecount': 9999, 'limit': 90, 'total': 999999}

    # ── 详情 ──────────────────────────────────────────────────
    def _video_urls(self, html):
        """返回 (主 m3u8, h265 m3u8)，都没有返回 (None, None)"""
        main = None
        m = re.search(r'"video":\{"url":"([^"]+)"', html)
        if m:
            main = m.group(1).replace('\\/', '/')
        h265 = None
        m2 = re.search(r'"video_h265":\{"url":"([^"]+)"', html)
        if m2:
            h265 = m2.group(1).replace('\\/', '/')
        return main, h265

    def _post_body(self, html):
        """正文 div（平衡匹配），拿不到返回 ''"""
        m = re.search(r'<div[^>]*class="post-content[^"]*"[^>]*>', html)
        if not m:
            return ''
        return self._balanced_div(html, m.end())

    @staticmethod
    def _balanced_div(html, start):
        """从 start（某 div 的 > 之后）取到与之配对的 </div> 之前的内容"""
        depth = 1
        tag_re = re.compile(r'<(/?)div\b[^>]*>', re.I)
        for tm in tag_re.finditer(html, start):
            if tm.group(1) == '/':
                depth -= 1
                if depth == 0:
                    return html[start:tm.start()]
            else:
                depth += 1
        return html[start:]

    def _strip_ads(self, body):
        """去掉正文里的广告按钮区 txt-apps（平衡匹配，只删这一块）"""
        m = re.search(r'<div[^>]*class="txt-apps"[^>]*>', body)
        if not m:
            return body
        inner = self._balanced_div(body, m.end())
        return body[:m.start()] + body[m.end() + len(inner) + len('</div>'):]

    def _content_links(self, body, self_pid):
        """正文里的 /archives/ 链接（合集帖用），返回 [(id, 标题)]"""
        out = []
        seen = set()
        for u, t in re.findall(r'<a[^>]*href="/archives/(\d+)/"[^>]*>(.*?)</a>', body, re.S):
            if u in seen or u == self_pid:
                continue
            title = self._clean(t)
            title = title.replace('｜点击查看详情 →', '').replace('｜点击查看详情', '')
            title = title.replace('👉', '').replace('👈', '').replace(' 相关文章', '').strip()
            if len(title) < 10:
                continue
            if title.startswith(('上一篇', '下一篇')):
                continue
            seen.add(u)
            out.append((u, title))
        return out

    def _content_images(self, body):
        """正文图片（pic.ksfwni.cn），排除主题/插件图"""
        imgs = []
        seen = set()
        for src in re.findall(r'<img[^>]+src="(https://pic\.ksfwni\.cn[^"]+)"', body):
            if src in seen:
                continue
            seen.add(src)
            imgs.append(src)
        return imgs

    def detailContent(self, ids):
        if ids[0] == 'diag':
            return {'list': [{'vod_id': 'diag', 'vod_name': '诊断结果',
                              'vod_content': _DIAG.get('text', '无诊断信息'),
                              'vod_play_from': '诊断',
                              'vod_play_url': '说明$diagplay'}]}
        pid = ids[0].split(':', 1)[1] if ':' in ids[0] else ids[0]
        html, host = self._http('/archives/%s/' % pid)
        if not html:
            return {'list': []}
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        title = self._clean(m.group(1)).split(' | ')[0] if m else ''
        main, h265 = self._video_urls(html)
        body = self._strip_ads(self._post_body(html))
        links = self._content_links(body, pid) if not main else []
        imgs = self._content_images(body)
        # 正文简介：第一段文字
        content = self._clean(body)[:300]
        vod = {'vod_id': 'post:' + pid, 'vod_name': title, 'vod_content': content}
        pm = re.search(r'x-bg-loader-url="([^"]+)"', html)
        if pm:
            vod['vod_pic'] = pm.group(1)
        sources = []
        urls = []
        if main:
            sources.append('在线播放')
            eps = ['在线播放$play@@' + pid]
            if h265 and h265 != main:
                eps.append('H265$play@@%s@@h265' % pid)
            urls.append('#'.join(eps))
        if links:
            sources.append('合集选集')
            eps = ['%s$post:%s' % (t[:30], u) for u, t in links]
            urls.append('#'.join(eps))
        if imgs:
            sources.append('图片')
            chunks = [imgs[i:i + 20] for i in range(0, len(imgs), 20)]
            eps = ['图集%d$pics://%s' % (i + 1, '&&'.join(c)) for i, c in enumerate(chunks)]
            urls.append('#'.join(eps))
            sources.append('单张')
            urls.append('#'.join(['图%d$%s' % (i + 1, u) for i, u in enumerate(imgs)]))
        if not sources:
            sources.append('正文')
            urls.append('全文$play@@' + pid)
        vod['vod_play_from'] = '$$$'.join(sources)
        vod['vod_play_url'] = '$$$'.join(urls)
        return {'list': [vod]}

    # ── 播放 ──────────────────────────────────────────────────
    def playerContent(self, flag, id, vipFlags):
        if id == 'diagplay':
            return {'parse': 0, 'url': '', 'header': {}}
        pid = id
        h265 = False
        if id.startswith('play@@'):
            parts = id.split('@@')
            pid = parts[1]
            h265 = len(parts) > 2 and parts[2] == 'h265'
        elif id.startswith('post:'):
            pid = id.split(':', 1)[1]
        html, host = self._http('/archives/%s/' % pid)
        main, h265_url = self._video_urls(html)
        url = h265_url if (h265 and h265_url) else main
        if not url:
            return {'parse': 0, 'url': '', 'header': {}}
        return {'parse': 0, 'url': url,
                'header': {'User-Agent': self.UA, 'Referer': host + '/'}}

    def isVideoFormat(self, url):
        u = url.lower()
        return (u.endswith('.m3u8') or u.endswith('.mp4') or u.endswith('.mkv')
                or u.endswith('.ts') or u.endswith('.jpg') or u.endswith('.jpeg')
                or u.endswith('.png') or u.endswith('.webp') or u.endswith('.gif')
                or u.startswith('pics://'))

    def manualVideoCheck(self):
        return False
