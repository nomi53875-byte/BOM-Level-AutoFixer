import streamlit as st
import pandas as pd
import re

# ==========================================
# 1. 核心資料讀取模組 (解析 Master 作為標準答案)
# ==========================================
def parse_bom_stable_logic(file_bytes):
    """將 BOM 解析為以 Ref Des 為 Key 的字典"""
    try: 
        text = file_bytes.decode("big5")
    except: 
        text = file_bytes.decode("utf-8", errors="ignore")
    
    lines = text.splitlines()
    ref_map = {}
    current_info = None
    
    for line in lines:
        match = re.match(r'^(\d)\s+(\S+)\s+([\d.]+)', line)
        if match:
            level, pn, qty = int(match.group(1)), match.group(2), float(match.group(3))
            parts = re.split(r'\s{2,}', line.strip())
            desc = parts[3] if len(parts) > 3 else ""
            ref_raw = parts[-1] if len(parts) > 4 else ""
            
            if qty <= 0: continue
                
            raw_refs = [re.sub(r'\(.*?\)\d*', '', r).strip() for r in ref_raw.split('.') if r.strip()]
            valid_refs = [r for r in raw_refs if re.match(r'^[A-Z]+\d+', r)]
            current_info = {"Level": level, "PN": pn, "Desc": desc}
            
            for r in valid_refs: 
                ref_map[r] = current_info
                
        elif line.startswith(" " * 10) and current_info:
            extra = [re.sub(r'\(.*?\)\d*', '', r).strip() for r in line.strip().split('.') if r.strip()]
            for r in [x for x in extra if re.match(r'^[A-Z]+\d+', x)]:
                ref_map[r] = current_info
                
    return ref_map

# ==========================================
# 2. 修正模組：逐行掃描 Target 並無損替換階層
# ==========================================
def auto_correct_bom(master_map, target_bytes):
    try: 
        target_text = target_bytes.decode("big5")
        encoding_used = "big5"
    except: 
        target_text = target_bytes.decode("utf-8", errors="ignore")
        encoding_used = "utf-8"
        
    lines = target_text.splitlines()
    corrected_lines = []
    change_log = []  # 紀錄改了哪些東西，讓使用者安心
    
    for line in lines:
        # 尋找有階層數字開頭的行
        match = re.match(r'^(\d)\s+(\S+)\s+([\d.]+)', line)
        
        if match:
            target_level = int(match.group(1))
            pn = match.group(2)
            qty = float(match.group(3))
            
            if qty > 0:
                parts = re.split(r'\s{2,}', line.strip())
                ref_raw = parts[-1] if len(parts) > 4 else ""
                raw_refs = [re.sub(r'\(.*?\)\d*', '', r).strip() for r in ref_raw.split('.') if r.strip()]
                valid_refs = [r for r in raw_refs if re.match(r'^[A-Z]+\d+', r)]
                
                needs_correction = False
                correct_level = target_level
                
                # 用這行的位置去查 Master 標準答案
                for r in valid_refs:
                    if r in master_map and master_map[r]["PN"] == pn:
                        master_level = master_map[r]["Level"]
                        if master_level != target_level:
                            needs_correction = True
                            correct_level = master_level
                            break # 只要確認需要改，就中斷迴圈
                
                if needs_correction:
                    # 🚀 核心修正魔法：只替換行首的那個數字，其餘空白與排版 100% 保留
                    new_line = re.sub(r'^\d', str(correct_level), line, count=1)
                    corrected_lines.append(new_line)
                    
                    change_log.append({
                        "料號 (PN)": pn,
                        "包含位置": ".".join(valid_refs[:3]) + ("..." if len(valid_refs)>3 else ""),
                        "❌ 原錯誤階層": target_level,
                        "✅ 修正後階層": correct_level
                    })
                    continue # 這行處理完畢，跳下一行
        
        # 如果不是主零件行，或是檢查後發現不需要修正，就「原封不動」保留原本的字串
        corrected_lines.append(line)
        
    # 將所有行重新組合成一份完整的文字檔案 (\r\n 確保 Windows 記事本排版正常)
    final_text = "\r\n".join(corrected_lines)
    return final_text, change_log, encoding_used

# ==========================================
# 3. Streamlit UI
# ==========================================
def main():
    st.set_page_config(page_title="BOM 階層智能修正工具", layout="wide")
    st.title("✨ BOM 階層智能修正工具")
    st.markdown("上傳基準 BOM 與待修 BOM。系統會自動揪出「位置與料號都對，但階層打錯」的行，並直接幫你修正產生新檔案。")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        master_file = st.file_uploader("📂 1. 上傳 基準 BOM (Master - 標準答案)", type=["txt", "csv"])
    with col2:
        target_file = st.file_uploader("📂 2. 上傳 待修 BOM (Target - 要被修正的檔案)", type=["txt", "csv"])

    if master_file and target_file:
        if st.button("🛠️ 開始自動修正", use_container_width=True):
            with st.spinner("正在進行無損修復..."):
                # 1. 建立標準答案字典
                master_map = parse_bom_stable_logic(master_file.getvalue())
                
                # 2. 逐行掃描並修正 Target
                final_text, change_log, encoding_used = auto_correct_bom(master_map, target_file.getvalue())
                
                st.divider()
                if change_log:
                    st.success(f"🎉 修正完成！共幫你自動修復了 **{len(change_log)}** 行的階層錯誤。")
                    
                    # 顯示修正紀錄讓使用者確認
                    st.markdown("### 📝 修正紀錄")
                    st.dataframe(pd.DataFrame(change_log), use_container_width=True)
                    
                    # 提供下載按鈕
                    st.markdown("### 📥 下載修正後的 BOM")
                    
                    # 為了相容原本 ERP 的習慣，使用原本解析到的編碼 (Big5 或 UTF-8) 輸出
                    # 如果 Big5 遇到無法編碼的字元，用 replace 忽略，避免當機
                    output_bytes = final_text.encode(encoding_used, errors='replace')
                    
                    new_filename = f"Fixed_{target_file.name}"
                    st.download_button(
                        label=f"下載修正檔 ({new_filename})",
                        data=output_bytes,
                        file_name=new_filename,
                        mime="text/plain"
                    )
                else:
                    st.info("👍 檢查完畢！待修 BOM 裡面的階層都非常正確，沒有發現需要修正的地方。")

if __name__ == "__main__":
    main()
