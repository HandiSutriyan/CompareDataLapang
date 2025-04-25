import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime

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
    
    #std_df = std_df.drop(columns='Unnamed: 21') #hapus kolom lebih
    std_df = std_df.drop([0])
    std_df.columns = set_col_std #ubah format header standar

    status_cols = [col for col in std_df.columns if col.lower().startswith("stat")]
    exclude_cols_std = ['timestamp'] + status_cols
    std_df = convert_columns_to_float(std_df, exclude_cols_std)


    return std_df

def interpolate(x):
    return x
def find_correction(x):
    return x

st.set_page_config(page_title="Kalibrasi Data Tools", layout="wide")
st.title("🛠️ Tools Kalibrasi & Perbandingan Data CSV")

st.markdown("""
Alat ini membandingkan data kalibrasi antara alat **standar** dan **unit under test (UUT)**.
""")


# --- Upload File ---
st.sidebar.header("📂 Upload Data")
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

    exclude_cols_uut = ['Date and Time']
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

    header_mapping = {}
    for i in range(min(len(std_headers), len(uut_headers))):
        std_col = st.selectbox(f"Header Standar #{i+1}", options=["-"] + std_headers, key=f"std_{i}")
        uut_col = st.selectbox(f"Header UUT #{i+1}", options=["-"] + uut_headers, key=f"uut_{i}")
        if std_col != "-" and uut_col != "-":
            header_mapping[std_col] = uut_col


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
    for std_col, uut_col in header_mapping.items():
        if std_col in df_merged.columns and uut_col in df_merged.columns:
            st.write(f"### Perbandingan: {std_col} vs {uut_col}")

            fig, ax = plt.subplots(figsize=(10, 5))
            sns.lineplot(x=df_merged[ts_col_std], y=df_merged[std_col], label=f"Standar - {std_col}", ax=ax, linewidth=2.5)
            sns.lineplot(x=df_merged[ts_col_std], y=df_merged[uut_col], label=f"UUT - {uut_col}", ax=ax, linewidth=2.5)

            y_max = max(df_merged[std_col].max(), df_merged[uut_col].max()) + 10
            ax.set_ylim(0, y_max)
            ax.set_title(f"Tren {std_col} dan {uut_col}")
            ax.legend()
            ax.grid(True)
            plt.xticks(rotation=45)
            st.pyplot(fig)

            df_merged[f"koreksi_{std_col}"] = df_merged[uut_col] - df_merged[std_col]
            st.write(df_merged[[ts_col_std, std_col, uut_col, f"koreksi_{std_col}"].copy()])
else:
    st.info("📁 Silakan upload kedua file CSV terlebih dahulu.")