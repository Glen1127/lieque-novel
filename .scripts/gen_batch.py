#!/usr/bin/env python3
"""Generate one batch of 10 chapter titles/synopses for 裂隙 skeleton"""
import json, os, urllib.request, time

API_URL = "https://api.minimaxi.com/v1"
API_KEY = "sk-cp-C-uWiSPsa-ncbvmmSML2dBqTBvue_TxpZI7A64Pl4ThQ0iT1RE_MTdwDAnW4U-451R966oePV68I10g4e2M4XPp4A3LpzhoOgb7okcET8qtCngN6Vmqqudk"
MODEL = "MiniMax-Text-01"

WORK_DIR = "/Users/glenx/Library/Mobile Documents/iCloud~md~obsidian/Documents/裂隙/裂隙写作"
OUTPUT_FILE = f"{WORK_DIR}/lieque_reverse/04章节表/generated_all_818.json"
INDEX_FILE = "/tmp/daoguai_chapters.json"
SOURCE_FILE = "/Users/glenx/Downloads/道诡异仙 作者：狐尾的笔.txt"

def read_chapters(index, source_path, ch_start, ch_end):
    """Read chapters with proper encoding handling"""
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
            
            # Find valid UTF-8 sequences
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

def main():
    # Load existing results
    existing = json.load(open(OUTPUT_FILE)) if os.path.exists(OUTPUT_FILE) else {}
    index = json.load(open(INDEX_FILE))
    
    # Find first missing chapter (keys are strings)
    existing_int = set(int(k) for k in existing.keys())
    first_missing = 1
    while first_missing in existing_int and first_missing <= 818:
        first_missing += 1
    
    if first_missing > 818:
        print("All 818 chapters complete!")
        return
    
    batch_start = ((first_missing - 1) // 10) * 10 + 1
    batch_end = min(batch_start + 9, 818)
    
    print(f"Processing batch {batch_start}-{batch_end} (first missing: {first_missing})")
    
    # Read source chapters
    chapters = read_chapters(index, SOURCE_FILE, batch_start, batch_end)
    
    # Build prompt
    chapters_text = "\n\n".join([f"【第{ch}章】{text[:400]}" for ch, text in sorted(chapters.items())])
    
    prompt = f"""【核心任务】将以下《道诡异仙》{batch_start}-{batch_end}章的剧情"意同形不同"地改编为《裂隙》{batch_start}-{batch_end}章。
【转换规则】李火旺→沈念（仓库存整理员）；溶洞/清风观/炼丹→大剧院仓库/档案室/整理回声；修真→人间↔档案室传递回声；丹阳子→档案管理员
【daoguai ch{batch_start}-{batch_end}内容】{chapters_text}
【输出要求】标题（2-4字）、一句话摘要（20字内）、详细摘要（60字内），裂隙世界剧情。
【禁止词】玄天宗/地下监牢/阿兄/黑石/追兵/封灵索/玄棱场/筑基/反杀筑基/姜家岜峒/血脉觉醒者/外门弟子
【输出格式】{{"1":{{"title":"","synopsis_short":"","synopsis":""}},...}}"""
    
    # Call API
    print(f"Calling MiniMax API...")
    result = call_api(prompt)
    response_text = result['choices'][0]['message']['content']
    print(f"Response length: {len(response_text)}")
    
    # Parse JSON - API may return multiple separate JSON objects separated by newlines
    # Keys are 1-indexed within the batch (1-10), need to remap to actual chapter numbers
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
                # Remap keys from 1-indexed to actual chapter numbers
                for k, v in parsed.items():
                    actual_ch = batch_start + int(k) - 1
                    batch_results[str(actual_ch)] = v
            except json.JSONDecodeError:
                pass  # Skip malformed fragments
    
    if not batch_results:
        print(f"Could not parse any valid JSON from response")
        print(f"Response: {response_text[:500]}")
        return

    # Merge and save
    existing.update(batch_results)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(existing)} chapters total. Batch {batch_start}-{batch_end} complete.")

if __name__ == "__main__":
    main()
