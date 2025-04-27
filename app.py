import os
import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import interp1d
import json

with open('correction.json', 'r') as f:
    DB_KOREKSI = json.load(f)

UNIT_LIST = ["hPa","InHg","m/s","knot"]

def convert_columns_to_float(df, exclude_cols):
    for col in df.columns:
        if col not in exclude_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def clean_std_df(std_df):
    set_col_std = ['timestamp', 'statP', 'PressureMeas_1m', 'statTA',
       'TAStat155_1m_1', 'statRH', 'RHStat155_1m_1', 'statSR',
       'SRMeasQMS101R_1m', 'StatPR', 'PRMeasQMR101_1', 'StatQFE',
       'QFE_1m', 'StatQNH', 'QNH_1m', 'StatWS', 'WS_1m',
       'StatWD', 'WD_1m', 'StatTG', 'TGMeasQMT103_1m']
    
    std_df = std_df.drop(columns='Unnamed: 21') #hapus kolom lebih
    std_df = std_df.drop([0])
    std_df.columns = set_col_std #ubah format header standar

    status_cols = [col for col in std_df.columns if col.lower().startswith("stat")]
    exclude_cols_std = ['timestamp'] + status_cols
    std_df = convert_columns_to_float(std_df, exclude_cols_std)

    return std_df

# Fungsi konversi satuan
def convert_unit(value, from_unit, to_unit):
    if from_unit == to_unit or "-" in (from_unit, to_unit):
        return value
    if from_unit == "InHg" and to_unit == "hPa":
        return value * 33.8639
    if from_unit == "hPa" and to_unit == "InHg":
        return value / 33.8639
    if from_unit == "m/s" and to_unit == "knot":
        return value / 0.514444
    if from_unit == "knot" and to_unit == "m/s":
        return value * 0.514444
    return value


def cari_koreksi_scipy(id_aws, parameter, nilai_baca):
    
    daftar_koreksi = DB_KOREKSI[id_aws][parameter]
    daftar_koreksi = sorted(daftar_koreksi, key=lambda x: x['setpoin'])
    
    setpoints = [item['setpoin'] for item in daftar_koreksi]
    koreksis = [item['koreksi'] for item in daftar_koreksi]

    interpolator = interp1d(
        setpoints,
        koreksis,
        kind='linear',
        fill_value=(koreksis[0], koreksis[-1]),  # Extrapolasi jika di luar range
        bounds_error=False
    )

    koreksi = interpolator(nilai_baca)
    return koreksi


st.set_page_config(page_title="Kalibrasi Data Tools", layout="wide")
st.title("🛠️ Tools Kalibrasi & Perbandingan Data CSV")

st.markdown("""
Alat ini membandingkan data kalibrasi antara alat **standar** dan **unit under test (UUT)**.
""")


# --- Upload File ---
st.sidebar.header("📂 Upload Data")
id_std = st.sidebar.selectbox("ID AWS Standar yang digunakan", options= list(DB_KOREKSI.keys()))
standard_files = st.sidebar.file_uploader("Upload CSV Alat Standar (bisa lebih dari satu)", type=["csv"], accept_multiple_files=True)
uut_file = st.sidebar.file_uploader("Upload CSV UUT", type=["csv"])

st.sidebar.markdown("---")
if st.sidebar.button("❌ Shutdown Aplikasi"):
    st.sidebar.warning("🚨 Aplikasi akan dihentikan...")
    st.stop()  # Menghentikan eksekusi Streamlit (opsional)
    os._exit(0)  # Menghentikan proses Python

if standard_files and uut_file:
    df_standard_list = [pd.read_csv(f) for f in standard_files]
    df_standard = pd.concat(df_standard_list, ignore_index=True)
    df_uut = pd.read_csv(uut_file)

    df_standard = clean_std_df(df_standard)

    exclude_cols_uut = df_uut.columns[0]
    df_uut = convert_columns_to_float(df_uut, exclude_cols_uut)

    st.subheader("📋 Pratinjau Data")
    st.write("### Data Alat Standar")
    st.dataframe(df_standard.head())
    st.write("### Data UUT")
    st.dataframe(df_uut.head())

    # --- Pembersihan Header ---
    st.subheader("🧹 Pembersihan Data Alat Standar")
    cols_to_drop = st.multiselect("Pilih kolom yang tidak akan digunakan", df_standard.columns)
    if cols_to_drop:
        df_standard = df_standard.drop(columns=cols_to_drop)

    # Hapus baris INVALID
    status_cols = [col for col in df_standard.columns if col.lower().startswith("stat")]
    remove_invalid = st.checkbox("Hapus baris dengan status INVALID di kolom status", value=True)
    if remove_invalid and status_cols:
        invalid_mask = df_standard[status_cols].apply(lambda row: row.str.upper().str.contains("INVALID"), axis=1).any(axis=1)
        df_standard = df_standard[~invalid_mask]

    #Inisialisasi header
    std_headers = df_standard.columns.tolist()
    uut_headers = df_uut.columns.tolist()

    # --- Konversi Timestamp ---
    st.subheader("🕒 Sinkronisasi Waktu")
    ts_col_std = st.selectbox("Pilih kolom timestamp alat standar", std_headers)
    ts_col_uut = st.selectbox("Pilih kolom timestamp UUT", uut_headers)

    time_format_std = st.text_input("Format waktu alat standar", value="%m/%d/%y %I:%M:%S %p")
    time_format_uut = st.text_input("Format waktu UUT", value="%d/%m/%Y %H:%M:%S")  # <<== perbaikan format

    try:
        df_standard[ts_col_std] = pd.to_datetime(df_standard[ts_col_std], format=time_format_std, errors='coerce')
        df_uut[ts_col_uut] = pd.to_datetime(df_uut[ts_col_uut], format=time_format_uut, errors='coerce', dayfirst=True)

        # Hapus baris dengan timestamp yang gagal dikonversi
        df_standard = df_standard.dropna(subset=[ts_col_std])
        df_uut = df_uut.dropna(subset=[ts_col_uut])

        st.success("✅ Timestamp berhasil dikonversi.")
    except Exception as e:
        st.error(f"❌ Gagal mengonversi waktu: {e}")

    # --- Header Mapping ---
    st.subheader("🔀 Mapping Header untuk Perbandingan")
    exclude_options_std = status_cols + [ts_col_std]
    option_std = list(filter(lambda x: x not in exclude_options_std, std_headers))
    option_uut = list(filter(lambda x: x != ts_col_uut, uut_headers))

    header_mapping = {}
    st.divider()
    tt_std = st.selectbox(f"Header Suhu Standar", ["-"] + option_std, key="tt_std")
    tt_uut = st.selectbox(f"Header Suhu UUT",["-"] + option_uut, key="tt_uut")
    if tt_std != "-" and tt_uut != "-":
        header_mapping[tt_std] = tt_uut
        df_standard[f"koreksi-{tt_std}"] = df_standard[tt_std].apply(lambda x: cari_koreksi_scipy(id_std, "TT", x))
        df_standard[f"{tt_std}-terkoreksi"] = df_standard[tt_std] + df_standard[f"koreksi-{tt_std}"]

    st.divider()
    rh_std = st.selectbox(f"Header Kelembapan Standar",["-"] + option_std, key="rh_std")
    rh_uut = st.selectbox(f"Header Kelembapan UUT",["-"] + option_uut, key="rh_uut")
    if rh_std != "-" and rh_uut != "-":
        header_mapping[rh_std] = rh_uut
        df_standard[f"koreksi-{rh_std}"] = df_standard[rh_std].apply(lambda x: cari_koreksi_scipy(id_std, "RH", x))
        df_standard[f"{rh_std}-terkoreksi"] = df_standard[rh_std] + df_standard[f"koreksi-{rh_std}"]

    st.divider()
    pp_std = st.selectbox(f"Header Tekanan Standar",["-"] + option_std, key="pp_std")
    pp_uut = st.selectbox(f"Header Tekanan UUT",["-"] + option_uut, key="pp_uut")
    konversi_pp = st.checkbox("Konversi satuan UUT InHg ke hPa", value=False)
    if pp_std != "-" and pp_uut != "-":
        header_mapping[pp_std] = pp_uut
        df_standard[f"koreksi-{pp_std}"] = df_standard[pp_std].apply(lambda x: cari_koreksi_scipy(id_std, "PP", x))
        df_standard[f"{pp_std}-terkoreksi"] = df_standard[pp_std] + df_standard[f"koreksi-{pp_std}"]
        if konversi_pp:
            df_uut[pp_uut] = df_uut[pp_uut].apply(lambda x: convert_unit(x, "InHg", "hPa"))
    
    st.divider()
    ws_std = st.selectbox(f"Header Kec. Angin Standar",["-"] + option_std, key="ws_std")
    ws_uut = st.selectbox(f"Header Kec. Angin UUT",["-"] + option_uut, key="ws_uut")
    konversi_ws = st.checkbox("Konversi satuan UUT knot ke m/s", value=False)
    if ws_std != "-" and ws_uut != "-":
        header_mapping[ws_std] = ws_uut
        df_standard[f"koreksi-{ws_std}"] = df_standard[ws_std].apply(lambda x: cari_koreksi_scipy(id_std, "WS", x))
        df_standard[f"{ws_std}-terkoreksi"] = df_standard[ws_std] + df_standard[f"koreksi-{ws_std}"]
        if konversi_ws:
            df_uut[ws_uut] = df_uut[ws_uut].apply(lambda x: convert_unit(x, "knot", "m/s"))
    
    st.divider()
    wd_std = st.selectbox(f"Header Arah Angin Standar",["-"] + option_std, key="wd_std")
    wd_uut = st.selectbox(f"Header Arah Angin UUT",["-"] + option_uut, key="wd_uut")
    if wd_std != "-" and wd_uut != "-":
        header_mapping[wd_std] = wd_uut
        df_standard[f"koreksi-{wd_std}"] = df_standard[wd_std].apply(lambda x: cari_koreksi_scipy(id_std, "WD", x))
        df_standard[f"{wd_std}-terkoreksi"] = df_standard[wd_std] + df_standard[f"koreksi-{wd_std}"]
    
    st.divider()
    sr_std = st.selectbox(f"Header Radiasi Matahari Standar",["-"] + option_std, key="sr_std")
    sr_uut = st.selectbox(f"Header Radiasi Matahari UUT",["-"] + option_uut, key="sr_uut")
    if sr_std != "-" and sr_uut != "-":
        header_mapping[sr_std] = sr_uut
        df_standard[f"{sr_std}-terkoreksi"] = df_standard[sr_std]

    st.divider()
    tw_std = st.selectbox(f"Header Suhu Air Standar",["-"] + option_std, key="tw_std")
    tw_uut = st.selectbox(f"Header Suhu Air UUT",["-"] + option_uut, key="tw_uut")
    if tw_std != "-" and tw_uut != "-":
        header_mapping[tw_std] = tw_uut
        df_standard[f"koreksi-{tw_std}"] = df_standard[tw_std].apply(lambda x: cari_koreksi_scipy(id_std, "WT", x))
        df_standard[f"{tw_std}-terkoreksi"] = df_standard[tw_std] + df_standard[f"koreksi-{tw_std}"]

    #header_mapping = {}
    # for i in range(min(len(std_headers), len(uut_headers))):
    #     std_col = st.selectbox(f"Header Standar #{i+1}", options=["-"] + std_headers, key=f"std_{i}")
    #     uut_col = st.selectbox(f"Header UUT #{i+1}", options=["-"] + uut_headers, key=f"uut_{i}")
    #     if std_col != "-" and uut_col != "-":
    #         header_mapping[std_col] = uut_col

    
    # --- Sinkronisasi Timestamp dan Gabung ---
    df_standard_sorted = df_standard.sort_values(ts_col_std)
    df_uut_sorted = df_uut.sort_values(ts_col_uut)

    df_merged = pd.merge_asof(
        df_standard_sorted,
        df_uut_sorted,
        left_on=ts_col_std,
        right_on=ts_col_uut,
        direction='nearest',
        tolerance=pd.Timedelta('1min')
    )

    # Hapus baris yang memiliki nilai kosong pada kolom hasil mapping
    cols_to_check = list(header_mapping.keys()) + list(header_mapping.values())
    df_merged = df_merged.dropna(subset=cols_to_check)
    st.subheader("📊 Visualisasi dan Koreksi")
    tabs = st.tabs(header_mapping.keys())
    for tab, param_col in zip(tabs,header_mapping.items()):
        std_col = param_col[0]
        uut_col = param_col[1]
        with tab:
            if std_col in df_merged.columns and uut_col in df_merged.columns:
                tab.write(f"### Perbandingan: {std_col} vs {uut_col}")

                if uut_col.lower().startswith("wd"):
                    df_merged[f"koreksi_{uut_col}"] = (df_merged[f"{std_col}-terkoreksi"] - df_merged[uut_col] + 180) % 360 -180
                else:
                    df_merged[f"koreksi_{uut_col}"] = df_merged[f"{std_col}-terkoreksi"] - df_merged[uut_col]
                
                col1, col2, col3 = tab.columns(3)
                col1.metric(f"Mean {std_col}", f"{df_merged[f"{std_col}-terkoreksi"].mean():.2f}",f"{df_merged[f"{std_col}-terkoreksi"].std():.2g}", border=True)
                col2.metric(f"Mean {uut_col}", f"{df_merged[uut_col].mean():.2f}", f"{df_merged[uut_col].std():.2g}", border=True)
                col3.metric(f"Koreksi {uut_col}", f"{df_merged[f"koreksi_{uut_col}"].mean():.2g}",f"{df_merged[f"koreksi_{uut_col}"].std():.2g}",border=True)

                tab.line_chart(
                    df_merged, 
                    x=ts_col_std, 
                    y=[f"{std_col}-terkoreksi",uut_col],
                    )
                
                #Buat Unduhan untuk Grafik
                fig, ax = plt.subplots(figsize=(10, 7))
                sns.lineplot(x=df_merged[ts_col_std], y=df_merged[f"{std_col}-terkoreksi"], label=f"Standar", ax=ax, linewidth=2.5)
                sns.lineplot(x=df_merged[ts_col_std], y=df_merged[uut_col], label=f"UUT", ax=ax, linewidth=2.5)

                ax.set_title(f"Tren {std_col} dan {uut_col}")
                ax.legend()
                ax.grid(True)
                plt.xticks(rotation=45)
                
                buf = io.BytesIO()
                fig.savefig(buf, format="png")
                buf.seek(0)
                tab.download_button(label="Unduh Grafik (PNG)",data=buf,file_name=f"grafik_tren_{std_col}_vs_{uut_col}",mime="image/png")
                if std_col.lower().startswith("sr"):
                    df_summary = df_merged[[ts_col_std, f"{std_col}", uut_col, f"koreksi_{uut_col}"].copy()]
                else:
                    df_summary = df_merged[[ts_col_std, f"{std_col}",f"koreksi-{std_col}",f"{std_col}-terkoreksi", uut_col, f"koreksi_{uut_col}"].copy()]
                tab.write(df_summary)

            
else:
    st.info("📁 Silakan upload kedua file CSV terlebih dahulu.")