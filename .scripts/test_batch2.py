#!/usr/bin/env python3
"""Debug batch 641-650 - check actual API response"""
import json, urllib.request, time

API_URL = "https://api.minimaxi.com/v1"
API_KEY = "sk-cp-C-uWiSPsa-ncbvmmSML2dBqTBvue_TxpZI7A64Pl4ThQ0iT1RE_MTdwDAnW4U-451R966oePV68I10g4e2M4XPp4A3LpzhoOgb7okcET8qtCngN6Vmqqudk"
MODEL = "MiniMax-Text-01"

INDEX_FILE = "/tmp/daoguai_chapters.json"
SOURCE_FILE = "/Users/glenx/Downloads/道诡异仙 作者：狐尾的笔.txt"

def read_chapters(index, source_path, ch_start, ch_end):
    chapters = {}
    with open(source_path, 'rb') as f:
        for i in range(ch_start, ch_end + 1):
            ch = next((c for c in index if c['ch'] == i), None)
            if not ch:
                continue
            start = ch['byte_offset']
            next_ch = next((c for c in index if c['ch'] == i + 1), None)
            end = next_ch['byte_offset'] if next_ch else None
            f.seek(start)
            raw = f.read(end - start if end else 10000)
            valid_utf8 = bytearray()
            j = 0
            while j < len(raw):
                b = raw[j]
                if b < 128:
                    valid_utf8.extend(bytes([b]))
                    j += 1
                elif b & 0xE0 == 0xC0:
                    if j + 1 < len(raw) and raw[j+1] & 0xC0 == 0x80:
                        valid_utf8.extend(raw[j:j+2])
                        j += 2
                    else:
                        j += 1
                elif b & 0xF0 == 0xE0:
                    if j + 2 < len(raw) and all(raw[j+k] & 0xC0 == 0x80 for k in [1,2]):
                        valid_utf8.extend(raw[j:j+3])
                        j += 3
                    else:
                        j += 1
                elif b & 0xF8 == 0xF0:
                    if j + 3 < len(raw) and all(raw[j+k] & 0xC0 == 0x80 for k in [1,2,3]):
                        valid_utf8.extend(raw[j:j+4])
                        j += 4
                    else:
                        j += 1
                else:
                    j += 1
            try:
                text = valid_utf8.decode('utf-8', errors='replace')
            except:
                text = raw.decode('latin-1', errors='replace')
            chapters[i] = text.strip()
    return chapters

def call_api(prompt, retries=3):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL + "/text/chatcompletion_v2",
                                  data=data,
                                  headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"API attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5)
            else:
                raise e

index = json.load(open(INDEX_FILE))
chapters = read_chapters(index, SOURCE_FILE, 641, 650)
chapters_text = "\n\n".join([f"【第{ch}章】{text[:400]}" for ch, text in sorted(chapters.items())])

prompt = f"""【核心任务】将以下《道诡异仙》641-650章的剧情"意同形不同"地改编为《裂隙》641-650章。
【转换规则】李火旺→沈念（仓库存整理员）；溶洞/清风观/炼丹→大剧院仓库/档案室/整理回声；修真→人间↔档案室传递回声；丹阳子→档案管理员
【daoguai ch641-650内容】{chapters_text}
【输出要求】标题（2-4字）、一句话摘要（20字内）、详细摘要（60字内），裂隙世界剧情。
【禁止词】玄天宗/地下监牢/阿兄/黑石/追兵/封灵索/玄棱场/筑基/反杀筑基/姜家岜峒/血脉觉醒者/外门弟子
【输出格式】{{"1":{{"title":"","synopsis_short":"","synopsis":""}},...}}"""

print(f"Calling API...")
result = call_api(prompt)
response_text = result['choices'][0]['message']['content']
print(f"Response length: {len(response_text)}")

# Parse line by line
batch_results = {}
for json_str in response_text.split('\n'):
    json_str = json_str.strip()
    if not json_str:
        continue
    start_idx = json_str.find('{')
    end_idx = json_str.rfind('}') + 1
    if start_idx >= 0 and end_idx > start_idx:
        fragment = json_str[start_idx:end_idx]
        try:
            parsed = json.loads(fragment)
            print(f"Parsed fragment keys: {list(parsed.keys())}")
            batch_results.update(parsed)
        except json.JSONDecodeError as e:
            print(f"Failed to parse: {e}")
            print(f"Fragment: {fragment[:100]}")

print(f"Total parsed: {len(batch_results)}")
print(f"Keys: {list(batch_results.keys())}")
