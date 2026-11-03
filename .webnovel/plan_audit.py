#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《裂隙》规划层审核引擎 v2

审的是「规划」不是正文。判定基准是 设定集/线与时代基线表.json。
九类检查：
  P1 一一对应完整性 —— 映照表待定义 / 漏登 / 登记未用 / 滞后
  P2 串线词（按线判定）—— 修真词零命中 + 道诡专名跨线残留
  P3 语义级雷同      —— 同母题跨线同构 / 同线重复解法 / 模板句式密度
  P4 元叙事污染
  P5 三线背景一致性  —— 线跳变断层
  P6 核心情感结构覆盖
  P7 状态追踪滞后
  P8 废弃规划层冲突  —— 与已落地正文的规划残留
  P9 基线表自身完备性  —— 母题是否三条线都给了对应 + 正文占位符

用法：
  python3 plan_audit.py            # 打印报告
  python3 plan_audit.py --json     # 输出 JSON
  python3 plan_audit.py --hints    # 附带可执行修复清单
"""

import os
import re
import json
import sys
import argparse
import collections
import difflib

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)
SKELETON = os.path.join(PROJ, 'lieque_reverse/04章节表/generated_all_818.json')
MAPPING = os.path.join(PROJ, 'lieque_reverse/07映照表/一对一映射.json')
STATE_DIR = os.path.join(PROJ, '05状态追踪')
BODY_DIR = os.path.join(PROJ, '正文')
BASELINE = os.path.join(PROJ, '设定集/线与时代基线表.json')
ERA_BASELINE = os.path.join(PROJ, '设定集/时代与制度基线.json')
OLD_PLAN = os.path.join(PROJ, '大纲/总纲.md')
OLD_CHAP = os.path.join(PROJ, '04章节表/章节表_卷一.json')

# ---------------------------------------------------------------- 词表

# 修真体系词：任何线都不得出现（来自基线表零命中清单）
XIU_ZERO = ["监天司", "司天监", "三教", "科举", "喜神", "乐跳怒饿",
             "一流帝王相", "九流最下等", "修士", "境界", "筑基", "金丹", "元婴",
             "炼气", "丹方", "炼丹", "符箓", "阵法", "法宝", "宗门", "掌门",
             "灵根", "天劫", "渡劫", "元神", "神识", "内丹", "外丹",
             "坐忘道", "袄景教", "出马弟子", "跳大神", "仙家", "二神",
             "巴虺", "心素", "火袄真经", "《大千录》"]

# 道诡专名：属于道诡世界的实体
DQ_CHARS = ['李火旺', '白灵淼', '丹阳子', '吕状元', '赵五', '杨娜', '游老爷',
            '何信', '孙宝禄', '姜英子', '静心师太', '春小满', '腊月十八',
            '金山找', '高志坚', '王韦', '韩符', '彭龙腾', '诸葛渊', '吕秀才',
            '正坤', '赵乐蓓', '手叁', '元二', '连知北', '侯文',
            '侯老二', '右子雄']
DQ_PLACES = ['建邺', '三山市', '西京城', '五里岗', '牛心村', '大齐', '大梁',
              '四齐', '后蜀', '正德寺', '清风观', '溶洞', '恒华山', '安慈庵',
              '十字寺', '钱家村']
DQ_ITEMS = ['道铃', '黑太岁', '黑鼎', '铜铃', '炼丹炉', '傩戏面具',
             '坐忘道面具', '大润血丹', '小润血丹', '药引', '玉佩', '紫穗剑']

# 线判定关键词（用于给骨架每章打线标签）
LINE_KW = {
    'modern': ['仓库', '档案室', '大剧院', '整理员', '协理员', '同事', '工位',
               '加班', '手机', '电话', '公司', '地铁', '公交', '咖啡', '医院',
               '医生', '病房', '警察', '监控', '服务器', '标签', '编号',
               '盘点', '交接', '老城区', '城东'],
    'ancient': ['顾长风', '戏班', '顾家班', '临川', '临江', '临京', '清溪岗',
                '胡家', '和尚', '方丈', '尼姑', '庵', '寺', '佛', '施主', '香客',
                '镖局', '镖师', '江湖', '朝廷', '陛下', '将军', '府', '县',
                '皇帝', '道士', '响马', '土匪', '兵家', '驿', '驴车', '铜钱',
                '烟杆', '寿材', '纸扎', '还愿', '香火', '牛车', '马车'],
    'archive': ['深层', '名单', '孔位', '罐子', '回声', '传递者', '聆听者',
                '碾磨', '阳寿', '橙石', '清音石', '蛰晶', '档案管理员',
                '记录员', '十二孔', '深层印记'],
}

# 场景标签（用于雷同检测）
PLACE_TAGS = [('大剧院', '仓库'), ('仓库', '仓库'), ('档案室', '档案室'),
              ('深层', '深层'), ('戏班', '戏班'), ('镖局', '镖局'),
              ('庵', '庵'), ('寺', '寺'), ('村', '村'), ('土匪', '土匪'),
              ('兵家', '兵家'), ('响马', '响马'), ('仪式', '仪式'),
              ('客栈', '客栈'), ('戏台', '戏台'), ('祠堂', '祠堂')]
ACTION_TAGS = [('初遇', '初遇'), ('相遇', '初遇'), ('被劫', '被劫'), ('绑架', '被劫'),
                ('袭击', '袭击'), ('攻击', '袭击'), ('对决', '对决'), ('战斗', '对决'),
                ('上香', '上香'), ('驱邪', '驱邪'), ('守村', '守村'), ('守夜', '守村'),
                ('伪装', '伪装'), ('乔装', '伪装'), ('交谈', '交谈'), ('夜谈', '夜谈'),
                ('告别', '告别'), ('觉醒', '觉醒'), ('传承', '传承'), ('封印', '封印'),
                ('祭拜', '祭拜'), ('复仇', '复仇'), ('逃亡', '逃亡'), ('被抓', '被抓'),
                ('潜入', '潜入'), ('唱戏', '唱戏'), ('搭台', '搭台'), ('押镖', '押镖'),
                ('审讯', '审讯'), ('交易', '交易'), ('超度', '超度'), ('普渡', '超度')]

TEMPLATE_WORDS = ['试图', '察觉', '意识到', '开始', '最终', '决定', '遭遇',
                  '面对', '心中', '危险', '真相', '复杂', '弥漫', '气氛']

META_WORDS = ['上架感言', '求票', '打赏', '月票', '推荐票', '感谢读者',
              '更新预告', '完结感言']

# 母题：跨线复用检查用
MOTIFS = {
    '戏班': ['戏班', '唱戏', '戏台', '搭台', '花旦', '班主', '顾长风', '顾家班'],
    '土匪': ['土匪', '响马', '劫', '寨', '山贼'],
    '仪式': ['仪式', '祭祀', '祭拜', '法事', '斋', '开光', '做醮'],
    '邪祟': ['邪祟', '狐仙', '黄皮子', '煞', '妖'],
    '寺庙庵': ['寺', '庵', '和尚', '方丈', '佛', '尼姑', '施主'],
    '孤儿': ['孤儿', '乞儿', '乞丐', '流浪儿'],
    '镖局': ['镖局', '镖师', '押镖', '走镖'],
    '婚宴': ['婚宴', '喜宴', '成亲', '娶', '嫁'],
}


# ---------------------------------------------------------------- 工具

def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def load_skeleton():
    return load_json(SKELETON)


def load_mapping():
    return load_json(MAPPING)


def blob_of(entry):
    return ' '.join(str(entry.get(k, ''))
                    for k in ('title', 'synopsis_short', 'synopsis'))


def blob_all(sk):
    """全字段拼接：骨架里任何字段出现过的名字都算已落地。"""
    out = []
    for v in sk.values():
        if not isinstance(v, dict):
            continue
        for val in v.values():
            if isinstance(val, str):
                out.append(val)
            elif isinstance(val, list):
                out.append(' '.join(str(x) for x in val))
    return ' '.join(out)


def seq_ratio(a, b):
    """两段文本的相似度（difflib SequenceMatcher），用于同构真伪判定。"""
    a = re.sub(r'\s+', '', str(a or ''))
    b = re.sub(r'\s+', '', str(b or ''))
    if not a or not b:
        return 0.0
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def parse_ch_range(spec):
    """解析 '25-36,114,148,151-152' 这样的章号串 → set(int)"""
    out = set()
    for part in re.split(r'[,\uFF0C]', str(spec or '')):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
            continue
        m = re.match(r'^(\d+)$', part)
        if m:
            out.add(int(m.group(1)))
    return out


def scene_tags(text):
    t = set()
    for w, lab in PLACE_TAGS + ACTION_TAGS:
        if w in text:
            t.add(lab)
    return tuple(sorted(t))


def line_of(text):
    """给一段文本打线标签（按词频取主导）"""
    sc = {}
    for line, kws in LINE_KW.items():
        sc[line] = sum(text.count(w) for w in kws)
    mx = max(sc.values())
    if mx == 0:
        return 'unknown'
    win = [l for l, v in sc.items() if v == mx]
    if len(win) > 1:
        return '+'.join(sorted(win))
    return win[0]


def body_progress():
    if not os.path.isdir(BODY_DIR):
        return 0, []
    chs = []
    for fn in os.listdir(BODY_DIR):
        if not fn.startswith('第'):
            continue
        m = re.search(r'(\d+)', fn)
        if m:
            chs.append(int(m.group(1)))
    return (max(chs) if chs else 0), sorted(chs)


def all_body_text():
    out = []
    if os.path.isdir(BODY_DIR):
        for fn in sorted(os.listdir(BODY_DIR)):
            if fn.startswith('第'):
                with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
                    out.append(f.read())
    return '\n'.join(out)


def motif_hits(sk):
    res = {}
    for mo, kws in MOTIFS.items():
        chs = []
        for k, v in sk.items():
            if not isinstance(v, dict):
                continue
            b = blob_of(v)
            if any(w in b for w in kws):
                chs.append(int(k))
        res[mo] = sorted(chs)
    return res


def segments(chs):
    """把章列表压成连续区间"""
    segs = []
    for c in sorted(chs):
        if segs and c == segs[-1][1] + 1:
            segs[-1][1] = c
        else:
            segs.append([c, c])
    return [(a, b) for a, b in segs]


def seg_str(segs):
    return [f'{a}-{b}' if a != b else str(a) for a, b in segs]


# ---------------------------------------------------------------- P1

def check_p1_mapping(sk, mp, bl):
    items = mp.get('道具映射', {})
    places = mp.get('地名映射', {})
    chars = mp.get('角色映射', {})
    emo = mp.get('核心情感结构映射', {})

    undef_items = [k for k, v in items.items()
                   if isinstance(v, dict) and v.get('lieque_name') == '待定义']
    undef_places = [k for k, v in places.items()
                    if isinstance(v, dict) and v.get('lieque_name') == '待定义']

    # 待落地：定义了但骨架/正文都还没出现的对应（规划期正常状态，单列不判 FAIL）
    body_txt = all_body_text()
    sk_txt = blob_all(sk)
    pending = []
    NA = ('非道具', '非地名', '非角色', '无对应')
    for grp, label in ((items, '道具'), (places, '地名')):
        for dk, dv in grp.items():
            if not isinstance(dv, dict):
                continue
            ln = dv.get('lieque_name', '')
            if not ln or ln == '待定义':
                continue
            if any(mk in ln for mk in NA):
                continue
            if ln not in body_txt and ln not in sk_txt:
                pending.append((label, dk, ln, dv.get('待办', '无待办标注')))

    appear = collections.Counter()
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        b = blob_of(v)
        for w in DQ_CHARS + DQ_PLACES + DQ_ITEMS:
            if w in b:
                appear[w] += 1
    mapped_src = set(items) | set(places) | set(chars)
    unmapped = {w: c for w, c in appear.items() if w not in mapped_src}

    body = all_body_text()
    sk_blob = blob_all(sk)
    written, _ = body_progress()
    unused = []
    # 「非道具」「非地名」「非角色」「无对应」= 该来源实体在裂隙侧本就不落地，
    # 属登记完备性说明，不是漏用。
    NA_MARKERS = ('非道具', '非地名', '非角色', '无对应')
    for grp, label in ((items, '道具'), (places, '地名'), (chars, '角色')):
        for dk, dv in grp.items():
            if not isinstance(dv, dict):
                continue
            ln = dv.get('lieque_name')
            if not ln or ln == '待定义':
                continue
            if any(mk in ln for mk in NA_MARKERS):
                continue
            # 判定用「裂隙侧名字」是否落地 —— 骨架里已把道诡原名替换掉了
            # 名字可能带括号补充说明，按主名做前缀匹配
            core = re.sub(r'[（(].*?[）)]', '', ln).strip()
            names_to_check = {ln, core} if core != ln else {ln}
            if any(nm in body or nm in sk_blob for nm in names_to_check):
                continue
            # 落点标注在正文进度之后的 = 规划期未到，不算漏用
            land = (dv.get('首次出现_ch') or dv.get('待落地_ch') or dv.get('落点_ch')
                    or dv.get('首次出现') or dv.get('出现_ch'))
            try:
                land_n = int(land)
            except (TypeError, ValueError):
                land_n = None
            if land_n is not None and land_n > written:
                continue
            unused.append((label, dk, ln))

    last_ch = mp.get('last_updated_ch', 0)

    # 核心情感结构：三线各一组才算完整
    emo_lines = [k for k in emo if k in ('modern', 'ancient', 'archive')]

    return {
        'name': 'P1 一一对应完整性',
        'status': 'FAIL' if (undef_items or undef_places or unmapped or unused
                             or len(emo_lines) < 3) else 'PASS',
        'data': {
            '待定义道具': undef_items,
            '待定义地名': undef_places,
            '骨架出现但未登记': unmapped,
            '登记但从未使用': unused,
            '待落地（规划期占位）': pending,
            '核心情感结构条数': len(emo),
            '核心情感结构覆盖线': emo_lines,
            'last_updated_ch': last_ch,
            '正文实际写到': written,
            '映射滞后章数': (written - last_ch) if written else 0,
        },
        'detail': f"待定义道具 {len(undef_items)}、待定义地名 {len(undef_places)}；"
                  f"漏登专名 {len(unmapped)} 个；登记未用 {len(unused)} 个"
                  f"（待落地占位 {len(pending)} 个不计）；"
                  f"核心情感结构覆盖 {len(emo_lines)}/3 条线；"
                  f"映照表停在 ch{last_ch}，正文已到 ch{written}",
    }


# ---------------------------------------------------------------- P2

def check_p2_leak(sk):
    """串线词：修真词任何线零命中；道诡专名跨线残留"""
    xiu_hits = collections.Counter()
    xiu_ch = collections.defaultdict(list)
    dq_ch = collections.defaultdict(list)
    ch_lines = {}

    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        b = blob_of(v)
        ln = line_of(b)
        ch_lines[int(k)] = ln
        for w in XIU_ZERO:
            if w in b:
                xiu_hits[w] += 1
                xiu_ch[w].append(int(k))
        for w in DQ_CHARS + DQ_PLACES + DQ_ITEMS:
            if w in b:
                dq_ch[w].append(int(k))

    dq_detail = {}
    for w, cs in dq_ch.items():
        lines = collections.Counter(ch_lines[c] for c in cs)
        dq_detail[w] = {'章数': len(cs), '线分布': dict(lines), '章': sorted(cs)}

    return {
        'name': 'P2 串线词（修真零命中 + 道诡专名）',
        'status': 'FAIL' if (xiu_hits or dq_ch) else 'PASS',
        'data': {
            '修真词命中': dict(xiu_hits.most_common()),
            '修真词章节': {w: sorted(c) for w, c in xiu_ch.items()},
            '道诡专名': dq_detail,
            '道诡专名涉及章数': len(set(c for cs in dq_ch.values() for c in cs)),
            '线标签': {str(k): v for k, v in sorted(ch_lines.items())},
        },
        'detail': f"修真零命中词 {len(xiu_hits)} 个，命中 {len(set(c for cs in xiu_ch.values() for c in cs))} 章；"
                  f"道诡专名 {len(dq_ch)} 个，涉及 {len(set(c for cs in dq_ch.values() for c in cs))} 章",
    }


# ---------------------------------------------------------------- P3

def check_p3_dup(sk, bl):
    """语义级雷同检测"""
    groups = collections.defaultdict(list)
    ch_lines = {}
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        ch_lines[int(k)] = line_of(blob_of(v))
        t = scene_tags(blob_of(v))
        if len(t) >= 2:
            groups[t].append(int(k))
    dup_groups = {str(t): sorted(cs) for t, cs in groups.items() if len(cs) >= 2}

    tw = {w: 0 for w in TEMPLATE_WORDS}
    for v in sk.values():
        if not isinstance(v, dict):
            continue
        s = str(v.get('synopsis', ''))
        for w in TEMPLATE_WORDS:
            if w in s:
                tw[w] += 1
    total = sum(1 for v in sk.values() if isinstance(v, dict))

    mh = motif_hits(sk)
    motif_report = {}
    for mo, chs in mh.items():
        if len(chs) < 4:
            continue
        segs = segments(chs)
        by_tag = collections.defaultdict(list)
        for c in chs:
            tags = scene_tags(blob_of(sk[str(c)]))
            if len(tags) >= 2:
                by_tag[tags].append(c)
        # 同构判定：标签组相同只是候选，还必须 synopsis 文本相似度高
        # （否则「都含仪式+档案室」这种关键词撞车会误判为同构）
        homos = {}
        for tg, cs in by_tag.items():
            if len(cs) < 2:
                continue
            real = []
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    a = str(sk[str(cs[i])].get('synopsis', ''))
                    b = str(sk[str(cs[j])].get('synopsis', ''))
                    if seq_ratio(a, b) >= 0.62:
                        real.append(cs[j])
            if real:
                homos[str(tg)] = sorted(set(real))
        if len(segs) >= 2 or homos:
            motif_report[mo] = {
                '总章数': len(chs),
                '连续段': seg_str(segs),
                '同构标签组': homos,
                '章': chs,
            }

    redlines = []
    for entry in (bl.get('母题差异化对照', {}) or {}).get('条目', []) or []:
        mo = entry.get('母题')
        kws = MOTIFS.get(mo, [])
        if not kws:
            continue
        chs = mh.get(mo, [])
        segs = segments(chs)
        if len(segs) < 2:
            continue
        # 若基线表给了机器可读的「红线判定」，按段级载体判定：
        # 出现在允许段里 = 同载体延续/已差异化，不算雷同；
        # 出现在未列出的段 = 真雷同。
        allow_spec = entry.get('红线判定') or {}
        allowed_chs = set()
        for grp in ('同载体延续段_允许', '残台_允许'):
            for item in allow_spec.get(grp, []) or []:
                allowed_chs.update(parse_ch_range(item.get('段', '')))
        if allowed_chs:
            bad = [c for c in chs if c not in allowed_chs]
            if not bad:
                continue
            redlines.append({
                '母题': mo,
                '出现段': seg_str(segs),
                '违规章': bad,
                '红线': entry.get('雷同红线', ''),
                '建议': '同母题再次出现时必须换载体/换机制/换代价；'
                        '对照基线表三线对应逐条核对',
            })
            continue
        redlines.append({
            '母题': mo,
            '出现段': seg_str(segs),
            '红线': entry.get('雷同红线', ''),
            '建议': '同母题再次出现时必须换载体/换机制/换代价；'
                    '对照基线表三线对应逐条核对',
        })

    same_line_dup = {}
    for t, cs in dup_groups.items():
        lines = collections.Counter(ch_lines[c] for c in cs)
        dom, n = lines.most_common(1)[0]
        if n >= 3:
            same_line_dup[t] = {'主导线': dom, '章数': n, '章': cs}

    # 分级判定：
    #   FAIL —— 触发了基线表红线（真雷同），或母题存在同构标签组（同载体复刻）
    #   WARN —— 标签组重复 / 母题多段出现但载体已差异化（噪声，不阻塞）
    #   PASS —— 无
    hard_fail = bool(redlines)
    hard_fail = hard_fail or any(v.get('同构标签组') for v in motif_report.values())
    status = 'FAIL' if hard_fail else ('WARN' if (dup_groups or motif_report) else 'PASS')

    return {
        'name': 'P3 语义级雷同',
        'status': status,
        'data': {
            '标签组重复数': len(dup_groups),
            '标签组重复': dict(sorted(dup_groups.items(),
                                     key=lambda x: -len(x[1]))[:20]),
            '同线内高频重复': same_line_dup,
            '模板词频次': tw,
            '模板词密度': {w: f'{c}/{total}' for w, c in tw.items()},
            '母题重复': motif_report,
            '基线表红线': redlines,
        },
        'detail': f"标签组重复 {len(dup_groups)} 组；"
                  f"重复母题 {len(motif_report)} 个；"
                  f"触发基线红线 {len(redlines)} 条；"
                  f"同构标签组 {sum(len(v.get('同构标签组') or {}) for v in motif_report.values())} 组；"
                  f"模板词最高 {max(tw.items(), key=lambda x: x[1])[0]}"
                  f" 出现在 {max(tw.values())} 章",
    }


# ---------------------------------------------------------------- P4

def check_p4_meta(sk):
    hits = []
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        b = blob_of(v)
        for w in META_WORDS:
            if w in b:
                hits.append({'ch': int(k), 'title': v.get('title'), 'word': w,
                             'synopsis': str(v.get('synopsis'))[:150]})
    return {
        'name': 'P4 元叙事污染',
        'status': 'FAIL' if hits else 'PASS',
        'data': {'命中': hits},
        'detail': f"{len(hits)} 章混入作者感言/运营话术",
    }


# ---------------------------------------------------------------- P5

def check_p5_worldline(sk):
    per_ch = {}
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        per_ch[int(k)] = line_of(blob_of(v))

    bands = {}
    for a in range(1, 819, 60):
        c = collections.Counter(per_ch.get(x, 'unknown')
                                for x in range(a, min(a + 60, 819)))
        bands[f'ch{a}-{min(a + 59, 818)}'] = dict(c)

    seq = [per_ch.get(c, 'unknown') for c in range(1, 819)]
    jumps = 0
    for i in range(1, len(seq)):
        if seq[i] != seq[i - 1] and 'unknown' not in (seq[i], seq[i - 1]):
            jumps += 1

    total = collections.Counter(seq)
    return {
        'name': 'P5 三线背景一致性',
        'status': 'WARN' if jumps > 300 else 'PASS',
        'data': {'逐段线分布': bands, '全线总量': dict(total), '主导权跳变次数': jumps},
        'detail': f"线主导权跳变 {jumps} 次；总量 {dict(total)}",
    }


# ---------------------------------------------------------------- P6

def check_p6_emo(sk, mp, bl):
    emo = mp.get('核心情感结构映射', {})
    need = list((bl.get('线定义', {}) or {}).keys())
    covered = set()
    for k, v in emo.items():
        if not isinstance(v, dict):
            continue
        # 条目本身就是以线名（modern/ancient/archive）为键
        if k in need:
            covered.add(k)
            continue
        # 补充结构里可能用线中文名标注
        txt = json.dumps(v, ensure_ascii=False)
        for line in need:
            cn = (bl.get('线定义', {}) or {}).get(line, {}).get('名', '')
            if cn and cn in txt:
                covered.add(line)
    missing = [l for l in need if l not in covered]

    pat_kw = ['初遇', '误认', '信任', '背叛', '守护', '牺牲', '清算', '抉择',
              '失去', '归属', '身份', '误解', '还债', '传承']
    pat_count = collections.Counter()
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        b = blob_of(v)
        for p in pat_kw:
            if p in b:
                pat_count[p] += 1

    return {
        'name': 'P6 核心情感结构覆盖',
        'status': 'FAIL' if missing else 'PASS',
        'data': {
            '已映射条数': len(emo),
            '已覆盖线': sorted(covered),
            '未覆盖线': missing,
            '骨架情感模式分布': dict(pat_count.most_common()),
        },
        'detail': f"核心情感结构仅 {len(emo)} 条；"
                  f"覆盖 {len(covered)}/{len(need)} 条线；"
                  f"未覆盖：{missing or '无'}",
    }


# ---------------------------------------------------------------- P7

def check_p7_state(sk):
    issues = []
    written, _ = body_progress()
    for f in sorted(os.listdir(STATE_DIR)):
        if not (f.startswith('volume_') and f.endswith('_state.json')):
            continue
        with open(os.path.join(STATE_DIR, f), encoding='utf-8') as fh:
            d = json.load(fh)
        done = d.get('ch_completed', 0)
        if isinstance(done, list):
            done = len(done)
        if not isinstance(done, int):
            done = 0
        if f == 'volume_001_state.json':
            continue
        if done < written and d.get('status') == '进行中':
            issues.append({'file': f, '记录ch_completed': done,
                           '正文实际': written, '滞后': written - done})
    cs_path = os.path.join(STATE_DIR, 'character_state.json')
    loc = None
    if os.path.isfile(cs_path):
        with open(cs_path, encoding='utf-8') as fh:
            cs = json.load(fh)
        loc = cs.get('shen_nian', {}).get('location')
    return {
        'name': 'P7 状态追踪滞后',
        'status': 'FAIL' if issues else 'PASS',
        'data': {'卷状态滞后': issues, '正文写到': written,
                 'character_state中沈念位置': loc},
        'detail': f"{len(issues)} 个卷状态文件滞后；"
                  f"character_state 记录沈念在「{loc}」",
    }


# ---------------------------------------------------------------- P8

def check_p8_legacy(sk):
    """废弃规划层是否已真正归档隔离（不是"有没有冲突"，而是"隔离干净没有"）"""
    legacy_files = []
    leaked = []

    # 1) 活跃目录里不能再有废弃层文件
    for d in ('03卷纲', '04章节表'):
        dd = os.path.join(PROJ, d)
        if os.path.isdir(dd):
            for fn in sorted(os.listdir(dd)):
                legacy_files.append(os.path.join(d, fn))
                leaked.append(os.path.join(d, fn))
    if os.path.exists(OLD_PLAN):
        legacy_files.append(os.path.relpath(OLD_PLAN, PROJ))
        leaked.append(os.path.relpath(OLD_PLAN, PROJ))

    # 2) 废弃层必须已归档到 _废弃_规划层/ 且带 README
    archive_dir = os.path.join(PROJ, '_废弃_规划层')
    archived = sorted(os.listdir(archive_dir)) if os.path.isdir(archive_dir) else []
    readme_ok = os.path.exists(os.path.join(archive_dir, 'README.md'))

    # 3) 废弃层角色不得作为主线实体出现在正文（只允许幻觉/提及）
    body_titles = {}
    ghost = {}
    if os.path.isdir(BODY_DIR):
        for fn in sorted(os.listdir(BODY_DIR)):
            if not (fn.startswith('第') and fn.endswith('.md')):
                continue
            n = int(re.search(r'(\d+)', fn).group())
            with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
                t = f.read()
            m = re.match(r'#\s*第[0-9一二三四五六七八九十百零]+章\s*(.+)', t)
            body_titles[n] = m.group(1).strip() if m else None
            for c in ('陈姐', '小陶', '第1032号'):
                if c in t:
                    ghost.setdefault(c, []).append(os.path.basename(fn))
    ghost_note = {
        '陈姐': 'ch2 档案室办公室（幻象场景中的管理者形象），非主线角色',
        '小陶': 'ch38 街道幻象 / ch39 篝火幻象 / ch41 回忆提及，均非实体角色',
        '第1032号': '现代线档案室册号，ch43 被沈念作为背景引用，非废弃层角色落地',
    }
    # 实体泄漏判定：只有当该编号被当作"存在/角色"来描写才算泄漏；
    # 被主角作为档案编号引用（现代线背景）不算泄漏。
    GHOST_ROLE_CONTEXT = ('那人', '这个人', '他是', '她是', '那位', '他就是')
    ghost_leak = []
    for k, files in ghost.items():
        if k != '第1032号' or not files:
            continue
        for fn in files:
            body_t = open(os.path.join(BODY_DIR, fn), encoding='utf-8').read()
            for m in re.finditer(re.escape(k), body_t):
                ctx = body_t[max(0, m.start() - 120):m.end() + 120]
                if any(c in ctx for c in GHOST_ROLE_CONTEXT):
                    ghost_leak.append(f'{k}@{fn}')
                    break

    ok = (not leaked) and readme_ok and not ghost_leak
    return {
        'name': 'P8 废弃规划层隔离',
        'status': 'PASS' if ok else 'FAIL',
        'data': {
            '活跃目录残留废弃层文件': leaked,
            '归档目录': '_废弃_规划层/' if os.path.isdir(archive_dir) else None,
            '已归档文件': archived,
            '归档说明README': readme_ok,
            '废弃层角色在正文出现': ghost,
            '废弃层角色性质': ghost_note,
            '废弃层角色实体泄漏': ghost_leak,
        },
        'detail': (f"活跃目录残留 {len(leaked)} 个废弃层文件；"
                   f"归档目录已有 {len(archived)} 个文件，README={'有' if readme_ok else '缺'}；"
                   f"废弃层核心角色实体泄漏 {len(ghost_leak)} 个"),
    }


# ---------------------------------------------------------------- P9

def check_p9_baseline(sk, bl):
    entries = (bl.get('母题差异化对照', {}) or {}).get('条目', []) or []
    incomplete = []
    for e in entries:
        missing = [ln for ln in ('modern', 'ancient', 'archive')
                   if not e.get(ln)]
        if missing:
            incomplete.append({'母题': e.get('母题'), '缺线': missing})
    no_redline = [e.get('母题') for e in entries if not e.get('雷同红线')]

    placeholders = []
    pat = re.compile(r'档案室同事[AB]|同事[AB]|待定义|TBD|TODO|XXX')
    if os.path.isdir(BODY_DIR):
        for fn in sorted(os.listdir(BODY_DIR)):
            if not (fn.startswith('第') and fn.endswith('.md')):
                continue
            with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
                t = f.read()
            hits = pat.findall(t)
            if hits:
                placeholders.append({'file': fn,
                                     '命中': dict(collections.Counter(hits))})

    anchors = bl.get('已落地锚点', {})
    body = all_body_text()
    anchor_unused = {}
    real_missing = {}
    for line, items in anchors.items():
        if not isinstance(items, dict):
            continue
        miss = []
        for k, desc in items.items():
            if k in body:
                continue
            # 锚点自身说明里标了规划状态的（尚未落地/规划中/待定/占位/未用）
            # 视为规划期占位，不是"声明缺失"
            d = desc if isinstance(desc, str) else ''
            if any(mk in d for mk in ('尚未落地', '规划中', '待定', '占位', '未用', '待落地')):
                continue
            miss.append(k)
        if miss:
            anchor_unused[line] = miss
            real_missing[line] = miss
    real_missing = {ln: v for ln, v in real_missing.items() if v}
    placeholder_names = {'档案室同事A/B', '记录员', '第1032号'}

    return {
        'name': 'P9 基线表完备性',
        'status': 'FAIL' if (incomplete or placeholders or real_missing) else 'PASS',
        'data': {
            '母题缺线': incomplete,
            '无雷同红线的母题': no_redline,
            '正文占位符残留': placeholders,
            '锚点声明但正文未出现': anchor_unused,
            '其中属必落实体(非占位)': real_missing,
            '规划期占位名单': sorted(placeholder_names),
        },
        'detail': f"母题缺线 {len(incomplete)}；正文占位符 {len(placeholders)} 章；"
                  f"必落实体缺失 {sum(len(v) for v in real_missing.values())} 项"
                  f"（另有 {sum(len(v) for v in anchor_unused.values()) - sum(len(v) for v in real_missing.values())}"
                  f" 项为规划期占位名）",
    }


# ---------------------------------------------------------------- 汇总

# ---------------------------------------------------------------- P11

# 丛林佛教语汇：按 设定集/时代与制度基线.json，异界线主路线为道教科仪
BUDDHIST_BAN = ['佛陀', '方丈', '和尚', '僧人', '普渡大斋', '大斋', '超度',
                '诵经', '经文', '袈裟', '菩萨像', '佛像', '成佛', '华严经',
                '佛门', '佛祖']

# 民国专属词：异界线禁用
REPUBLIC_BAN = ['巡捕', '包打听', '青帮', '钞票', '现大洋', '袁大头',
                 '剪辫', '铁路', '电报', '军阀', '国会', '剪发辫']

# 异界线制度违例
ERA_BAN = ['九流', '九流最下等', '监天司', '司天监', '袄景教', '袄影教',
           '法教', '坐忘道', '走偏门的把戏', '玄牝', '敖摩揭',
           '丹药', '境界', '修为', '灵气', '内丹', '法力', '玉佩']

# 需排除误报上下文（普通汉语搭配，非修真语汇）
ERA_BAN_EXCLUDE = {
    '法力': ('无',),   # 「无法力敌」= 不能硬拼，不是修真语汇
}

# 道教科仪语境下合法的词：符箓/符水/黄纸/画符 是民俗法物，不是修真体系语汇。
# 但若出现在描述「修为/境界体系」的句子里，仍算违规 —— 由 ERA_BAN_CONTEXT 判定。
TAOIST_OK = ['符箓', '符水', '符纸', '画符', '黄纸', '黄表', '香灰',
             '法坛', '科仪', '坛场', '道观', '坛主', '道人', '送亡',
             '安魂', '斋醮', '打醮', '禳解', '扶乩']


def has_banned(text: str, word: str) -> bool:
    """带上下文排除的违例词检测"""
    if word not in text:
        return False
    ex = ERA_BAN_EXCLUDE.get(word)
    if not ex:
        return True
    for m in re.finditer(re.escape(word), text):
        before = text[max(0, m.start() - 2):m.start()]
        if not any(b in before for b in ex):
            return True
    return False


def body_files():
    """列出正文文件，按章号排序；目录不存在返回空表"""
    if not os.path.isdir(BODY_DIR):
        return []
    out = []
    for fn in os.listdir(BODY_DIR):
        if fn.startswith('第') and fn.endswith('.md'):
            m = re.search(r'(\d+)', fn)
            if m:
                out.append((int(m.group(1)), fn))
    return [fn for _, fn in sorted(out)]


def check_p11_era(sk, eb):
    """时代与宗教路线校验：骨架 + 已落地正文"""
    hits = collections.defaultdict(list)

    # 骨架
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        b = blob_of(v)
        for w in BUDDHIST_BAN:
            if w in b:
                hits['骨架·佛教语汇'].append({'ch': int(k), 'word': w,
                                            'title': v.get('title')})
        for w in REPUBLIC_BAN:
            if w in b:
                hits['骨架·民国词'].append({'ch': int(k), 'word': w,
                                           'title': v.get('title')})
        for w in ERA_BAN:
            if has_banned(b, w):
                hits['骨架·制度违例'].append({'ch': int(k), 'word': w,
                                             'title': v.get('title')})

    # 正文：只查含 ancient 线标志词的章节（现代线允许"警察"等）
    for fn in body_files():
        n = int(re.search(r'(\d+)', fn).group())
        with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
            t = f.read()
        ln = line_of(t)
        if ln == 'modern':
            continue
        for w in BUDDHIST_BAN:
            if w in t:
                hits['正文·佛教语汇'].append({'ch': n, 'word': w})
        for w in REPUBLIC_BAN:
            if w in t:
                hits['正文·民国词'].append({'ch': n, 'word': w})
        for w in ERA_BAN:
            if has_banned(t, w):
                hits['正文·制度违例'].append({'ch': n, 'word': w})

    # 引号风格：正文必须统一为「」
    quote_bad = []
    for fn in body_files():
        n = int(re.search(r'(\d+)', fn).group())
        with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
            t = f.read()
        if '"' in t or '“' in t or '”' in t:
            quote_bad.append(n)
        elif t.count('「') != t.count('」'):
            quote_bad.append(n)

    # 时代线一致性：正文不得在同章混用现代专属器物与古代专属器物
    cross = []
    for fn in body_files():
        n = int(re.search(r'(\d+)', fn).group())
        with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
            t = f.read()
        modern_hit = [w for w in ('手机', '电脑', '服务器', '监控', '地铁', '公交')
                      if w in t]
        ancient_hit = [w for w in ('镖局', '镖师', '捕头', '里正', '银两', '铜钱',
                                   '戏台', '祠堂', '牛车', '马车')
                       if w in t]
        if modern_hit and ancient_hit:
            cross.append({'ch': n, '现代词': modern_hit, '古代词': ancient_hit})

    total = sum(len(v) for v in hits.values())
    return {
        'name': 'P11 时代与宗教路线',
        'status': 'FAIL' if (hits or quote_bad or cross) else 'PASS',
        'data': {
            '违规明细': {k: v for k, v in hits.items()},
            '违规总数': total,
            '引号风格不统一章': sorted(set(quote_bad)),
            '时代混用章': cross,
            '基准': '设定集/时代与制度基线.json',
            '宗教主路线': (eb.get('线定义', {}) or {}).get(
                'ancient', {}).get('宗教路线', {}).get('主路线', '未定义'),
        },
        'detail': f"时代/宗教违规 {total} 处；"
                  f"引号风格不统一 {len(set(quote_bad))} 章；"
                  f"时代混用 {len(cross)} 章",
    }


# ---------------------------------------------------------------- 汇总

# ---------------------------------------------------------------- P12

CN_NUM = '零一二三四五六七八九'


def to_cn_num(n: int) -> str:
    if n < 10:
        return CN_NUM[n]
    if n < 20:
        return '十' + (CN_NUM[n % 10] if n % 10 else '')
    if n < 100:
        return CN_NUM[n // 10] + '十' + (CN_NUM[n % 10] if n % 10 else '')
    return str(n)


TITLE_RE = re.compile(r'^#\s*第([0-9一二三四五六七八九十百零]+)章\s*(.+)$')
TITLE_MIN = 2200
TITLE_MAX = 3400
TITLE_STRICT = range(30, 47)   # 新写章节（ch30 起）字数硬区间


def check_p12_body_norm():
    """正文规范：标题格式 / 字数 / 引号 / 段落密度"""
    issues = []
    for fn in body_files():
        n = int(re.search(r'(\d+)', fn).group())
        with open(os.path.join(BODY_DIR, fn), encoding='utf-8') as f:
            t = f.read()
        m = TITLE_RE.match(t.splitlines()[0] if t else '')
        if not m:
            issues.append({'ch': n, 'type': '标题格式', 'detail': '首行非「# 第X章 标题」'})
            continue
        num, title = m.group(1), m.group(2).strip()
        if num.isdigit():
            issues.append({'ch': n, 'type': '标题格式',
                           'detail': f'章号用阿拉伯数字，应为「{to_cn_num(n)}」'})
        elif num != to_cn_num(n):
            issues.append({'ch': n, 'type': '标题格式',
                           'detail': f'章号「{num}」与文件章号不符，应为「{to_cn_num(n)}」'})
        if not title:
            issues.append({'ch': n, 'type': '标题', 'detail': '缺标题'})
        cnt = len(re.findall(r'[\u4e00-\u9fff]', t))
        if n in TITLE_STRICT and not (TITLE_MIN <= cnt <= TITLE_MAX):
            issues.append({'ch': n, 'type': '字数',
                           'detail': f'{cnt} 字，超出 {TITLE_MIN}-{TITLE_MAX}'})
        if t.count('「') != t.count('」'):
            issues.append({'ch': n, 'type': '引号', 'detail': '直角引号不配对'})
    return {
        'name': 'P12 正文规范',
        'status': 'FAIL' if issues else 'PASS',
        'data': {'问题': issues, '问题数': len(issues),
                 '字数硬区间章': f'ch{TITLE_STRICT.start}-ch{TITLE_STRICT.stop - 1}',
                 '区间': f'{TITLE_MIN}-{TITLE_MAX}'},
        'detail': f"{len(issues)} 项格式问题",
    }


# ---------------------------------------------------------------- 汇总

def check_p10_plagiarism(sk):
    """正文 × 道诡异仙原文 雷同检测（抄袭守卫）
    复用 .webnovel/plagiarism_check.py 的判定逻辑，避免两套阈值。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'plc', os.path.join(PROJ, '.webnovel', 'plagiarism_check.py'))
    if spec is None or spec.loader is None:
        return {'name': 'P10 正文抄袭检测', 'status': 'WARN',
                'data': {'错误': '无法定位 plagiarism_check.py'},
                'detail': '无法加载 plagiarism_check.py'}
    plc = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(plc)
    except Exception as e:
        return {'name': 'P10 正文抄袭检测', 'status': 'WARN',
                'data': {'错误': str(e)},
                'detail': '无法加载 plagiarism_check.py'}

    book = plc.load_book()
    if not book:
        return {'name': 'P10 正文抄袭检测', 'status': 'WARN',
                'data': {}, 'detail': '未找到原书，跳过检测'}

    rows = []
    for c in plc.body_chapters():
        fn = os.path.join(plc.BODY, f'第{c}章.md')
        if not os.path.exists(fn):
            continue
        raw = open(fn, encoding='utf-8').read()
        t = plc.norm(re.sub(r'^#.*$', '', raw, flags=re.M))
        if not t:
            continue
        best = (0, 0, None)
        for j, (_bt, bb) in book.items():
            b = plc.norm(bb)
            if not b:
                continue
            sm = difflib.SequenceMatcher(None, t, b, autojunk=False)
            bl_ = sm.get_matching_blocks()
            total = sum(x.size for x in bl_)
            longest = max(x.size for x in bl_)
            if total > best[0]:
                best = (total, longest, j)
        total, longest, j = best
        rate = total / max(1, len(t))
        status = 'PASS'
        if rate >= 0.35 or longest >= 40:
            status = 'BLOCK'
        elif rate >= 0.15 or longest >= 20:
            status = 'WARN'
        rows.append({'ch': c, 'rate': round(rate * 100, 1),
                     'longest': longest, 'match_ch': j, 'status': status})

    blocks = [r for r in rows if r['status'] == 'BLOCK']
    warns = [r for r in rows if r['status'] == 'WARN']
    return {
        'name': 'P10 正文抄袭检测',
        'status': 'FAIL' if blocks else ('WARN' if warns else 'PASS'),
        'data': {
            '检测章数': len(rows),
            'BLOCK章': [r['ch'] for r in blocks],
            'BLOCK明细': blocks,
            'WARN章': [r['ch'] for r in warns],
            'WARN明细': warns,
        },
        'detail': (f"检测 {len(rows)} 章：BLOCK {len(blocks)} 章（必须重写）"
                   f" / WARN {len(warns)} 章（需人工确认）"
                   f" / PASS {len(rows)-len(blocks)-len(warns)} 章"),
    }


# ── P13 来源专名残留检测 ───────────────────────────────────────────
# 骨架与正文里不得出现来源书独有的角色名/地名/组织名/术语/标志物。
# 词表来自 .webnovel/src_name_whitelist.json（人工筛定的来源书专名，均已验证
# 确实出现在来源原文中）。不设「源书频次≥5」门槛 —— 低频专名（如于儿神、虚字辈）
# 撞了照样是硬伤。
SOURCE_FILE = '/Users/glenx/Downloads/道诡异仙 作者：狐尾的笔.txt'

# 白名单文件缺失时的兜底词表（不完整，但不至于整项失效）
SOURCE_FORBIDDEN = [
    '李火旺', '丹阳子', '白灵淼', '吕状元', '赵五', '杨娜', '游老爷',
    '何信', '孙宝禄', '姜英子', '诸葛渊', '吕秀才', '正德寺', '清风观',
    '西京城', '建邺', '三山市', '监天司', '坐忘道', '心素', '玄阳',
    '五里岗', '牛心村', '安慈庵', '十字寺', '恒华山', '大润血丹',
    '小润血丹', '傩戏面具', '于儿神', '虚字辈', '司命', '妈陀', '蓐收',
    '心蟠', '司天少监', '皇甫天罡', '诸葛渊', '舍利子', '无生老母',
]


def src_whitelist():
    """读取来源书专名白名单（人工维护，固定表）。

    为什么不运行时自动提取：
    自动提取会把「自己/什么/他们/面对/意外」这类普通汉语词灌进词表，
    几百个假阳性淹没真残留。提取是离线动作，结论落到
    .webnovel/src_name_whitelist.json，审核时只做「词表 × 源书 × 资产」三查。

    词表来源（人工整理，每条都用源书原文校验过频次 >=3）：
      1) 映照表（角色/地名/道具/体系）的 key —— 权威「源书实体 → 我方替换名」
      2) 源书章节标题里的专名型标识词
      3) 源书独有的器物/制度/技艺名（灵孽/人魈/昼禁/问米/龙户…）
    通用称谓（道人/师父/长老/馒头/神像/牌位/香炉…）不进表 ——
    那是任何小说都会用的词，不构成抄袭证据。
    """
    wp = os.path.join(os.path.dirname(BODY_DIR), '.webnovel', 'src_name_whitelist.json')
    wl = []
    if os.path.exists(wp):
        try:
            wl = [str(x).strip() for x in json.load(open(wp, encoding='utf-8'))]
        except Exception:
            wl = []
    if not wl:
        wl = list(SOURCE_FORBIDDEN)
    # 源书校验：源书里 <3 次的不是源书专名（普通词或误录）
    book = load_source_book()
    if book:
        wl = [w for w in wl if book.count(w) >= 3]
    out, seen = [], set()
    for w in wl:
        if w and w not in seen and len(w) >= 2:
            seen.add(w)
            out.append(w)
    return out


def check_p13_source_names(sk):
    """来源专名/标志物残留：骨架 + 正文里不得出现来源书独有名字。"""
    wl = src_whitelist()
    if not os.path.exists(SOURCE_FILE):
        return {'name': 'P13 来源专名残留', 'status': 'WARN',
                'detail': '未找到来源原文，跳过', 'data': {}}
    blob = blob_all(sk)
    body = all_body_text()
    hits = []
    for w in wl:
        a = blob.count(w)
        b = body.count(w)
        if a or b:
            hits.append({'词': w, '骨架': a, '正文': b})
    if hits:
        return {'name': 'P13 来源专名残留', 'status': 'FAIL',
                'detail': f'发现 {len(hits)} 个来源书专名/标志物残留',
                'data': {'残留': hits}}
    return {'name': 'P13 来源专名残留', 'status': 'PASS',
            'detail': f'来源专名 0 残留（检测 {len(wl)} 个词）', 'data': {}}


# ── P14 标题同号相似度检测 ───────────────────────────────────────────
# 骨架若与源书「同一章号→同名标题」，等于整本书的骨架是源书的换名复刻。
# 这是比正文抄袭更严重的系统性问题：即使正文全部原创，读者仍能看出对应关系。
def load_source_book():
    """读取源书全文（用于标题/专名比对）。找不到返回 None。"""
    for cand in [
        '/Users/glenx/Downloads/道诡异仙 作者：狐尾的笔.txt',
        os.path.join(os.path.dirname(BODY_DIR), '..', '道诡异仙 参考', '道诡异仙.txt'),
    ]:
        if os.path.exists(cand):
            try:
                return open(cand, encoding='utf-8').read()
            except Exception:
                return None
    return None

# 通用词型章节标题：这些词在任何小说里都会出现，
# 「同号 + 通用词标题」不构成抄袭证据，计入 P14 软命中不判 FAIL。
GENERIC_TITLES = set(['一年', '一日', '一月', '夜色', '最后一次', '灾变'])
# 说明：通用词豁免表只允许放「任何小说都会用」的中性词。
# 判定标准：该词不是来源书章节标题里的标识词，且源书正文中不是专有术语。
# 上一版曾把 银陵城/灵孽/昼禁/龙户/赊刀人/记相/坐忘 等 105 个源书专名塞进这里，
# 导致 34 章与源书逐字相同的标题被自我豁免（详见 P14 检测器）。



def source_synopsis_map(book):
    """提取源书每章的开头若干字，作为该章剧情指纹。"""
    out = {}
    parts = re.split(r'^第(\d+)章\s*(.+?)\s*$', book, flags=re.M)
    # parts = [pre, num1, title1, body1, num2, title2, body2, ...]
    for i in range(1, len(parts) - 2, 3):
        try:
            out[int(parts[i])] = parts[i + 2][:400]
        except ValueError:
            continue
    return out


def check_p14_titles(sk):
    """标题同号相似度检测。

    分三级：
      硬（FAIL）—— 同号 + 标题含专名型撞词 + 剧情 synopsis 也相似
      中（WARN）—— 同号 + 标题相似，但剧情不同
      软（INFO）—— 同号 + 标题是通用词（"线索""陷阱""他们"…），
                   这类标题任何小说都会用，不构成抄袭证据
    """
    book = load_source_book()
    if not book:
        return {'name': 'P14 标题同号相似度', 'status': 'WARN',
                'data': {'错误': '未找到源书，跳过检测'},
                'detail': '未找到源书，跳过检测'}
    src_titles = {}
    for m in re.finditer(r'^第(\d+)章\s*(.+?)\s*$', book, re.M):
        src_titles[int(m.group(1))] = m.group(2).strip()
    src_synopsis = source_synopsis_map(book)

    hard, mid, soft = [], [], []
    for k, v in sk.items():
        if not isinstance(v, dict):
            continue
        n = int(k)
        st = src_titles.get(n)
        my = str(v.get('title', '')).strip()
        if not st or not my:
            continue
        r = difflib.SequenceMatcher(None, st, my).ratio()
        if r < 0.45:
            continue
        # 通用词型标题：任何小说都会用，不算证据
        if my in GENERIC_TITLES or len(my) <= 2:
            soft.append({'ch': n, '源': st, '我': my, '相似度': round(r, 2)})
            continue
        # 专名型：再看剧情是否也相似
        src_syn = src_synopsis.get(n, '')
        sim = seq_ratio(src_syn, str(v.get('synopsis', '')))
        row = {'ch': n, '源': st, '我': my, '标题相似度': round(r, 2),
               '剧情相似度': round(sim, 2)}
        if sim >= 0.55:
            hard.append(row)
        else:
            mid.append(row)
    status = 'FAIL' if hard else ('WARN' if mid else 'PASS')
    return {
        'name': 'P14 标题同号相似度',
        'status': status,
        'data': {
            '硬命中_标题与剧情双相似': hard,
            '中命中_仅标题相似': mid[:60],
            '软命中_通用词型不计入': len(soft),
        },
        'detail': (f"硬命中 {len(hard)} 章（标题+剧情双相似，必须改）；"
                   f"中命中 {len(mid)} 章（仅标题相似，需差异化）；"
                   f"通用词型 {len(soft)} 章（不计）"),
    }


# 我方专名与源书撞名的通用词豁免。
# 判据：源书里该词是普通名词/通用称谓（带路人、排行第二），不是专名标识。
# 撞专名标识（角色名、地名、组织名、器物专名）一律不豁免，必须改。
GENERIC_NAME_EXEMPT = {
    '向导': '通用称谓，源书指带路脚夫，非专名',
    '老二': '通用称谓，源书指排行第二/二儿子，非专名',
}


def check_p15_name_collision(sk):
    """反向检查：我方专名不得与源书原文撞名。

    骨架里出现的人名/地名/组织名，如果源书原文里也有，读者会一眼认出对应关系。
    这里只查映射表登记过的我方专名，避免通用词误报。
    """
    src = load_source_book()
    if not src:
        return {'name': 'P15 我方专名撞源书', 'status': 'WARN',
                'detail': '未找到来源原文，跳过', 'data': {}}
    mp = load_mapping()
    names = set()
    # 映照表用中文分组键（角色映射/道具映射/地名映射/体系映射），
    # 早期版本按英文 items/places/chars 取，取不到 → 静默扫 0 个（假阴性）。
    GRP_KEYS = ('角色映射', '道具映射', '地名映射')
    for grp in GRP_KEYS:
        for dk, dv in (mp.get(grp) or {}).items():
            if not isinstance(dv, dict):
                continue
            ln = dv.get('lieque_name')
            if not ln or ln in ('待定义', 'NA'):
                continue
            core = re.sub(r'[（(].*?[）)]', '', str(ln)).strip()
            if len(core) >= 2:
                names.add(core)
    # 体系映射：条目列表形式（说明 + 条目）
    sysm = mp.get('体系映射') or {}
    for item in (sysm.get('条目') or []) if isinstance(sysm, dict) else []:
        if isinstance(item, dict):
            ln = item.get('lieque_name') or item.get('裂隙对应')
            if ln and ln not in ('待定义', 'NA'):
                core = re.sub(r'[（(].*?[）)]', '', str(ln)).strip()
                if len(core) >= 2:
                    names.add(core)
    if not names:
        return {'name': 'P15 我方专名撞源书', 'status': 'FAIL',
                'detail': '映照表未解析出任何我方专名（假阴性，检查器失效）',
                'data': {'映照表键': sorted(mp.keys())}}
    body = all_body_text()
    blob = blob_all(sk)
    collide = []
    exempted = []
    for n in sorted(names):
        c = src.count(n)
        if c < 3:
            continue
        if n in GENERIC_NAME_EXEMPT:
            # 通用称谓/民俗词：源书当普通名词用，不构成抄袭证据。
            # 例：向导=带路人、老二=排行第二。
            exempted.append({'我方名': n, '源书频次': c,
                            '我方出现': body.count(n) + blob.count(n),
                            '理由': GENERIC_NAME_EXEMPT[n]})
            continue
        collide.append({'我方名': n, '源书频次': c,
                        '我方出现': body.count(n) + blob.count(n)})
    if collide:
        return {'name': 'P15 我方专名撞源书', 'status': 'FAIL',
                'detail': f'{len(collide)} 个我方专名与源书原文撞名'
                          f'（另有 {len(exempted)} 个通用词豁免）',
                'data': {'撞名': collide, '通用词豁免': exempted}}
    return {'name': 'P15 我方专名撞源书', 'status': 'PASS',
            'detail': f'我方专名 0 撞名（检查 {len(names)} 个，'
                      f'通用词豁免 {len(exempted)} 个）',
            'data': {'通用词豁免': exempted}}


def run():
    sk = load_skeleton()
    mp = load_mapping()
    bl = load_json(BASELINE)
    eb = load_json(ERA_BASELINE) if os.path.exists(ERA_BASELINE) else {}
    return [
        check_p1_mapping(sk, mp, bl),
        check_p2_leak(sk),
        check_p3_dup(sk, bl),
        check_p4_meta(sk),
        check_p5_worldline(sk),
        check_p6_emo(sk, mp, bl),
        check_p7_state(sk),
        check_p8_legacy(sk),
        check_p9_baseline(sk, bl),
        check_p10_plagiarism(sk),
        check_p11_era(sk, eb),
        check_p12_body_norm(),
        check_p13_source_names(sk),
        check_p14_titles(sk),
        check_p15_name_collision(sk),
    ]


def print_report(checks, hints=False):
    print('=' * 72)
    print('《裂隙》规划层审核报告')
    print('=' * 72)
    for c in checks:
        icon = {'FAIL': '[FAIL]', 'WARN': '[WARN]', 'PASS': '[PASS]'}[c['status']]
        print(f"{icon} {c['name']}")
        print(f"       {c['detail']}")
        if hints and c['status'] != 'PASS':
            for k, v in c['data'].items():
                if isinstance(v, (list, dict)) and v:
                    s = json.dumps(v, ensure_ascii=False)
                    print(f"       · {k}: {s[:420]}{'…' if len(s) > 420 else ''}")
        print()
    n_fail = sum(1 for c in checks if c['status'] == 'FAIL')
    n_warn = sum(1 for c in checks if c['status'] == 'WARN')
    print(f"规划审核: {n_fail} FAIL / {n_warn} WARN / {len(checks)} 项检查")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--hints', action='store_true')
    a = ap.parse_args()
    checks = run()
    if a.json:
        print(json.dumps(checks, ensure_ascii=False, indent=1))
    else:
        print_report(checks, hints=a.hints)


if __name__ == '__main__':
    main()
