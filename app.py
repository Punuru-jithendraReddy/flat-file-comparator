import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import datetime
import time

# --- 1. CONFIG & CUSTOM COLORS ---
st.set_page_config(page_title="Flat File Comparison Tool", layout="wide")

# Inject Custom CSS for Green Button and Blue Tags
st.markdown("""
    <style>
    /* 1. Make the 'Run Comparison' button GREEN */
    div.stButton > button {
        background-color: #28a745 !important; 
        color: white !important;
        border-color: #28a745 !important;
        font-weight: bold !important;
    }
    div.stButton > button:hover {
        background-color: #218838 !important;
        border-color: #1e7e34 !important;
    }

    /* 2. Make the Multiselect (Key Columns) tags BLUE */
    span[data-baseweb="tag"] {
        background-color: #007bff !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE LOGIC ---

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
            prog_text = st.empty()
            prog_text.caption(f"Scanning {len(xls.sheet_names)} sheets in {file_obj.name}...")
            
            for sheet in xls.sheet_names:
                try:
                    temp_df = pd.read_excel(file_obj, sheet_name=sheet, header=header_row)
                    if len(temp_df) > max_rows:
                        max_rows = len(temp_df)
                        best_df = temp_df
                except: continue
            
            prog_text.empty() # Clear message
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

# --- 3. UI LAYOUT ---

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

# B. Configuration
st.divider()
with st.expander("⚙️ Advanced Settings", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Matching Logic**")
        opt_case_cols = st.checkbox("Case-Insensitive Columns", value=True)
        opt_case_data = st.checkbox("Case-Insensitive Data", value=True)
        opt_trim = st.checkbox("Trim Whitespace", value=True)
    with c2:
        st.markdown("**Output Sheets**")
        gen_row_sheet = st.checkbox("Row Comparison", value=True)
        gen_col_sheet = st.checkbox("Column Analysis", value=True)
    with c3:
        st.markdown("**Stats**")
        gen_uniq_sheet = st.checkbox("Unique Values", value=True)
        gen_stats_sheet = st.checkbox("Summary Stats", value=True)

# --- 4. EXECUTION ---

if src_file and tgt_file:
    st.divider()
    st.subheader("📋 Column Selection")
    
    src_file.seek(0); tgt_file.seek(0)
    
    with st.spinner("Analyzing files..."):
        df1 = smart_read_file(src_file, src_header)
        df2 = smart_read_file(tgt_file, tgt_header)

    if df1 is not None and df2 is not None:
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
            selected_src = st.multiselect(
                "Select Key Columns (Unique Identifiers)", 
                options=sorted(common_cols_list, key=str),
                default=sorted(common_cols_list, key=str)
            )

            if st.button("🚀 Run Comparison", type="primary"):
                if not selected_src:
                    st.error("Select at least one column.")
                else:
                    start_time = time.time()
                    with st.spinner("Comparing..."):
                        
                        # Prepare Data
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
                        
                        # Stats
                        c_both, c_src, c_tgt = len(in_both), len(only_src), len(only_tgt)
                        total = c_both + c_src + c_tgt
                        match_pct = (c_both/total*100) if total else 0

                        # --- DISPLAY ON SCREEN SUMMARY ---
                        st.success("✅ Comparison Complete!")
                        st.divider()
                        st.subheader("📊 Executive Summary")
                        
                        # Metrics Row
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Total Rows", f"{total:,}")
                        m2.metric("Match Percentage", f"{match_pct:.2f}%")
                        m3.metric("Only in Source", f"{c_src:,}", delta_color="inverse")
                        m4.metric("Only in Target", f"{c_tgt:,}", delta_color="inverse")

                        # Preview Data Table
                        st.write("#### Mismatch Preview")
                        preview_data = pd.DataFrame({
                            "Category": ["Rows Only in Source", "Rows Only in Target", "Matches"],
                            "Count": [c_src, c_tgt, c_both]
                        })
                        st.bar_chart(preview_data.set_index("Category"))

                        # --- GENERATE EXCEL ---
                        buffer = BytesIO()
                        wb = Workbook()
                        wb.remove(wb.active)

                        # Styles
                        title_font = Font(size=14, bold=True, color="FFFFFF")
                        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
                        bold = Font(bold=True)

                        # 1. Executive Summary Sheet
                        ws_sum = wb.create_sheet("Executive Summary")
                        ws_sum.column_dimensions['A'].width = 30; ws_sum.column_dimensions['B'].width = 50
                        r = 1
                        def write_kv(k, v, r, is_header=False):
                            if is_header:
                                cell = ws_sum.cell(row=r, column=1, value=k)
                                cell.font = title_font; cell.fill = header_fill
                                ws_sum.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
                            else:
                                ws_sum.cell(row=r, column=1, value=k).font = bold
                                ws_sum.cell(row=r, column=2, value=v)
                            return r + 1

                        r = write_kv("File Information", "", r, True)
                        r = write_kv("Source File", src_file.name, r)
                        r = write_kv("Target File", tgt_file.name, r)
                        r += 1
                        r = write_kv("Comparison Statistics", "", r, True)
                        r = write_kv("Match Percentage", f"{match_pct:.2f}%", r)
                        r = write_kv("Matched Rows", f"{c_both:,}", r)
                        r = write_kv("Rows Only in Source", f"{c_src:,}", r)
                        r = write_kv("Rows Only in Target", f"{c_tgt:,}", r)

                        # 2. Detail Sheets
                        if gen_col_sheet:
                            ws = wb.create_sheet("Column Names")
                            ws.append(["Column Name", "In Source", "In Target"])
                            for c in sorted(list(set(df1.columns) | set(df2.columns)), key=str):
                                ws.append([c, "Yes" if c in df1.columns else "No", "Yes" if c in df2.columns else "No"])

                        if gen_row_sheet:
                            ws = wb.create_sheet("Row Comparison")
                            ws.append(['Status'] + selected_src)
                            # Limit preview for speed if needed, but writing full here
                            for _, row in only_src.iterrows(): ws.append(['Only in Source'] + row.astype(str).tolist())
                            for _, row in only_tgt.iterrows(): ws.append(['Only in Target'] + row.astype(str).tolist())
                            for _, row in in_both.iterrows(): ws.append(['In Both'] + row.astype(str).tolist())

                        if gen_uniq_sheet:
                            ws = wb.create_sheet("Unique Values")
                            col_idx = 1
                            for c in selected_src:
                                s_v = set(df1_n[c].dropna()[df1_n[c]!=''])
                                t_v = set(df2_n[c].dropna()[df2_n[c]!=''])
                                ws.cell(1, col_idx, c).font = bold
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
                                ws.cell(1, col_idx, c).font = bold
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