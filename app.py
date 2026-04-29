import streamlit as st
import pandas as pd
import re

# ==========================================
# 初始化 Session State
# ==========================================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ==========================================
# 1. 核心資料讀取模組
# ==========================================
def parse_bom_stable_logic(file_bytes):
    try: text = file_bytes.decode("big5")
    except: text = file_bytes.decode("utf-8", errors="ignore")
    
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
            for r in valid_refs: ref_map[r] = current_info
        elif line.startswith(" " * 10) and current_info:
            extra = [re.sub(r'\(.*?\)\d*', '', r).strip() for r in line.strip().split('.') if r.strip()]
            for r in [x for x in extra if re.match(r'^[A-Z]+\d+', x)]:
                ref_map[r] = current_info
    return ref_map

# ==========================================
# 2. 修正與 ECO 監測模組
# ==========================================
def process_bom_with_eco_monitor(master_map, target_bytes):
    try: 
        target_text = target_bytes.decode("big5")
        encoding_used = "big5"
    except: 
        target_text = target_bytes.decode("utf-8", errors="ignore")
        encoding_used = "utf-8"
        
    lines = target_text.splitlines()
    corrected_lines = []
    fix_log = []   # 存放自動修正的項目
    eco_log = []   # 存放疑似 ECO 的變更項目
    
    for line in lines:
        match = re.match(r'^(\d)\s+(\S+)\s+([\d.]+)', line)
        if match:
            t_level, t_pn, qty = int(match.group(1)), match.group(2), float(match.group(3))
            if qty > 0:
                parts = re.split(r'\s{2,}', line.strip())
                ref_raw = parts[-1] if len(parts) > 4 else ""
                raw_refs = [re.sub(r'\(.*?\)\d*', '', r).strip() for r in ref_raw.split('.') if r.strip()]
                valid_refs = [r for r in raw_refs if re.match(r'^[A-Z]+\d+', r)]
                
                is_fixed = False
                for r in valid_refs:
                    if r in master_map:
                        m_info = master_map[r]
                        # 情況 A：料號相同，但階層不同 -> 自動修正
                        if m_info["PN"] == t_pn:
                            if m_info["Level"] != t_level:
                                new_line = re.sub(r'^\d', str(m_info["Level"]), line, count=1)
                                corrected_lines.append(new_line)
                                fix_log.append({
                                    "位置 (Ref)": r,
                                    "料號 (PN)": t_pn,
                                    "❌ 原階層": t_level,
                                    "✅ 修正後": m_info["Level"]
                                })
                                is_fixed = True
                                break
                        # 情況 B：料號不同 -> 疑似 ECO 變更
                        else:
                            eco_log.append({
                                "位置 (Ref)": r,
                                "基準料號 (Master PN)": m_info["PN"],
                                "待修料號 (Target PN)": t_pn,
                                "基準階層": m_info["Level"],
                                "待修階層": t_level,
                                "狀態": "⚠️ 料號變動 (疑似 ECO)"
                            })
                if is_fixed: continue # 已修正則跳過後續處理
        
        corrected_lines.append(line)
        
    final_text = "\r\n".join(corrected_lines)
    return final_text, fix_log, eco_log, encoding_used

# ==========================================
# 3. Streamlit UI
# ==========================================
def main():
    st.set_page_config(page_title="BOM 智能修正與 ECO 監控工具", layout="wide")
    st.title("🎯 BOM 智能修正與 ECO 監控工具")
    st.markdown("以位置為對齊基礎，自動修正階層錯誤，並主動列舉疑似 ECO 的料號變動項目。")
    
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🗑️ 清除所有檔案", use_container_width=True):
            st.session_state.uploader_key += 1
            st.rerun()
            
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        master_file = st.file_uploader("📂 1. 上傳 基準 BOM (Master)", key=f"m_{st.session_state.uploader_key}")
        st.info(f"👉 狀態：{'✅ 已讀取' if master_file else '❌ 未讀取'}")
    with col2:
        target_file = st.file_uploader("📂 2. 上傳 待修 BOM (Target)", key=f"t_{st.session_state.uploader_key}")
        st.info(f"👉 狀態：{'✅ 已讀取' if target_file else '❌ 未讀取'}")

    if master_file and target_file:
        if st.button("🚀 執行智能分析與修復", use_container_width=True):
            with st.spinner("深度分析中..."):
                master_map = parse_bom_stable_logic(master_file.getvalue())
                final_text, fix_log, eco_log, encoding_used = process_bom_with_eco_monitor(master_map, target_file.getvalue())
                
                st.divider()
                
                # --- 第一部分：自動修正結果 ---
                st.subheader("✅ 階層自動修正紀錄")
                if fix_log:
                    st.success(f"已自動修正 {len(fix_log)} 處階層錯誤。")
                    st.dataframe(pd.DataFrame(fix_log), use_container_width=True)
                else:
                    st.info("未發現單純的階層錯誤。")

                # --- 第二部分：疑似 ECO 變更監控 (重點！) ---
                st.subheader("🔍 疑似 ECO 變更監控")
                if eco_log:
                    st.warning(f"偵測到 {len(eco_log)} 處位置發生料號變動，請核對 ECO 內容。")
                    # 移除重複的位置紀錄 (因為一個零件行可能有複數 Ref)
                    df_eco = pd.DataFrame(eco_log).drop_duplicates(subset=["位置 (Ref)"])
                    st.dataframe(df_eco, use_container_width=True)
                else:
                    st.success("未發現料號變動項目。")

                # --- 第三部分：下載 ---
                st.divider()
                st.markdown("### 📥 下載修正後的 BOM")
                output_bytes = final_text.encode(encoding_used, errors='replace')
                st.download_button(
                    label=f"點我下載修正檔 (Fixed_{target_file.name})",
                    data=output_bytes,
                    file_name=f"Fixed_{target_file.name}",
                    mime="text/plain"
                )

if __name__ == "__main__":
    main()
