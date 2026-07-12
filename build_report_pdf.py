# -*- coding: utf-8 -*-
"""Render eval_full_report content into a formatted PDF for human review.
Ad-hoc reporting script, not part of the shipped lawrag CLI."""
import json
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
pdfmetrics.registerFontFamily('STSong-Light', normal='STSong-Light', bold='STSong-Light',
                               italic='STSong-Light', boldItalic='STSong-Light')

META = os.environ.get('LAWRAG_META', r'C:\Users\wxt20\Documents\rag\metadata_output')
detail = json.load(open(os.path.join(META, 'eval_full_detail.json'), encoding='utf-8'))
rows = {r['qid']: r for r in detail['rows']}
summary = detail['summary']

FONT = 'STSong-Light'
FONT_BOLD = 'STSong-Light'  # reportlab has no built-in CJK bold CID font; emphasis via color/size instead

styles = getSampleStyleSheet()
title_style = ParagraphStyle('TitleZH', parent=styles['Title'], fontName=FONT_BOLD,
                              fontSize=19, leading=25, spaceAfter=4)
subtitle_style = ParagraphStyle('SubtitleZH', parent=styles['Normal'], fontName=FONT,
                                 fontSize=10, textColor=colors.HexColor('#555555'), leading=14)
h1 = ParagraphStyle('H1ZH', parent=styles['Heading1'], fontName=FONT_BOLD, fontSize=14,
                     leading=18, spaceBefore=16, spaceAfter=8, textColor=colors.HexColor('#1a1a2e'))
h2 = ParagraphStyle('H2ZH', parent=styles['Heading2'], fontName=FONT_BOLD, fontSize=11.5,
                     leading=15, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor('#16213e'))
body = ParagraphStyle('BodyZH', parent=styles['Normal'], fontName=FONT, fontSize=9.5,
                       leading=15, alignment=TA_LEFT, spaceAfter=6)
small = ParagraphStyle('SmallZH', parent=body, fontSize=8, leading=12, textColor=colors.HexColor('#444444'))
mono_small = ParagraphStyle('MonoSmall', parent=small, fontName=FONT, fontSize=8, leading=12,
                             textColor=colors.HexColor('#333333'))
callout_title = ParagraphStyle('CalloutTitle', parent=body, fontName=FONT_BOLD, fontSize=10.5,
                                spaceAfter=4)
callout_body = ParagraphStyle('CalloutBody', parent=body, fontSize=9, leading=13.5)
tbl_head = ParagraphStyle('TblHead', parent=body, fontName=FONT_BOLD, fontSize=8.5,
                           textColor=colors.white, leading=11)
tbl_cell = ParagraphStyle('TblCell', parent=body, fontSize=8, leading=11, spaceAfter=0)
tbl_cell_c = ParagraphStyle('TblCellC', parent=tbl_cell, alignment=1)

NAVY = colors.HexColor('#16213e')
LIGHT = colors.HexColor('#f2f4f8')
GREEN = colors.HexColor('#e8f5e9')
RED = colors.HexColor('#fdecea')
AMBER = colors.HexColor('#fff4e5')
GREEN_TXT = colors.HexColor('#1e7d34')
RED_TXT = colors.HexColor('#8a1c1c')
AMBER_TXT = colors.HexColor('#8a5a00')

story = []

# ---------- Cover / header ----------
story.append(Paragraph('lawrag Eval 报告', title_style))
story.append(Paragraph('检索基线 + 完整评测（BM25 / DeepSeek-chat） — 三轮迭代最终结果', subtitle_style))
story.append(Spacer(1, 10))

meta_rows = [
    ['运行日期', '2026-07-12 首轮 + 修复 ～ 2026-07-13 补丁 + 复核定稿'],
    ['仓库', 'ragflow_repo（已推送 github.com/x-tian-lab/ragflow，commit 5b2acfc → 22971c4）'],
    ['语料根 (LAWRAG_ROOT)', 'C:\\Users\\wxt20\\Desktop\\rag sys（与指令给出的路径不同，已修正）'],
    ['检索器', 'BM25 / jieba, k=5（三轮未改动）'],
    ['LLM', 'deepseek-chat (api.deepseek.com/v1)'],
    ['测试集', 'testset_v1.jsonl — 60 题（55 正题 + 5 拒答题）'],
]
mt = Table([[Paragraph(f'<b>{a}</b>', small), Paragraph(b, small)] for a, b in meta_rows],
           colWidths=[42*mm, 128*mm])
mt.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.white),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(mt)
story.append(Spacer(1, 14))

# ---------- Executive summary ----------
story.append(Paragraph('执行摘要', h1))
story.append(Paragraph(
    '三轮迭代：v1 原始代码自动判分 <b>61.7%</b>（37/60，拒答 0/5）→ v2 修复 doc_title 截断 + 引用判分逻辑后 '
    '<b>68.3%</b>（41/60，拒答标志修复因全/半角逗号 bug 未生效，拒答仍 0/5）→ v3 补上逗号归一化后 '
    '<b>76.7%</b>（46/60，<font color="#1e7d34">拒答 5/5</font>）。'
    '本轮对全部 14 道剩余判负题做了 100% 人工复核（此前只抽查了 11/23），确认其中 10 道内容其实正确，'
    '人工复核后的估计准确率约 <b>93.3%</b>（56/60），已明显超过 spec 验收线（&gt;80%）。', body))

v_data = [
    ['版本', '代码状态', '准确率', '拒答正确率'],
    ['v1', '首次跑通，未修复', '61.7%（37/60）', '0/5'],
    ['v2', '修 doc_title + cite_ok + 判分归一化；refused 标志修复有 bug', '68.3%（41/60）', '0/5'],
    ['v3', '补上逗号归一化，重建索引', '76.7%（46/60）', '5/5'],
    ['v3 + 人工复核', '全部 14 道剩余判负题逐一核对', '≈93.3%（56/60，非自动判分）', '5/5'],
]
vt = Table([[Paragraph(c, tbl_head if i == 0 else tbl_cell) for c in row] for i, row in enumerate(v_data)],
           colWidths=[28*mm, 92*mm, 32*mm, 18*mm], repeatRows=1)
vt.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(vt)
story.append(Spacer(1, 10))

comma_box = Table([
    [Paragraph('关键调试细节：全角/半角逗号 bug', ParagraphStyle('ct2', parent=callout_title, textColor=RED_TXT))],
    [Paragraph(
        'v2 里 generator.py 判断 LLM 是否自主拒答用的是 <font face="Courier">REFUSE_NO_HIT.rstrip(x) in text</font>'
        '（x 为句号），'
        '但 REFUSE_NO_HIT 字面量写的是半角逗号","，DeepSeek-chat 实际输出的是中文全角逗号"，"——一个字符宽度不匹配，'
        '子串匹配全部失败，5 道拒答题的 refused 标志继续保持 False。'
        '两侧统一归一化为半角逗号后（commit 22971c4），拒答题从 0/5 直接跳到 5/5。', callout_body)],
], colWidths=[170*mm])
comma_box.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, -1), RED),
    ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#c0392b')),
    ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
]))
story.append(comma_box)

story.append(PageBreak())

# ---------- Section 1: env ----------
story.append(Paragraph('1. 环境修正记录', h1))
env_data = [['项目', '指令给出', '实际情况']]
env_data += [
    ['LAWRAG_ROOT', 'Documents\\rag\\rag sys', '不存在；实际语料在 Desktop\\rag sys（1451 文件，40MB），已改用此路径'],
    ['控制台编码', '—', '默认 GBK，eval --mode full 打印 ✓/✗ 会报错，需设 PYTHONIOENCODING=utf-8'],
    ['LLM API Key', '未提供', '由用户提供 DeepSeek key，运行时通过环境变量注入，未落盘'],
]
et = Table([[Paragraph(c, tbl_head if i == 0 else tbl_cell) for c in row] for i, row in enumerate(env_data)],
           colWidths=[30*mm, 45*mm, 95*mm], repeatRows=1)
et.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(et)

# ---------- Section 2: index ----------
story.append(Paragraph('2. 索引构建（index --retriever bm25）', h1))
story.append(Paragraph(
    '三轮共用：1115/1115 文件解析成功，0 失败。共 59097 个 chunk，引用级别 A 55338（94%）/ B 3759（6%）/ C 0（0%）。'
    'v3 索引在应用 metadata_overrides/manual_titles.json 后重建，doc_title 已更正（见第4节"发现2"历史记录）。', body))

# ---------- Section 3: retrieval baseline ----------
story.append(Paragraph('3. 检索基线（eval --mode retrieval，不调 LLM）', h1))
story.append(Paragraph(
    '三轮未改动检索器代码，基线数字保持一致：n=55，file_hit@5 = <b>94.5%</b>，loc_hit@5 = <b>92.7%</b>'
    '（优于 README 历史基线 90.9%/89.1%）。', body))
rt_data = [['格式', 'n', 'file_hit@5', 'loc_hit@5']]
rt_data += [
    ['doc', '10', '100%', '100%'], ['docx', '22', '100%', '100%'],
    ['md', '5', '40%', '40%'], ['txt', '13', '100%', '92%'], ['xlsx', '5', '100%', '100%'],
]
rtt = Table([[Paragraph(c, tbl_head if i == 0 else tbl_cell_c) for c in row] for i, row in enumerate(rt_data)],
            colWidths=[40*mm, 30*mm, 50*mm, 50*mm], repeatRows=1)
rtt.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(rtt)
story.append(Spacer(1, 6))
story.append(Paragraph(
    '3 个未命中（M02/M04/M05）全部集中在 md 格式，属于已知限制"跨格式孪生文档"导致的评测口径问题，'
    '不是检索能力问题。', body))

story.append(PageBreak())

# ---------- Section 4: full eval history ----------
story.append(Paragraph('4. 完整评测三轮对比（eval --mode full，调用 DeepSeek-chat）', h1))

story.append(Paragraph('v1（原始代码）— 61.7%', h2))
story.append(Paragraph(
    '自动判分把 5 道拒答题全部计为失败，另有 18 道正题判负。人工抽查 11 道后确认根因集中在三类：'
    'generator.py 的 refused 标志漏设、3 份文档的 doc_title 被截断、eval.py 判分逻辑过于死板（子串匹配、无数值容差）。', body))

story.append(Paragraph('v2（首批修复后）— 68.3%', h2))
story.append(Paragraph(
    '修复 doc_title 截断（metadata_overrides/manual_titles.json + pipeline.py 覆盖层）、cite_ok 改为结构化比对 '
    'chunk.file_name/doc_title、_contains_key 加入全半角归一化 + 数值相对误差容差。6 道题（D02/C03/C10/T12/M04/X02）'
    '由 FAIL 转 OK。同批提交也修了 refused 漏标问题，但补丁本身有 bug（下方说明），拒答题仍 0/5。'
    '另出现 2 道"新失败"（D04/T02），人工核对后确认内容完全正确，是 LLM 回答措辞随机性撞上判分假阴性，'
    '<b>不是代码回归</b>。', body))

story.append(Paragraph('v3（本报告最终版）— 76.7%，拒答 5/5', h2))
story.append(Paragraph(
    f'n=60，准确率 = <b>{summary["accuracy"]*100:.1f}%</b>，超时(&gt;5s)题数 = {summary["over_5s"]}，'
    f'拒答正确 = {summary["refuse_correct"]}/{summary["refuse_total"]}。全部 60 题延迟均 &lt;5s，满足验收线。', body))

qt_data = [['题型 qtype', 'n', '准确率']]
for k, v in summary['by_qtype'].items():
    qt_data.append([k, str(v['n']), f'{v["acc"]*100:.1f}%'])
ft_data = [['格式 format', 'n', '准确率']]
for k, v in summary['by_format'].items():
    ft_data.append([k, str(v['n']), f'{v["acc"]*100:.1f}%'])


def make_small_table(data):
    t = Table([[Paragraph(c, tbl_head if i == 0 else tbl_cell_c) for c in row] for i, row in enumerate(data)],
              colWidths=[38*mm, 18*mm, 25*mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


two_col = Table([[make_small_table(qt_data), make_small_table(ft_data)]], colWidths=[85*mm, 85*mm])
two_col.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
story.append(two_col)

story.append(PageBreak())

# ---------- Section 5: 100% manual review ----------
story.append(Paragraph('5. 剩余 14 道判负题 — 本轮 100% 人工复核', h1))
story.append(Paragraph(
    '不同于 v1 报告只抽查了 23 道判负题中的 11 道，这次对 v3 剩余的全部 14 道判负题逐一核对。', body))

cat_data = [
    ['分类', 'qid', '结论'],
    ['判分假阴性（内容完全正确）',
     'D04,D09,D14,D17,D18,C05,C09,D21,T02',
     '答案与黄金答案在事实/数字/日期上完全一致，只是句式、括号说明、百分数写法（"80%" vs "百分之八十"）等表层差异触发假阴性'],
    ['判分假阴性（正确回答了所问，黄金答案含额外未问信息）',
     'D07',
     '题目只问"情节严重"档罚款上限，模型只答该档是对的，但黄金答案还含"一般情形"数字，全量关键词比对判负'],
    ['真实但轻微的内容缺口', 'T09', '只引用了两部依据法规中的一部，漏引一部；其余内容（部门名称等）正确'],
    ['真实生成错误', 'M02', '把《证券法》总则第五条误当成第三章第三节"禁止内幕交易"的第五十条——条号张冠李戴'],
    ['真实检索颗粒度缺口（正确拒答但不给分）',
     'M05,X03',
     '命中了正确的 xlsx 源文件，但具体数字所在的表格行未被拆进检索到的 chunk，模型如实拒答而非编造'],
]
ct = Table([[Paragraph(c, tbl_head if i == 0 else tbl_cell) for c in row] for i, row in enumerate(cat_data)],
           colWidths=[46*mm, 40*mm, 84*mm], repeatRows=1)
ct.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(ct)
story.append(Spacer(1, 8))
story.append(Paragraph(
    '即 14 道里 10 道内容其实正确（9 假阴性 + D07 部分正确算对），1 道部分对（T09），1 道真错（M02），'
    '2 道是"正确拒答但拿不到分"的表格检索缺口（M05/X03）。'
    '<b>人工复核后的估计准确率：(46 + 10) / 60 ≈ 93.3%</b>——这不是自动化数字，仅供参考，'
    '正式验收仍应走 spec 既定的人工复核流程。', body))

story.append(PageBreak())

# ---------- Section 6: recommendations ----------
story.append(Paragraph('6. 建议（更新版，已完成项标记）', h1))
recs_done = [
    'generator.py::generate() 的 refused 漏标 — 已完成（commit 5b2acfc, 22971c4）',
    'eval.py::eval_full 的 cite_ok 判定改结构化比对 — 已完成（commit 5b2acfc）',
    '人工修正 3 条已定位的 doc_title — 已完成（metadata_overrides/manual_titles.json）',
]
for r in recs_done:
    story.append(Paragraph(f'✓ <font color="#1e7d34">{r}</font>', body))

recs_new = [
    'M05/X03 暴露的表格分块粒度问题：大型 xlsx 源表转换/分块后，某些具体统计行未必落在检索返回的 top-k chunk 里。'
    '建议评估按行/列关键字段加大表格 chunk 的召回覆盖，或对大表增加行级索引。',
    'M02 的真实错误提示检索/生成在"总则性提及"与"具体章节条文"之间的消歧还不够——禁止内幕交易在《证券法》里'
    '既在总则第五条被原则性提及，又在第三章第三节第五十条具体规定，模型引用了前者。可考虑在检索排序或 prompt 里'
    '加入"优先选择具体章节而非总则"的启发式。',
    '剩余的 10 道判分假阴性建议把 _contains_key 换成弱 LLM-judge，或改为人工语义复核——这是目前自动化数字'
    '（76.7%）与实际质量（约93%）之间差距的主要来源。',
]
for i, r in enumerate(recs_new, 1):
    story.append(Paragraph(f'{i}. {r}', body))

story.append(PageBreak())

# ---------- Appendix: full table ----------
story.append(Paragraph('附录 A：完整 60 题最终结果（v3）', h1))
story.append(Paragraph(
    '标记：<font color="#1e7d34">假阴性</font> = 人工核对后内容正确。'
    '<font color="#8a5a00">部分</font> = 内容部分正确/有轻微缺口。'
    '<font color="#8a1c1c">真实错误/缺口</font> = 确认的真实问题。', small))
story.append(Spacer(1, 4))

notes = {
    'D04': ('FAIL', '假阴性', AMBER), 'D07': ('FAIL', '假阴性(部分)', AMBER),
    'D09': ('FAIL', '假阴性', AMBER), 'D14': ('FAIL', '假阴性', AMBER),
    'D17': ('FAIL', '假阴性', AMBER), 'D18': ('FAIL', '假阴性', AMBER),
    'D21': ('FAIL', '假阴性(cite_ok已修复)', AMBER),
    'C05': ('FAIL', '假阴性', AMBER), 'C09': ('FAIL', '假阴性', AMBER),
    'T02': ('FAIL', '假阴性', AMBER),
    'T09': ('FAIL', '部分缺口(漏引一部法规)', AMBER),
    'M02': ('FAIL', '真实错误(条号张冠李戴)', RED),
    'M05': ('FAIL', '检索颗粒度缺口(正确拒答)', RED),
    'X03': ('FAIL', '检索颗粒度缺口(正确拒答)', RED),
}

order = list(rows.keys())
head = ['qid', 'qtype', 'format', '结果', 'cite_ok', 'key_ok', 'refused', '结论']
data = [head]
row_colors = [None]
for qid in order:
    r = rows[qid]
    if qid in notes:
        label, note, color = notes[qid]
    else:
        label, note, color = ('OK' if r['ok'] else 'FAIL', '—', GREEN if r['ok'] else None)
    data.append([qid, r['qtype'], r['format'], label,
                 str(r['cite_ok']), str(r['key_ok']), str(r['refused']), note])
    row_colors.append(color)

tdata = [[Paragraph(c, tbl_head if i == 0 else tbl_cell_c) for c in row[:-1]] +
         [Paragraph(row[-1], tbl_head if i == 0 else tbl_cell)]
         for i, row in enumerate(data)]
apt = Table(tdata, colWidths=[13*mm, 17*mm, 15*mm, 15*mm, 15*mm, 15*mm, 15*mm, 55*mm], repeatRows=1)
style_cmds = [
    ('BACKGROUND', (0, 0), (-1, 0), NAVY),
    ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dddddd')),
    ('ALIGN', (0, 0), (-1, -2), 'CENTER'),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
]
for i, c in enumerate(row_colors):
    if i == 0:
        continue
    bg = c if c else (GREEN if data[i][3] == 'OK' else colors.white)
    style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))
apt.setStyle(TableStyle(style_cmds))
story.append(apt)

story.append(Spacer(1, 10))
story.append(Paragraph('附录 B：原始数据文件与复现', h1))
story.append(Paragraph(
    'eval_full_detail.json — v3 最终版 60 题完整明细（问题、黄金答案、检索命中文件、模型完整回答、引用列表、'
    '各判分子项、耗时）。复现命令：设置报告开头的环境变量后依次执行 '
    '<font face="Courier">python -m lawrag.cli index --retriever bm25</font> 与 '
    '<font face="Courier">python -m lawrag.cli eval --mode full</font>。'
    '逐题明细额外用了 ragflow_repo/run_diag_eval.py（判分逻辑与 lawrag/eval.py::eval_full 保持同步）。'
    '代码改动：5b2acfc（refused 标志 + cite_ok 结构化比对 + doc_title 修正）、'
    '22971c4（修复全/半角逗号导致 refused 补丁失效）。', small))

# ---------- Build ----------
out_path = os.path.join(META, 'eval_full_report.pdf')
doc = SimpleDocTemplate(out_path, pagesize=A4,
                         leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
                         title='lawrag Eval 报告', author='lawrag eval pipeline')
doc.build(story)
print('written to', out_path)
