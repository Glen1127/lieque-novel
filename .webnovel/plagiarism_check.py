#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《裂隙》正文与道诡异仙原文的雷同检测（抄袭守卫）

背景：ch31-46 曾被直接复制《道诡异仙》原书同号章节正文（49-91% 字符重合），
只替换了人名与少量词。此脚本把该检测固化为常规关卡，
任何写作流程结束后都必须跑一遍。

判定：
  红线  重合率 >= 35% 或最长连续重合 >= 40 字  -> BLOCK（必须重写）
  警戒  重合率 >= 15% 或最长连续重合 >= 20 字  -> WARN（必须人工确认）
  通过  其余

用法：
  python3 .webnovel/plagiarism_check.py            # 全量
  python3 .webnovel/plagiarism_check.py 30 46      # 指定章范围
  python3 .webnovel/plagiarism_check.py --json
"""
import os, re, sys, json, difflib

ROOT = '/Users/glenx/Documents/裂隙'
BOOK = '/Users/glenx/Downloads/道诡异仙 作者：狐尾的笔.txt'
BODY = os.path.join(ROOT, '正文')

# 人名/专名替换对：这些词不同不算雷同，检测时先归一
NAME_MAP = [
    ('李火旺', '主角'), ('沈念', '主角'),
    ('白灵淼', '女主'), ('白赛', '科员'), ('记录员', '女主'),
    ('丹阳子', '档案管理员'), ('游老爷', '聆听者'),
    ('吕状元', '顾长风'), ('赵五', '同事A'), ('杨娜', '小陶'),
    ('正坤', '老周'), ('赵乐蓓', '沈敏'), ('孙宝禄', '向导'),
    ('姜英子', '双面人'), ('静心师太', '庵主'), ('春小满', '年轻回声'),
    ('腊月十八', '守庙人'), ('金山找', '打更人'), ('高志坚', '审查员'),
    ('王韦', '不确定者'), ('彭龙腾', '深层守卫'), ('诸葛渊', '真相者'),
    ('吕秀才', '戏班成员'), ('何信', '同事B'), ('韩符', '畸形回声'),
    ('坐忘道', '伪装者'), ('心素', '传递者'), ('巴虺', '碾磨机制'),
    ('玉佩', '橙石'), ('糖块', '罐子'), ('黑太岁', '蛰晶'), ('道铃', '清音石'),
    ('建邺', '临川镇'), ('三山市', '临江市'), ('西京城', '西关城'),
    ('正德寺', '云台寺'), ('安慈庵', '苦竹庵'), ('十字寺', '十字石庙'),
    ('恒华山', '断云岭'), ('牛心村', '空心坳'), ('钱家村', '铜锣村'),
    ('大齐', '北燕'), ('大梁', '南楚'), ('四齐', '西戎'), ('后蜀', '北漠'),
    ('监天司', '名单系统'), ('司天监', '名单系统'), ('袄景教', '野路子信众'),
    ('跳大神', '民俗香头戏'), ('出马弟子', '民俗香头戏'), ('仙家', '保家仙'),
    ('二神', '替身少年'), ('喜神', '喜神者'), ('大千录', '档案检索权'),
    ('火袄真经', '怜悯'), ('兵家', '马帮武装'), ('十二福', '十二孔名单'),
    ('大润血丹', '阳寿符'), ('小润血丹', '遗愿签'), ('五里岗', '五里铺'),
    ('溶洞', '回声溶洞'), ('手叁', '三先生'), ('元二', '老二'),
    ('侯老二', '沈二'), ('侯文', '沈立'), ('连知北', '林知北'),
]
PUNCT = re.compile(r'[\s\n\r"“”，。、！？：；…—·()（）《》\[\]【】〈〉「」『』]')


def norm(s: str) -> str:
    s = PUNCT.sub('', s)
    for a, b in NAME_MAP:
        s = s.replace(a, b)
    return s


def ngrams(s: str, n: int = 12):
    """字符 n-gram 集合，用于快速预筛候选章"""
    return {s[i:i + n] for i in range(0, max(0, len(s) - n), 3)}


def quick_candidates(t: str, book_grams: dict, top: int = 12, min_shared: int = 6):
    """按 n-gram 重叠数给原书各章打分，只返回最可能的 top 章"""
    g = ngrams(t)
    if not g:
        return []
    scored = []
    for j, bg in book_grams.items():
        shared = len(g & bg)
        if shared >= min_shared:
            scored.append((shared, j))
    scored.sort(reverse=True)
    return [j for _, j in scored[:top]]


def load_book():
    if not os.path.exists(BOOK):
        return {}
    dq = open(BOOK, encoding='utf-8', errors='ignore').read()
    parts = re.split(r'\n第(\d+)章\s*([^\n]*)\n', dq)
    book = {}
    for i in range(1, len(parts), 3):
        try:
            book[int(parts[i])] = (parts[i + 1].strip(), parts[i + 2])
        except (ValueError, IndexError):
            pass
    return book


def body_chapters():
    out = []
    for f in os.listdir(BODY):
        if not (f.startswith('第') and f.endswith('.md')):
            continue
        m = re.search(r'\d+', f)
        if m:
            out.append(int(m.group()))
    return sorted(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    as_json = '--json' in sys.argv
    book = load_book()
    if not book:
        print('未找到原书，无法检测：', BOOK)
        return 2
    chapters = body_chapters()
    if len(args) >= 2:
        chapters = [c for c in chapters if int(args[0]) <= c <= int(args[1])]
    elif len(args) == 1:
        chapters = [c for c in chapters if c == int(args[0])]

    rows, blocks = [], []
    # 预筛：构建原书各章的 n-gram 索引
    book_grams = {j: ngrams(norm(b)) for j, (_bt, b) in book.items()}
    for c in chapters:
        fn = os.path.join(BODY, f'第{c}章.md')
        if not os.path.exists(fn):
            continue
        raw = open(fn, encoding='utf-8').read()
        title_m = re.match(r'#\s*第[0-9一二三四五六七八九十百零]+章\s*(.+)', raw)
        t = norm(re.sub(r'^#.*$', '', raw, flags=re.M))
        if not t:
            continue
        # 快速预筛出候选原章（Top 15），只在候选上做精确比对
        cands = quick_candidates(t, book_grams, top=15)
        if not cands:
            cands = list(book.keys())[:1]  # 兜底：至少比一章
        best = (0, 0, None, 0)
        for j in cands:
            _btitle, bbody = book[j]
            b = norm(bbody)
            if not b:
                continue
            sm = difflib.SequenceMatcher(None, t, b, autojunk=False)
            blocks_ = sm.get_matching_blocks()
            total = sum(x.size for x in blocks_)
            longest = max(x.size for x in blocks_)
            if total > best[0]:
                best = (total, longest, j, len(b))
        total, longest, j, blen = best
        rate = total / max(1, len(t))
        status = 'PASS'
        if rate >= 0.35 or longest >= 40:
            status = 'BLOCK'
        elif rate >= 0.15 or longest >= 20:
            status = 'WARN'
        rows.append({'ch': c, 'rate': round(rate * 100, 1),
                     'longest': longest, 'match_ch': j, 'status': status})

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0

    print('=' * 74)
    print('《裂隙》正文 × 道诡异仙 雷同检测（抄袭守卫）')
    print('=' * 74)
    print(f'{"章":<6}{"重合率":<10}{"最长连续":<12}{"对应原章":<10}{"判定"}')
    n_block = n_warn = 0
    for r in rows:
        mark = {'PASS': '', 'WARN': '  <<< 警戒', 'BLOCK': '  <<< BLOCK 必须重写'}[r['status']]
        if r['status'] == 'BLOCK':
            n_block += 1
        elif r['status'] == 'WARN':
            n_warn += 1
        print(f'ch{r["ch"]:<5}{str(r["rate"])+"%":<10}{r["longest"]:<12}'
              f'{("ch"+str(r["match_ch"])) if r["match_ch"] else "-":<10}{r["status"]}{mark}')
    print('-' * 74)
    print(f'检测 {len(rows)} 章：BLOCK {n_block} 章 / WARN {n_warn} 章 / PASS {len(rows)-n_block-n_warn} 章')
    if n_block:
        print('\nBLOCK 章必须在重写后才能进正文，禁止提交。')
    return 1 if n_block else 0


if __name__ == '__main__':
    sys.exit(main())
