import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import datetime

# --- 1. Helper Functions (Logic from your original App) ---

def normalize_for_comparison(series, is_case_insensitive, should_trim):
    """Standardizes data for comparison."""
    s_numeric = pd.to_numeric(series, errors='coerce')
    s = series.where(s_numeric.isna(), s_numeric)
    s = pd.to_datetime(s, errors='coerce').dt.strftime('%Y-%m-%d').fillna(s)
    s = s.astype(str)
    s = s.str.replace(r'\.0$', '', regex=True)
    s_lower_for_nulls = s.str.lower().str.strip()
    s[s_lower_for_nulls.isin(['nan', '<na>', 'none', 'nat', ''])] = ''
    
    if should_trim:
        s = s.str.strip().str.replace(r'\s+', ' ', regex=True) 
    if is_case_insensitive:
        s = s.str.lower()
    return s

def load_data(file, header_row, sheet_name=None):
    """Reads the file uploaded by the user."""
    try:
        if file.name.endswith(('.xlsx', '.xls', '.xlsm')):
            return pd.read_excel(file, header=header_row, sheet_name=sheet_name)
        elif file.name.endswith('.csv'):
            return pd.read_csv(file, header=header_row, encoding='utf-8-sig')
        elif file.name.endswith('.tsv'):
            return pd.read_csv(file, header=header_row, sep='\t', encoding='utf-8-sig')
        else:
            return pd.read_csv(file, header=header_row) # Fallback
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

# --- 2. The Web App Interface ---

st.set_page_config(page_title="Flat File Comparator", layout="wide")
st.title("📂 Flat File Comparison Tool")
st.markdown("Upload two files (Excel or CSV) to compare them row-by-row without writing code.")

# Layout: Two columns for inputs
col1, col2 = st.columns(2)

with col1:
    st.subheader("Source File")
    src_file = st.file_uploader("Upload Source", type=["xlsx", "xls", "csv", "tsv"], key="src")
    src_header = st.number_input("Header Row (Source)", min_value=1, value=1, key="h1") - 1
    
    src_sheet = None
    if src_file and src_file.name.endswith(('xlsx', 'xls', 'xlsm')):
        xl_file = pd.ExcelFile(src_file)
        if len(xl_file.sheet_names) > 1:
            src_sheet = st.selectbox("Select Source Sheet", xl_file.sheet_names, key="s1")
        else:
            src_sheet = xl_file.sheet_names[0]

with col2:
    st.subheader("Target File")
    tgt_file = st.file_uploader("Upload Target", type=["xlsx", "xls", "csv", "tsv"], key="tgt")
    tgt_header = st.number_input("Header Row (Target)", min_value=1, value=1, key="h2") - 1

    tgt_sheet = None
    if tgt_file and tgt_file.name.endswith(('xlsx', 'xls', 'xlsm')):
        xl_file = pd.ExcelFile(tgt_file)
        if len(xl_file.sheet_names) > 1:
            tgt_sheet = st.selectbox("Select Target Sheet", xl_file.sheet_names, key="s2")
        else:
            tgt_sheet = xl_file.sheet_names[0]

# Options
st.divider()
st.subheader("Settings")
c1, c2, c3 = st.columns(3)
case_insensitive_cols = c1.checkbox("Case-Insensitive Columns", value=True)
case_insensitive_data = c2.checkbox("Case-Insensitive Data", value=True)
trim_whitespace = c3.checkbox("Trim Whitespace", value=True)

# --- 3. Processing Logic ---

if src_file and tgt_file:
    # Reset file pointers to beginning before reading
    src_file.seek(0)
    tgt_file.seek(0)

    df1 = load_data(src_file, src_header, src_sheet)
    df2 = load_data(tgt_file, tgt_header, tgt_sheet)

    if df1 is not None and df2 is not None:
        st.info(f"Loaded: Source ({len(df1)} rows) | Target ({len(df2)} rows)")

        # Column Matching Logic
        if case_insensitive_cols:
            src_map = {str(c).lower(): c for c in df1.columns}
            tgt_map = {str(c).lower(): c for c in df2.columns}
            common_lower = set(src_map.keys()) & set(tgt_map.keys())
            common_cols = [src_map[k] for k in common_lower]
            src_to_tgt_map = {src_map[k]: tgt_map[k] for k in common_lower}
        else:
            common_cols = list(set(df1.columns) & set(df2.columns))
            src_to_tgt_map = {c: c for c in common_cols}

        if not common_cols:
            st.error("No common columns found between the files!")
        else:
            selected_cols = st.multiselect("Select Key Columns for Comparison", common_cols, default=common_cols)

            if st.button("Run Comparison", type="primary"):
                if not selected_cols:
                    st.error("Please select at least one column.")
                else:
                    with st.spinner("Comparing files..."):
                        # Prepare data
                        selected_tgt = [src_to_tgt_map.get(c, c) for c in selected_cols]
                        df1_n = df1[selected_cols].copy()
                        df2_n = df2[selected_tgt].copy()
                        df2_n.columns = selected_cols # Rename target cols to match source

                        # Normalize
                        for c in selected_cols:
                            df1_n[c] = normalize_for_comparison(df1_n[c], case_insensitive_data, trim_whitespace)
                            df2_n[c] = normalize_for_comparison(df2_n[c], case_insensitive_data, trim_whitespace)

                        df1_n['_oid_src'] = df1.index
                        df2_n['_oid_tgt'] = df2.index

                        # Merge
                        merged = pd.merge(df1_n, df2_n, on=selected_cols, how='outer', indicator=True)

                        only_src_ids = merged[merged['_merge']=='left_only']['_oid_src'].dropna()
                        only_tgt_ids = merged[merged['_merge']=='right_only']['_oid_tgt'].dropna()
                        both_ids = merged[merged['_merge']=='both']['_oid_src'].dropna()

                        only_src = df1.loc[only_src_ids]
                        only_tgt = df2.loc[only_tgt_ids]
                        in_both = df1.loc[both_ids]

                        # --- Ranked Diagnosis (Simplified for Web) ---
                        impact_msg = ""
                        if len(only_src) > 0 and len(selected_cols) > 1:
                            src_fail = merged[merged['_merge'] == 'left_only'][selected_cols]
                            tgt_fail = merged[merged['_merge'] == 'right_only'][selected_cols]
                            
                            best_col = None
                            max_save = 0
                            
                            for col_to_drop in selected_cols:
                                temp_cols = [c for c in selected_cols if c != col_to_drop]
                                if not temp_cols: continue
                                src_sigs = src_fail[temp_cols].set_index(temp_cols).index
                                tgt_sigs = tgt_fail[temp_cols].set_index(temp_cols).index
                                saved_count = src_sigs.isin(tgt_sigs).sum()
                                if saved_count > max_save:
                                    max_save = saved_count
                                    best_col = col_to_drop
                            
                            if best_col:
                                impact_msg = f"Tip: Ignoring '{best_col}' would fix {max_save} mismatches."

                        # --- Generate Excel in Memory ---
                        output = BytesIO()
                        wb = Workbook()
                        wb.remove(wb.active)

                        # Executive Summary
                        ws_sum = wb.create_sheet("Executive Summary")
                        data = [
                            ["Metric", "Value"],
                            ["Source Rows", len(df1)],
                            ["Target Rows", len(df2)],
                            ["Matched Rows", len(in_both)],
                            ["Only in Source", len(only_src)],
                            ["Only in Target", len(only_tgt)],
                            ["Match %", f"{len(in_both)/(len(in_both)+len(only_src)+len(only_tgt))*100:.2f}%"]
                        ]
                        for row in data: ws_sum.append(row)
                        if impact_msg: ws_sum.append(["Diagnosis", impact_msg])

                        # Row Comparison
                        ws_rows = wb.create_sheet("Row Comparison")
                        # Add headers
                        headers = ['Status'] + list(df1.columns)
                        ws_rows.append(headers)
                        
                        # Add Data (Limited to 10k rows for web performance safety, or full if you prefer)
                        for _, row in only_src.iterrows(): ws_rows.append(['Only Source'] + row.tolist())
                        for _, row in only_tgt.iterrows(): ws_rows.append(['Only Target'] + row.tolist())
                        
                        wb.save(output)
                        output.seek(0)

                        st.success("Comparison Complete!")
                        st.metric("Match Percentage", f"{len(in_both)/(len(in_both)+len(only_src)+len(only_tgt))*100:.2f}%")
                        if impact_msg: st.warning(impact_msg)

                        st.download_button(
                            label="📥 Download Comparison Report (Excel)",
                            data=output,
                            file_name=f"comparison_report_{datetime.datetime.now().strftime('%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )