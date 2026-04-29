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
    change_log = []  
    
    for line in lines:
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
                
                for r in valid_refs:
                    if r in master_map and master_map[r]["PN"] == pn:
                        master_level = master_map[r]["Level"]
                        if master_level != target_level:
                            needs_correction = True
                            correct_level = master_level
                            break 
                
                if needs_correction:
                    # 🚀 核心修正魔法：只替換行首的那個數字
                    new_line = re.sub(r'^\d', str(correct_level), line, count=1)
                    corrected_lines.append(new_line)
                    
                    change_log.append({
                        "料號 (PN)": pn,
                        "包含位置": ".".join(valid_refs[:3]) + ("..." if len(valid_refs)>3 else ""),
                        "❌ 原錯誤階層": target_level,
                        "✅ 修正後階層": correct_level
                    })
                    continue 
        
        corrected_lines.append(line)
        
    final_text = "\r\n".join(corrected_lines)
    return final_text, change_log, encoding_used

# ==========================================
# 3. Streamlit UI 介面
# ==========================================
def main():
    st.set_page_config(page_title="BOM 階層智能修正工具", layout="wide")
    st.title("✨ BOM 階層智能修正工具")
    st.markdown("上傳基準 BOM 與待修 BOM。系統會自動揪出「位置與料號都對，但階層打錯」的行，並直接幫你修正產生新檔案。")
    st.divider()

    # 左右兩個上傳區塊
    col1, col2 = st.columns(2)
    with col1:
        master_file = st.file_uploader("📂 1. 上傳 基準 BOM (Master - 標準答案)", type=["txt", "csv"])
        st.info(f"👉 基準檔案狀態：{'✅ 已讀取' if master_file else '❌ 未讀取'}")
        
    with col2:
        target_file = st.file_uploader("📂 2. 上傳 待修 BOM (Target - 要被修正的檔案)", type=["txt", "csv"])
        st.info(f"👉 待修檔案狀態：{'✅ 已讀取' if target_file else '❌ 未讀取'}")

    st.divider()

    # 判斷是否兩個檔案都上傳了
    if master_file and target_file:
        st.success("🎉 系統確認：兩個檔案都收到了！請點擊下方按鈕開始修正👇")
        
        if st.button("🛠️ 開始自動修正", use_container_width=True):
            with st.spinner("正在進行無損修復..."):
                master_map = parse_bom_stable_logic(master_file.getvalue())
                final_text, change_log, encoding_used = auto_correct_bom(master_map, target_file.getvalue())
                
                if change_log:
                    st.success(f"🎉 修正完成！共幫你自動修復了 **{len(change_log)}** 行的階層錯誤。")
                    
                    st.markdown("### 📝 修正紀錄")
                    st.dataframe(pd.DataFrame(change_log), use_container_width=True)
                    
                    st.markdown("### 📥 下載修正後的 BOM")
                    output_bytes = final_text.encode(encoding_used, errors='replace')
                    new_filename = f"Fixed_{target_file.name}"
                    
                    st.download_button(
                        label=f"點我下載修正檔 ({new_filename})",
                        data=output_bytes,
                        file_name=new_filename,
                        mime="text/plain"
                    )
                else:
                    st.info("👍 檢查完畢！待修 BOM 裡面的階層都非常正確，沒有發現需要修正的地方。")
    else:
        st.warning("⚠️ 系統判定：請確保上方【兩個框框】都有成功拖入檔案，執行按鈕才會出現喔！")

if __name__ == "__main__":
    main()
