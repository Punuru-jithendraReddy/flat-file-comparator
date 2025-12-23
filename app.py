import streamlit as st
import pandas as pd
from io import BytesIO
import datetime
import time

# --- 1. CONFIGURATION & SETUP ---
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    HAS_OPENPYXL = True
except Exception:
    HAS_OPENPYXL = False

st.set_page_config(
    page_title="Flat File Comparison Tool", 
    page_icon="📊",
    layout="wide"
)

# --- 2. CSS STYLING (Green Button, Blue Tags, Profile, Alignment) ---
st.markdown("""
<style>
    /* 1. GREEN BUTTON (Strict) */
    div.stButton > button {
        background-color: #28a745 !important; 
        color: white !important;
        border-color: #28a745 !important;
        font-weight: bold !important;
        width: 100%;
        height: 50px;
        font-size: 18px !important;
    }
    div.stButton > button:hover {
        background-color: #218838 !important;
        border-color: #1e7e34 !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }

    /* 2. BLUE MULTISELECT TAGS (Strict) */
    span[data-baseweb="tag"] {
        background-color: #007bff !important;
        color: white !important;
    }

    /* 3. METRIC BOXES - Better Alignment */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        height: 100%; /* Force equal height */
    }

    /* 4. FOOTER */
    .footer {
        position: fixed;
        left: 0; bottom: 0; width: 100%;
        background-color: #1a202c;
        color: white;
        text-align: center;
        padding: 10px;
        font-size: 14px;
        z-index: 99999;
    }
    .footer a { color: #63b3ed; text-decoration: none; font-weight: bold; }
    
    /* SECTION HEADERS (To match Excel look on UI) */
    .section-header {
        color: #2c3e50;
        font-weight: 700;
        font-size: 1.2rem;
        margin-top: 20px;
        margin-bottom: 10px;
        padding-bottom: 5px;
        border-bottom: 2px solid #4472C4; /* Excel Blue */
    }

    /* Adjust padding for footer */
    .block-container { padding-bottom: 80px; }
</style>
""", unsafe_allow_html=True)

# --- 3. LOGIC FUNCTIONS ---

def normalize_for_comparison(series, is_case_insensitive_data, should_trim_whitespace):
    """Standardizes data for comparison."""
    s_numeric = pd.to_numeric(series, errors='coerce')
    s = series.where(s_numeric.isna(), s_numeric)
    s = pd.to_datetime(s, errors='coerce').dt.strftime('%Y-%m-%d').fillna(s)
    s = s.astype(str)
    s = s.str.replace(r'\.0$', '', regex=True)
    s_lower_for_nulls = s.str.lower().str.strip()
    s[s_lower_for_nulls.isin(['nan', '<na>', 'none', 'nat', ''])] = ''
    
    if should_trim_whitespace:
        s = s.str.strip().str.replace(r'\s+', ' ', regex=True) 
        
    if is_case_insensitive_data:
        s = s.str.lower()
        
    return s

def smart_read_file(file_obj, header_row):
    """Reads file, automatically selecting the sheet with the most rows."""
    file_ext = file_obj.name.split('.')[-1].lower()
    
    try:
        if file_ext in ['xlsx', 'xls', 'xlsm', 'xlsb', 'odf', 'ods']:
            xls = pd.ExcelFile(file_obj)
            if len(xls.sheet_names) == 1:
                return pd.read_excel(file_obj, header=header_row)
            
            # Scan for the best sheet
            best_df, max_rows = None, -1
            
            for sheet in xls.sheet_names:
                try:
                    temp_df = pd.read_excel(file_obj, sheet_name=sheet, header=header_row)
                    if len(temp_df) > max_rows:
                        max_rows = len(temp_df)
                        best_df = temp_df
                except: continue
            
            return best_df

        elif file_ext == 'json': return pd.read_json(file_obj)
        elif file_ext == 'xml': return pd.read_xml(file_obj)
        else:
            # CSV/TSV
            common_args = {'header': header_row, 'engine': 'python', 'sep': None if file_ext != 'tsv' else '\t', 'skipinitialspace': True}
            try:
                file_obj.seek(0)
                return pd.read_csv(file_obj, encoding='utf-8-sig', **common_args)
            except:
                file_obj.seek(0)
                return pd.read_csv(file_obj, encoding='latin1', **common_args)
                
    except Exception as e:
        st.error(f"Failed to read {file_obj.name}. Error: {e}")
        return None

def get_diagnosis(pct):
    if pct == 100: return "Files are identical."
    elif pct >= 95: return "High Accuracy (Minor Differences)"
    elif pct >= 80: return "Moderate Variance"
    else: return "Critical Mismatch"

# --- 4. SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/10891/10891404.png", width=70)
    st.title("Settings")
    
    st.markdown("### 🛠 Options")
    opt_case_cols = st.checkbox("Case-Insensitive Columns", value=True)
    opt_case_data = st.checkbox("Case-Insensitive Data", value=True)
    opt_trim = st.checkbox("Trim Whitespace", value=True)
    
    st.markdown("### 📑 Excel Output")
    gen_row_sheet = st.checkbox("Row Comparison", value=True)
    gen_col_sheet = st.checkbox("Column Analysis", value=True)
    gen_uniq_sheet = st.checkbox("Unique Values", value=True)
    gen_stats_sheet = st.checkbox("Summary Stats", value=True)

    st.markdown("---")
    st.markdown("### 👨‍💻 Developer")
    st.markdown("**Jithendra Reddy**")
    st.markdown("📧 [Email](mailto:jithendrareddypunuru@gmail.com)")
    st.markdown("🔗 [LinkedIn](https://www.linkedin.com/in/jithendrareddypunuru/)")

# --- 5. MAIN UI ---

st.title("📂 Flat File Comparison Tool")
st.markdown("Upload two files below to generate a detailed comparison report.")

# A. File Inputs
col_input1, col_input2 = st.columns(2)
with col_input1:
    st.subheader("Source File")
    src_file = st.file_uploader("Upload Source", type=["xlsx", "xls", "csv", "tsv", "json", "xml"], key="src")
    src_header = st.number_input("Header Row (Source)", min_value=1, value=1, key="h1") - 1

with col_input2:
    st.subheader("Target File")
    tgt_file = st.file_uploader("Upload Target", type=["xlsx", "xls", "csv", "tsv", "json", "xml"], key="tgt")
    tgt_header = st.number_input("Header Row (Target)", min_value=1, value=1, key="h2") - 1

# B. Execution
if src_file and tgt_file:
    st.divider()
    
    # Read Files
    df1 = smart_read_file(src_file, src_header)
    df2 = smart_read_file(tgt_file, tgt_header)

    if df1 is not None and df2 is not None:
        # Get Total Counts immediately
        total_src_rows = len(df1)
        total_tgt_rows = len(df2)

        # Map Columns
        src_cols = df1.columns
        tgt_cols = df2.columns
        common_cols_list = []
        src_to_tgt_map = {}

        if opt_case_cols:
            src_map = {str(c).lower(): c for c in src_cols}
            tgt_map = {str(c).lower(): c for c in tgt_cols}
            common_lower = set(src_map.keys()) & set(tgt_map.keys())
            for k in common_lower:
                common_cols_list.append(src_map[k])
                src_to_tgt_map[src_map[k]] = tgt_map[k]
        else:
            common = set(src_cols) & set(tgt_cols)
            common_cols_list = list(common)
            src_to_tgt_map = {c: c for c in common}

        if not common_cols_list:
            st.error("❌ No common columns found.")
        else:
            c_sel, c_btn = st.columns([3, 1])
            with c_sel:
                # Default: Select ALL common columns
                all_options = sorted(common_cols_list, key=str)
                selected_src = st.multiselect(
                    "Select Key Columns (Unique Identifiers)", 
                    options=all_options,
                    default=all_options
                )

            with c_btn:
                st.write("") # Spacer
                st.write("") 
                # This button will be GREEN due to CSS
                run_btn = st.button("🚀 Run Comparison")

            if run_btn:
                if not selected_src:
                    st.error("Select at least one column.")
                else:
                    with st.spinner("Comparing..."):
                        
                        # 1. PRIMARY MERGE (KEY MATCHING)
                        selected_tgt = [src_to_tgt_map[c] for c in selected_src]
                        df1_n = df1[selected_src].copy()
                        df2_n = df2[selected_tgt].copy()
                        df2_n.columns = selected_src # Align

                        for c in selected_src:
                            df1_n[c] = normalize_for_comparison(df1_n[c], opt_case_data, opt_trim)
                            df2_n[c] = normalize_for_comparison(df2_n[c], opt_case_data, opt_trim)

                        df1_n['_oid_src'] = df1.index
                        df2_n['_oid_tgt'] = df2.index

                        merged = pd.merge(df1_n, df2_n, on=selected_src, how='outer', indicator=True)

                        only_src = df1.loc[merged[merged['_merge']=='left_only']['_oid_src'].dropna()].reindex(columns=selected_src)
                        only_tgt = df2.loc[merged[merged['_merge']=='right_only']['_oid_tgt'].dropna()].reindex(columns=selected_tgt)
                        in_both  = df1.loc[merged[merged['_merge']=='both']['_oid_src'].dropna()].reindex(columns=selected_src)
                        
                        # 2. VALUE MISMATCH ANALYSIS (For matched rows only)
                        mismatch_df = pd.DataFrame()
                        value_cols = [c for c in common_cols_list if c not in selected_src]
                        
                        if value_cols and not in_both.empty:
                            matched_indices = merged[merged['_merge'] == 'both']
                            idx_src = matched_indices['_oid_src'].astype(int)
                            idx_tgt = matched_indices['_oid_tgt'].astype(int)
                            
                            v_df1 = df1.loc[idx_src, value_cols].reset_index(drop=True)
                            v_df2 = df2.loc[idx_tgt, value_cols].reset_index(drop=True)
                            v_df2.columns = [c if c in value_cols else src_to_tgt_map.get(c,c) for c in v_df2.columns] 
                            v_df2 = v_df2[value_cols]

                            mm_counts = []
                            for col in value_cols:
                                s1 = normalize_for_comparison(v_df1[col], opt_case_data, opt_trim)
                                s2 = normalize_for_comparison(v_df2[col], opt_case_data, opt_trim)
                                diff = (s1 != s2).sum()
                                if diff > 0:
                                    mm_counts.append({'Column': col, 'Mismatch Count': diff})
                            
                            mismatch_df = pd.DataFrame(mm_counts)
                            if not mismatch_df.empty:
                                mismatch_df = mismatch_df.sort_values(by='Mismatch Count', ascending=False)


                        # Stats
                        c_both = len(in_both)
                        c_src = len(only_src)
                        c_tgt = len(only_tgt)
                        total_union = c_both + c_src + c_tgt
                        match_pct = (c_both/total_union*100) if total_union else 0
                        diagnosis = get_diagnosis(match_pct)

                        # --- DISPLAY ON SCREEN SUMMARY ---
                        st.success("✅ Comparison Complete!")
                        
                        # Section 1: File Information
                        st.markdown('<div class="section-header">File Information</div>', unsafe_allow_html=True)
                        f1, f2, f3, f4 = st.columns(4)
                        f1.metric("Source File", src_file.name)
                        f2.metric("Source Total Rows", f"{total_src_rows:,}")
                        f3.metric("Target File", tgt_file.name)
                        f4.metric("Target Total Rows", f"{total_tgt_rows:,}")

                        # Section 2: Comparison Statistics
                        st.markdown('<div class="section-header">Comparison Statistics</div>', unsafe_allow_html=True)
                        s1, s2, s3, s4 = st.columns(4)
                        s1.metric("Rows in BOTH (Match)", f"{c_both:,}")
                        s2.metric("Rows ONLY in Source", f"{c_src:,}", delta="- Missing", delta_color="inverse")
                        s3.metric("Rows ONLY in Target", f"{c_tgt:,}", delta="+ New", delta_color="inverse")
                        s4.metric("Match Percentage", f"{match_pct:.2f}%")

                        # Section 3: Status
                        st.markdown('<div class="section-header">Mismatch Diagnosis</div>', unsafe_allow_html=True)
                        st.info(f"**Status:** {diagnosis}")

                        # Section 4: Mismatch Table (if exists)
                        if not mismatch_df.empty:
                            st.markdown('<div class="section-header">Mismatch Diagnosis (Ranked by Impact)</div>', unsafe_allow_html=True)
                            st.dataframe(
                                mismatch_df.set_index('Column'), 
                                use_container_width=True,
                                height=250
                            )

                        # --- GENERATE EXCEL (MATCHING IMAGE FORMAT) ---
                        buffer = BytesIO()
                        wb = Workbook()
                        wb.remove(wb.active)

                        # Styles
                        header_font = Font(name='Calibri', size=11, bold=True, color="FFFFFF")
                        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid") # Excel Blue
                        
                        def write_section_header(ws, r, title):
                            cell = ws.cell(row=r, column=1, value=title)
                            cell.font = header_font
                            cell.fill = header_fill
                            # Merge across A and B for header look
                            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
                            return r + 1

                        def write_kv_pair(ws, r, key, value):
                            # Column A: Bold Key
                            c1 = ws.cell(row=r, column=1, value=key)
                            c1.font = Font(bold=True)
                            # Column B: Value
                            c2 = ws.cell(row=r, column=2, value=value)
                            c2.alignment = Alignment(horizontal='left')
                            return r + 1

                        # 1. Executive Summary Sheet
                        ws_sum = wb.create_sheet("Executive Summary")
                        ws_sum.column_dimensions['A'].width = 35
                        ws_sum.column_dimensions['B'].width = 80
                        
                        row_ptr = 1
                        
                        # Section: File Information
                        row_ptr = write_section_header(ws_sum, row_ptr, "File Information")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Source File Name", src_file.name)
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Source Total Rows", f"{total_src_rows:,}")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Target File Name", tgt_file.name)
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Target Total Rows", f"{total_tgt_rows:,}")
                        row_ptr += 1 # Empty row

                        # Section: Comparison Statistics
                        row_ptr = write_section_header(ws_sum, row_ptr, "Comparison Statistics")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Rows in BOTH Files (Match)", f"{c_both:,}")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Rows ONLY in Source", f"{c_src:,}")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Rows ONLY in Target", f"{c_tgt:,}")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Match Percentage", f"{match_pct:.2f}%")
                        row_ptr += 1

                        # Section: Matching Configuration
                        row_ptr = write_section_header(ws_sum, row_ptr, "Matching Configuration")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Key Columns Selected", ", ".join(selected_src))
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Excluded Columns", "None") # Logic uses all common, explicit exclude not in UI yet
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Case Insensitive Data", str(opt_case_data))
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Trim Whitespace", str(opt_trim))
                        row_ptr += 1

                        # Section: Mismatch Diagnosis
                        row_ptr = write_section_header(ws_sum, row_ptr, "Mismatch Diagnosis (Ranked by Impact)")
                        row_ptr = write_kv_pair(ws_sum, row_ptr, "Status", diagnosis)
                        
                        # 2. Mismatch Contributors (Sorted High to Low)
                        if not mismatch_df.empty:
                            ws_mm = wb.create_sheet("Mismatch Contributors")
                            ws_mm.column_dimensions['A'].width = 40
                            ws_mm.column_dimensions['B'].width = 20
                            
                            # Header
                            h1 = ws_mm.cell(1, 1, "Column Name")
                            h2 = ws_mm.cell(1, 2, "Mismatch Count")
                            h1.font = header_font; h1.fill = header_fill
                            h2.font = header_font; h2.fill = header_fill
                            
                            for idx, row in mismatch_df.iterrows():
                                ws_mm.append([row['Column'], row['Mismatch Count']])

                        # 3. Detail Sheets (Core Logic Preserved)
                        if gen_col_sheet:
                            ws = wb.create_sheet("Column Names")
                            ws.append(["Column Name", "In Source", "In Target"])
                            for c in sorted(list(set(df1.columns) | set(df2.columns)), key=str):
                                ws.append([c, "Yes" if c in df1.columns else "No", "Yes" if c in df2.columns else "No"])

                        if gen_row_sheet:
                            ws = wb.create_sheet("Row Comparison")
                            ws.append(['Status'] + selected_src)
                            for _, row in only_src.iterrows(): ws.append(['Only in Source'] + row.astype(str).tolist())
                            for _, row in only_tgt.iterrows(): ws.append(['Only in Target'] + row.astype(str).tolist())
                            for _, row in in_both.iterrows(): ws.append(['In Both'] + row.astype(str).tolist())

                        if gen_uniq_sheet:
                            ws = wb.create_sheet("Unique Values")
                            col_idx = 1
                            for c in selected_src:
                                s_v = set(df1_n[c].dropna()[df1_n[c]!=''])
                                t_v = set(df2_n[c].dropna()[df2_n[c]!=''])
                                ws.cell(1, col_idx, c).font = Font(bold=True)
                                ws.cell(2, col_idx, "Only Source"); ws.cell(2, col_idx+1, "Only Target")
                                for i, v in enumerate(sorted(s_v - t_v), 3): ws.cell(i, col_idx, v)
                                for i, v in enumerate(sorted(t_v - s_v), 3): ws.cell(i, col_idx+1, v)
                                col_idx += 3

                        if gen_stats_sheet:
                            ws = wb.create_sheet("Summary Stats")
                            nums = [c for c in selected_src if pd.api.types.is_numeric_dtype(df1[c])]
                            col_idx = 1
                            for c in nums:
                                tgt_c = src_to_tgt_map.get(c,c)
                                ws.cell(1, col_idx, c).font = Font(bold=True)
                                ws.cell(2, col_idx, "Stat"); ws.cell(2, col_idx+1, "Src"); ws.cell(2, col_idx+2, "Tgt")
                                for i, s in enumerate(['count','sum','mean','min','max'], 3):
                                    ws.cell(i, col_idx, s)
                                    try: ws.cell(i, col_idx+1, getattr(df1[c], s)())
                                    except: pass
                                    try: ws.cell(i, col_idx+2, getattr(df2[tgt_c], s)())
                                    except: pass
                                col_idx += 4

                        wb.save(buffer)
                        buffer.seek(0)
                        
                        st.download_button(
                            label="📥 Download Full Report (Excel)",
                            data=buffer,
                            file_name=f"Comparison_Report_{datetime.datetime.now().strftime('%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

# --- 6. FOOTER ---
st.markdown("""
<div class="footer">
    Developed by <strong>Jithendra Reddy</strong> | 
    <a href="mailto:jithendrareddypunuru@gmail.com">jithendrareddypunuru@gmail.com</a> | 
    <a href="https://www.linkedin.com/in/jithendrareddypunuru/" target="_blank">LinkedIn Profile</a>
</div>
""", unsafe_allow_html=True)