import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
import io

# ---------------------------------------------------------
# 1. APPLICATION SETUP & GOOGLE SHEETS CONNECTION
# ---------------------------------------------------------
st.set_page_config(
    page_title="TSAL Aerospace Routing Explorer",
    page_icon="✈️",
    layout="wide"
)

SPREADSHEET_NAME = "Project sheet"
CREDENTIALS_FILE = "credentials.json"
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource(ttl=60)
def get_gspread_client():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPE)
    return gspread.authorize(creds)

def load_sheet_data():
    client = get_gspread_client()
    sheet = client.open(SPREADSHEET_NAME).worksheet("Sheet1")
    all_values = sheet.get_all_values()
    return sheet, all_values

def parse_yearly_data(raw_data):
    """
    Extracts the 3 distinct yearly blocks:
    2024: Columns A to AB (Indices 0 to 27)
    2025: Columns AE to BF (Indices 30 to 57)
    2026: Columns BI to CJ (Indices 60 to 87)
    """
    header_row = 1
    data_rows = raw_data[2:]

    def build_df(start_col, end_col, year_label):
        headers = [col.strip() for col in raw_data[header_row][start_col:end_col+1]]
        cleaned_headers = []
        for i, h in enumerate(headers):
            name = h if h else f"Col_{i}"
            cleaned_headers.append(name)
        
        rows = []
        sheet_row_indices = []
        for idx, r in enumerate(data_rows, start=3):
            sub_row = r[start_col:end_col+1]
            if len(sub_row) > 1 and sub_row[1].strip():
                rows.append(sub_row)
                sheet_row_indices.append(idx)
        
        df = pd.DataFrame(rows, columns=cleaned_headers)
        df["Year"] = year_label
        df["_SheetRowIndex"] = sheet_row_indices

        # Cast numeric fields safely
        numeric_cols = ["Setup", "M/C", "Labour", "Chnge over", "Total time", "Length(mm)", "Width(mm)", "Thickness(mm)  ", "Diameter(mm)", "Surface area (Sq Ft)", "Time per Sq Ft"]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace("%", "").str.strip(), errors="coerce").fillna(0.0)

        return df

    return build_df(0, 27, "2024"), build_df(30, 57, "2025"), build_df(60, 87, "2026")

# ---------------------------------------------------------
# 2. SESSION STATE & LOGIN PAGE
# ---------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.plant = None
    st.session_state.department = None

def login_page():
    st.title("✈️ Tata Sikorsky Aerospace Limited (TSAL)")
    st.subheader("Aerospace Manufacturing Master Portal")
    col1, _ = st.columns([1, 2])
    with col1:
        with st.form("login_form"):
            st.markdown("### Authentication")
            plant = st.selectbox("Select Plant", ["TSAL-2001", "TSAL-2002", "TSAL-HQ"])
            dept = st.selectbox("Select Department", ["IE", "Production", "Quality", "CAM/Tooling"])
            submit = st.form_submit_button("Access Portal", use_container_width=True)
            if submit:
                st.session_state.logged_in = True
                st.session_state.plant = plant
                st.session_state.department = dept
                st.rerun()

if not st.session_state.logged_in:
    login_page()
    st.stop()

# ---------------------------------------------------------
# 3. DATA LOAD & NAVIGATION
# ---------------------------------------------------------
sheet_obj, raw_sheet_values = load_sheet_data()
df_2024, df_2025, df_2026 = parse_yearly_data(raw_sheet_values)

st.sidebar.markdown(f"**Session:** `{st.session_state.plant} | {st.session_state.department}`")
if st.sidebar.button("Log Out"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.markdown("---")
view_mode = st.sidebar.radio(
    "Navigation Menu", 
    [
        "🔍 3-Year Comparison & Trends", 
        "📄 Export Shop Traveler (Excel)", 
        "➕ Add New Record (With Poka-Yoke)", 
        "🗑️ Delete Record"
    ]
)

# ---------------------------------------------------------
# FEATURE 1: 3-YEAR COMPARISON & INTERACTIVE CHARTS
# ---------------------------------------------------------
if view_mode == "🔍 3-Year Comparison & Trends":
    st.title("📊 Multi-Year Component Routing & Visual Trends")

    combined_df = pd.concat([df_2024, df_2025, df_2026], ignore_index=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        work_centers = sorted([wc for wc in combined_df["Work Center"].dropna().unique() if wc])
        selected_wc = st.selectbox("1️⃣ Work Center", options=work_centers)
    with col2:
        wc_records = combined_df[combined_df["Work Center"] == selected_wc]
        work_orders = sorted([wo for wo in wc_records["Work order no"].dropna().unique() if wo])
        selected_wo = st.selectbox("2️⃣ Work Order No", options=work_orders)
    with col3:
        wo_records = wc_records[wc_records["Work order no"] == selected_wo]
        part_numbers = sorted([p for p in wo_records["Part no"].dropna().unique() if p])
        selected_part = st.selectbox("3️⃣ Part Number", options=part_numbers)

    row_2024 = df_2024[(df_2024["Part no"] == selected_part) & (df_2024["Work Center"] == selected_wc)]
    row_2025 = df_2025[(df_2025["Part no"] == selected_part) & (df_2025["Work Center"] == selected_wc)]
    row_2026 = df_2026[(df_2026["Part no"] == selected_part) & (df_2026["Work Center"] == selected_wc)]

    # Top KPI Cards
    kpi1, kpi2, kpi3 = st.columns(3)
    t24 = row_2024['Total time'].values[0] if not row_2024.empty else 0
    t25 = row_2025['Total time'].values[0] if not row_2025.empty else 0
    t26 = row_2026['Total time'].values[0] if not row_2026.empty else 0

    with kpi1:
        st.metric("2024 Total Time", f"{t24:.1f} min", help=f"Rev: {row_2024['Rev no'].values[0] if not row_2024.empty else '-'}")
    with kpi2:
        delta_25 = round(t25 - t24, 1) if t24 > 0 and t25 > 0 else None
        st.metric("2025 Total Time", f"{t25:.1f} min", delta=f"{delta_25} min" if delta_25 else None, delta_color="inverse")
    with kpi3:
        delta_26 = round(t26 - t25, 1) if t25 > 0 and t26 > 0 else None
        st.metric("2026 Std Live Time", f"{t26:.1f} min", delta=f"{delta_26} min" if delta_26 else None, delta_color="inverse")

    st.markdown("---")

    # Interactive Charts
    st.subheader("📈 Cycle Time Analysis & Stage Breakdown")
    chart_col1, chart_col2 = st.columns(2)

    # Chart 1: Total Time Trend
    trend_data = pd.DataFrame({
        "Year": ["2024", "2025", "2026"],
        "Total Time (min)": [t24, t25, t26]
    })
    fig_bar = px.bar(
        trend_data, x="Year", y="Total Time (min)", 
        title=f"Total Cycle Time Trend for {selected_part}",
        text="Total Time (min)", color="Year",
        color_discrete_sequence=["#4A90E2", "#50E3C2", "#F5A623"]
    )
    fig_bar.update_layout(showlegend=False)
    chart_col1.plotly_chart(fig_bar, use_container_width=True)

    # Chart 2: Stacked Time Breakdown (Setup vs M/C vs Labour vs Changeover)
    def extract_time_stages(row):
        if row.empty:
            return 0, 0, 0, 0
        return row['Setup'].values[0], row['M/C'].values[0], row['Labour'].values[0], row['Chnge over'].values[0]

    s24, m24, l24, c24 = extract_time_stages(row_2024)
    s25, m25, l25, c25 = extract_time_stages(row_2025)
    s26, m26, l26, c26 = extract_time_stages(row_2026)

    fig_stack = go.Figure(data=[
        go.Bar(name='Setup', x=['2024', '2025', '2026'], y=[s24, s25, s26], marker_color='#E74C3C'),
        go.Bar(name='M/C Cutting', x=['2024', '2025', '2026'], y=[m24, m25, m26], marker_color='#3498DB'),
        go.Bar(name='Labour', x=['2024', '2025', '2026'], y=[l24, l25, l26], marker_color='#2ECC71'),
        go.Bar(name='Change Over', x=['2024', '2025', '2026'], y=[c24, c25, c26], marker_color='#F39C12')
    ])
    fig_stack.update_layout(barmode='stack', title=f"Operation Time Component Breakdown (min)")
    chart_col2.plotly_chart(fig_stack, use_container_width=True)

    # Comparison Grid
    st.subheader("📋 Specification & Engineering Metrics Comparison")
    grid_rows = []
    for yr_name, df_yr in [("Year 2024", row_2024), ("Year 2025", row_2025), ("Year 2026 (Live)", row_2026)]:
        if not df_yr.empty:
            r = df_yr.iloc[0].to_dict()
            grid_rows.append({
                "Year": yr_name,
                "Process": r.get("Process", ""),
                "Operation Code": r.get("Operation", r.get("Operatioon", "")),
                "Operation Description": r.get("Operation Short Text", ""),
                "Dimensions (LxWxT)": f"{r.get('Length(mm)',0)} x {r.get('Width(mm)',0)} x {r.get('Thickness(mm)  ',0)} mm",
                "Diameter": f"{r.get('Diameter(mm)',0)} mm",
                "Surface Area": f"{r.get('Surface area (Sq Ft)',0)} sq ft",
                "Perimeter": f"{r.get('Parimeter',0)} mm",
                "Batch Efficiency": r.get("Batch Efficiency ", ""),
                "Time / Sq Ft": f"{r.get('Time per Sq Ft',0)} min/sqft",
                "Revision": r.get("Rev no", ""),
                "Engineering Remark": r.get(" Remark", "")
            })
    st.dataframe(pd.DataFrame(grid_rows), use_container_width=True)

# ---------------------------------------------------------
# FEATURE 2: EXPORT SHOP FLOOR TRAVELER / EXCEL REPORT
# ---------------------------------------------------------
elif view_mode == "📄 Export Shop Traveler (Excel)":
    st.title("📄 Export Shop Floor Routing Traveler")
    st.markdown("Generate a clean, standardized Excel routing traveler ready for manufacturing shop-floor execution.")

    exp_year = st.selectbox("Select Target Year", ["Year 2024", "Year 2025", "Std Live Year 2026"])
    target_export_df = df_2024 if exp_year == "Year 2024" else (df_2025 if exp_year == "Year 2025" else df_2026)

    selected_wc_filter = st.multiselect("Filter by Work Center (Optional)", options=target_export_df["Work Center"].unique(), default=target_export_df["Work Center"].unique())
    export_subset = target_export_df[target_export_df["Work Center"].isin(selected_wc_filter)].copy()
    
    # Drop internal helper columns
    export_subset = export_subset.drop(columns=["_SheetRowIndex"], errors="ignore")

    st.write(f"Previewing **{len(export_subset)} records** for download:")
    st.dataframe(export_subset.head(10), use_container_width=True)

    # Generate Excel in memory
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        export_subset.to_excel(writer, index=False, sheet_name=exp_year)
    excel_data = excel_buffer.getvalue()

    st.download_button(
        label=f"📥 Download {exp_year} Routing Sheet (.xlsx)",
        data=excel_data,
        file_name=f"TSAL_{exp_year.replace(' ', '_')}_Traveler.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )

# ---------------------------------------------------------
# FEATURE 3: ADD NEW RECORD WITH POKA-YOKE INPUT VALIDATION
# ---------------------------------------------------------
elif view_mode == "➕ Add New Record (With Poka-Yoke)":
    st.title("➕ Add Manufacturing Routing Record")
    st.info(f"Adding record under **{st.session_state.plant}** | Dept: **{st.session_state.department}**")
    
    target_year = st.selectbox("Select Target Year Table", ["Year 2024", "Year 2025", "Std Live Year 2026"])

    with st.form("poka_yoke_add_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            part_no = st.text_input("Part Number (e.g., xxxxxxxxxx101)")
            cell = st.selectbox("Cell", ["Cell-01", "Cell-02", "Cell-03", "Cell-04"])
            machine_fam = st.selectbox("Machine Family", ["Modig", "Mazak", "Jyoti", "Makino", "DMG Mori"])
            work_center = st.selectbox("Work Center", ["MS-01-11", "MS-01-12", "AW-02-03", "AE-02-06", "MK-03-01", "DM-04-02"])
            work_order = st.text_input("Work Order No", "WO-2026-1101")
        
        with c2:
            shape = st.selectbox("Shape", ["Rectangular", "Cylindrical"])
            length = st.number_input("Length (mm)", value=450.0, step=10.0)
            width = st.number_input("Width (mm)", value=180.0, step=10.0)
            thickness = st.number_input("Thickness (mm)", value=25.0, step=1.0)
            diameter = st.number_input("Diameter (mm)", value=0.0, step=5.0)
            process = st.text_input("Process", "Adaptive Dynamic Profiling")
            op_code = st.text_input("Operation Code", "OP-020")
            op_text = st.text_input("Operation Short Text", "Aero Profile Machining")

        with c3:
            setup = st.number_input("Setup Time (min)", value=30.0, step=1.0)
            mc_time = st.number_input("M/C Time (min)", value=45.0, step=1.0)
            labour = st.number_input("Labour Time (min)", value=18.0, step=1.0)
            changeover = st.number_input("Change Over (min)", value=12.0, step=1.0)
            efficiency = st.slider("Batch Efficiency (%)", 70.0, 100.0, 92.0)
            rev_no = st.selectbox("Revision Level", ["R00", "R01", "R02", "R03", "R04", "R05"])
            remark = st.text_input("Engineering Remark", "S-92 Flight ready sign-off")

        submitted = st.form_submit_button("Validate & Append to Google Sheet", type="primary")

        if submitted:
            # POKA-YOKE VALIDATION RULES
            validation_errors = []

            if not part_no.strip():
                validation_errors.append("Part Number cannot be blank.")
            
            if shape == "Rectangular":
                if length <= 0 or width <= 0 or thickness <= 0:
                    validation_errors.append("Rectangular parts require positive Length, Width, and Thickness.")
                if diameter != 0:
                    validation_errors.append("Rectangular parts must have Diameter = 0.")
            elif shape == "Cylindrical":
                if diameter <= 0 or thickness <= 0:
                    validation_errors.append("Cylindrical parts require positive Diameter and Thickness.")

            if setup < 0 or mc_time < 0 or labour < 0 or changeover < 0:
                validation_errors.append("Cycle times cannot be negative.")

            total_calc_time = round(setup + mc_time + labour + changeover, 1)
            if total_calc_time == 0:
                validation_errors.append("Total cycle time must be greater than 0.")

            # Display errors if validation fails
            if validation_errors:
                for err in validation_errors:
                    st.error(f"❌ Validation Block: {err}")
            else:
                # Calculations
                if diameter > 0:
                    surf_area = round((3.14159 * (diameter / 2) ** 2) / 92903.04, 3)
                    perimeter = round(3.14159 * diameter, 1)
                else:
                    surf_area = round((length * width) / 92903.04, 3)
                    perimeter = round(2 * (length + width), 1)

                time_per_sqft = round(total_calc_time / surf_area, 2) if surf_area > 0 else 0

                # Anomaly warning
                if time_per_sqft > 600:
                    st.warning(f"⚠️️ Anomaly Warning: Time per Sq Ft is high ({time_per_sqft} min/sqft). Please verify feeds and speeds.")

                # Target table offset
                year_col_offset = 1 if target_year == "Year 2024" else (31 if target_year == "Year 2025" else 61)
                next_row = len(raw_sheet_values) + 1
                sno = len(df_2024) + 1

                new_row_values = [
                    sno, part_no, st.session_state.plant, st.session_state.department,
                    cell, "Machine", machine_fam, length, width, thickness, diameter,
                    surf_area, perimeter, shape, f"{efficiency}%", time_per_sqft,
                    process, work_center, work_order, op_code, op_text,
                    setup, mc_time, labour, changeover, total_calc_time, rev_no, remark
                ]

                start_cell_a1 = gspread.utils.rowcol_to_a1(next_row, year_col_offset)
                end_cell_a1 = gspread.utils.rowcol_to_a1(next_row, year_col_offset + len(new_row_values) - 1)
                cell_range = f"{start_cell_a1}:{end_cell_a1}"

                sheet_obj.update(range_name=cell_range, values=[new_row_values])
                st.success(f"✅ Part passed validation! Appended to {target_year} at row {next_row}.")
                st.cache_resource.clear()

# ---------------------------------------------------------
# VIEW 4: DELETE RECORD
# ---------------------------------------------------------
elif view_mode == "🗑️ Delete Record":
    st.title("🗑️ Delete Recorded Manufacturing Row")
    st.warning("⚠️ Action will clear the selected record from the Google Sheet.")

    target_year = st.selectbox("Select Year Table", ["Year 2024", "Year 2025", "Std Live Year 2026"])
    active_df = df_2024 if target_year == "Year 2024" else (df_2025 if target_year == "Year 2025" else df_2026)

    selected_part_to_del = st.selectbox("Select Part to Delete", active_df["Part no"].unique())
    matching_rows = active_df[active_df["Part no"] == selected_part_to_del]

    st.write("Matching Rows Found:")
    st.dataframe(matching_rows[["SNo", "Part no", "Work Center", "Process", "Total time", "Rev no", "_SheetRowIndex"]])

    sheet_row_to_delete = st.selectbox("Select Exact Sheet Row Index to Delete", matching_rows["_SheetRowIndex"].values)

    if st.button("Confirm and Delete Record", type="primary"):
        year_col_start = 1 if target_year == "Year 2024" else (31 if target_year == "Year 2025" else 61)
        year_col_end = year_col_start + 27
        start_cell = gspread.utils.rowcol_to_a1(sheet_row_to_delete, year_col_start)
        end_cell = gspread.utils.rowcol_to_a1(sheet_row_to_delete, year_col_end)
        
        sheet_obj.batch_clear([f"{start_cell}:{end_cell}"])
        st.success(f"Row {sheet_row_to_delete} cleared for {target_year}!")
        st.cache_resource.clear()
        st.rerun()