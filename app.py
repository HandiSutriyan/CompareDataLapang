import os
import io
import streamlit as st

from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import interp1d
import json
import openpyxl

with open('correction.json', 'r') as f:
    DB_KOREKSI = json.load(f)

UNIT_LIST = ["hPa","InHg","m/s","knot"]
UUT_LOGGER = ["CS","Vaisala/AWI"]

def convert_columns_to_float(df, exclude_cols):
    for col in df.columns:
        if col not in exclude_cols:
            try:
                df[col] = df[col].str.replace(',', '.').astype(float) #konversi desimal yang pakai koma
            except (ValueError, AttributeError):
                df[col] = pd.to_numeric(df[col], errors='coerce') #konversi desimal yang pakai titik
    return df

def clean_std_df(input_df):
    std_df = input_df.copy()
    std_df.columns = std_df.columns.str.strip()
    new_header = []
    for i, col in enumerate(std_df.columns):
        if 'Unnamed' in col and i > 0:
            next_col = std_df.columns[i+1] if i+1 < len(std_df.columns) else ''
            new_header.append(f'Stat_{next_col}')
        elif i == 0:
            new_header.append('Timestamp')
        else:
            new_header.append(col)
    
    std_df.columns = new_header #ubah format header standar
    std_df = std_df.dropna(axis=1,how='all') #hapus kolom lebih
    std_df = std_df.drop([0]).reset_index(drop=True) #hapus baris lebih

    std_df_cols = std_df.columns
    status_std_cols = [col for col in std_df_cols if col.lower().startswith("stat")]

    #Hapus kolom dari sensor yang tidak terpakai (kolom invalid)
    invalid_stat_columns = [col for col in status_std_cols if (std_df[col] == "INVALID").all()]

    sensor_columns_to_drop = [
        col.replace('Stat_', '') for col in invalid_stat_columns 
        if col.replace('Stat_', '') in std_df_cols
    ]

    drop_cols = invalid_stat_columns + sensor_columns_to_drop
    std_df = std_df.drop(columns=drop_cols)

    #Hapus baris data yang invalid
    status_std_cols = [col for col in status_std_cols if col not in invalid_stat_columns]
    if status_std_cols:
        invalid_mask = std_df[status_std_cols].apply(lambda row: row.str.upper().str.contains("INVALID"), axis=1).any(axis=1)
        std_df = std_df[~invalid_mask]
    
    #Konversi data numerik ke float
    exclude_cols_std = [std_df.columns[0]] + status_std_cols
    std_df = convert_columns_to_float(std_df, exclude_cols_std)

    return std_df

# Fungsi konversi satuan
def convert_unit(value, from_unit, to_unit):
    if from_unit == to_unit or "-" in (from_unit, to_unit):
        return value
    if from_unit == "InHg" and to_unit == "hPa":
        return value * 33.86388
    if from_unit == "hPa" and to_unit == "InHg":
        return value / 33.86388
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


st.set_page_config(page_title="Kalibrasi AWOS", layout="wide")
st.title("🛠️ Kalibrasi & Perbandingan Data")

st.markdown("""
Alat ini membandingkan data kalibrasi antara alat **standar** dan **unit under test (UUT)**.
""")


# --- Upload File ---
st.logo('logo-bmkg.png',size="large", icon_image='logo-bmkg.png')
st.sidebar.header("Laboratorium Kalibrasi BMKG Pusat")
st.sidebar.divider()
st.sidebar.subheader("📂 Upload Data")
id_std = st.sidebar.selectbox("ID AWS Standar yang digunakan", options= list(DB_KOREKSI.keys()))
standard_files = st.sidebar.file_uploader("Upload CSV Alat Standar (bisa lebih dari satu)", type=["csv"], accept_multiple_files=True)
id_logger = st.sidebar.selectbox("Jenis Logger UUT", options= list(UUT_LOGGER))
uut_file = st.sidebar.file_uploader("Upload CSV UUT", type=["csv"])

st.sidebar.markdown("---")
if st.sidebar.button("❌ Shutdown Aplikasi"):
    st.sidebar.warning("🚨 Aplikasi akan dihentikan...")
    st.stop()  # Menghentikan eksekusi Streamlit (opsional)
    os._exit(0)  # Menghentikan proses Python

if standard_files and uut_file:
    df_standard_list = [pd.read_csv(f, sep=None, engine='python') for f in standard_files]
    df_standard = pd.DataFrame()
    
    #Cleaning data setiap file
    for df in df_standard_list:
        clean_df = clean_std_df(df)
        df_standard = pd.concat([df_standard,clean_df], ignore_index=True)

    std_df_cols = df_standard.columns
    status_std_cols = [col for col in std_df_cols if col.lower().startswith("stat")]

    #Logger UUT
    if id_logger == "CS":
        df_uut = pd.read_csv(uut_file,sep=None, engine='python', skiprows=1, header=0)
        df_uut = df_uut.drop([0,1])
    else:
        df_uut = pd.read_csv(uut_file,sep=None, engine='python')
        
    df_uut.dropna(axis=1, how='all').reset_index(drop=True)

    exclude_cols_uut = df_uut.columns[:2]
    df_uut = convert_columns_to_float(df_uut, exclude_cols_uut)

    st.subheader("📋 Pratinjau Data")
    st.write("### Data Alat Standar")
    st.dataframe(df_standard.head())
    st.write("### Data UUT")
    st.dataframe(df_uut.head())

    #Inisialisasi header
    std_headers = df_standard.columns.tolist()
    uut_headers = df_uut.columns.tolist()

    # --- Konversi Timestamp ---
    st.subheader("🕒 Sinkronisasi Waktu")
    with st.expander("Ubahsuai sinkronisasi format waktu"):
        col_t_std,col_f_std = st.columns(2)
        col_t_uut,col_f_uut = st.columns(2)

        ts_col_std = col_t_std.selectbox("Pilih kolom timestamp alat standar", std_headers)
        ts_col_uut = col_t_uut.selectbox("Pilih kolom timestamp UUT", uut_headers)

        time_format_std = col_f_std.text_input("Format waktu alat standar", value="%m/%d/%y %I:%M:%S %p")
        time_format_uut = col_f_uut.text_input("Format waktu UUT", value="%d/%m/%Y %H:%M:%S")  # <<== perbaikan format

    try:
        df_standard[ts_col_std] = pd.to_datetime(df_standard[ts_col_std], format=time_format_std, errors='coerce')
        df_uut[ts_col_uut] = pd.to_datetime(df_uut[ts_col_uut], format=time_format_uut, errors='coerce', dayfirst=True)

        # Hapus baris dengan timestamp yang gagal dikonversi
        df_standard = df_standard.dropna(subset=[ts_col_std])
        df_uut = df_uut.dropna(subset=[ts_col_uut])

        st.success("✅ Timestamp berhasil dikonversi.")
    except Exception as e:
        st.error(f"❌ Gagal mengonversi waktu: {e}")

    #Pemetaan header
    status_cols = [col for col in df_standard.columns if col.lower().startswith("stat")]   
    exclude_options_std = status_cols + [ts_col_std]
    option_std = list(filter(lambda x: x not in exclude_options_std, std_headers))
    option_uut = list(filter(lambda x: x != ts_col_uut, uut_headers))


    # --- Pembersihan Header ---
    st.subheader("🧹 Pembersihan Kolom Data")
    with st.expander("Klik jika ingin menghapus kolom yang tidak diperlukan"):
        cols_to_drop = st.multiselect("Pilih kolom Standar yang tidak akan digunakan", option_std)
        if cols_to_drop:
            df_standard = df_standard.drop(columns=cols_to_drop)
            option_std = [col for col in option_std if col not in cols_to_drop]
        
        cols_uut_drop = st.multiselect("Pilih kolom UUT yang tidak akan digunakan", option_uut)
        if cols_uut_drop:
            df_uut = df_uut.drop(columns=cols_uut_drop)
            option_uut = [col for col in option_uut if col not in cols_uut_drop]

    # --- Header Mapping ---
    st.subheader("🔀 Mapping Header untuk Perbandingan")

    header_mapping = {}
    
    col_t,col_rh= st.columns(2)
    col_t.subheader("🌡Suhu Udara")
    tt_std = col_t.selectbox(f"Header Suhu Standar", ["-"] + option_std, key="tt_std")
    tt_uut = col_t.selectbox(f"Header Suhu UUT",["-"] + option_uut, key="tt_uut")
    if tt_std != "-" and tt_uut != "-":
        header_mapping[tt_std] = tt_uut
        df_standard[f"koreksi-{tt_std}"] = df_standard[tt_std].apply(lambda x: cari_koreksi_scipy(id_std, "TT", x))
        df_standard[f"{tt_std}-terkoreksi"] = df_standard[tt_std] + df_standard[f"koreksi-{tt_std}"]

    col_rh.subheader("💦 Kelembapan")
    rh_std = col_rh.selectbox(f"Header Kelembapan Standar",["-"] + option_std, key="rh_std")
    rh_uut = col_rh.selectbox(f"Header Kelembapan UUT",["-"] + option_uut, key="rh_uut")
    if rh_std != "-" and rh_uut != "-":
        header_mapping[rh_std] = rh_uut
        df_standard[f"koreksi-{rh_std}"] = df_standard[rh_std].apply(lambda x: cari_koreksi_scipy(id_std, "RH", x))
        df_standard[f"{rh_std}-terkoreksi"] = df_standard[rh_std] + df_standard[f"koreksi-{rh_std}"]

    col_p,col_ws = st.columns(2)
    col_p.subheader("🎈 Tekanan")
    pp_std = col_p.selectbox(f"Header Tekanan Standar",["-"] + option_std, key="pp_std")
    pp_uut = col_p.selectbox(f"Header Tekanan UUT",["-"] + option_uut, key="pp_uut")
    konversi_pp = col_p.checkbox("Konversi satuan UUT InHg ke hPa", value=False)
    if pp_std != "-" and pp_uut != "-":
        header_mapping[pp_std] = pp_uut
        df_standard[f"koreksi-{pp_std}"] = df_standard[pp_std].apply(lambda x: cari_koreksi_scipy(id_std, "PP", x))
        df_standard[f"{pp_std}-terkoreksi"] = df_standard[pp_std] + df_standard[f"koreksi-{pp_std}"]
        if konversi_pp:
            df_uut[pp_uut] = df_uut[pp_uut].apply(lambda x: convert_unit(x, "InHg", "hPa"))
    
    col_ws.subheader("🍃 Kecepatan Angin")
    ws_std = col_ws.selectbox(f"Header Kec. Angin Standar",["-"] + option_std, key="ws_std")
    ws_uut = col_ws.selectbox(f"Header Kec. Angin UUT",["-"] + option_uut, key="ws_uut")
    konversi_ws = col_ws.checkbox("Konversi satuan UUT knot ke m/s", value=False)
    if ws_std != "-" and ws_uut != "-":
        header_mapping[ws_std] = ws_uut
        df_standard[f"koreksi-{ws_std}"] = df_standard[ws_std].apply(lambda x: cari_koreksi_scipy(id_std, "WS", x))
        df_standard[f"{ws_std}-terkoreksi"] = df_standard[ws_std] + df_standard[f"koreksi-{ws_std}"]
        if konversi_ws:
            df_uut[ws_uut] = df_uut[ws_uut].apply(lambda x: convert_unit(x, "knot", "m/s"))
    
    col_wd,col_sr = st.columns(2)
    col_wd.subheader("🌬 Arah Angin")
    wd_std = col_wd.selectbox(f"Header Arah Angin Standar",["-"] + option_std, key="wd_std")
    wd_uut = col_wd.selectbox(f"Header Arah Angin UUT",["-"] + option_uut, key="wd_uut")
    if wd_std != "-" and wd_uut != "-":
        header_mapping[wd_std] = wd_uut
        df_standard[f"koreksi-{wd_std}"] = df_standard[wd_std].apply(lambda x: cari_koreksi_scipy(id_std, "WD", x))
        df_standard[f"{wd_std}-terkoreksi"] = df_standard[wd_std] + df_standard[f"koreksi-{wd_std}"]
    
    col_sr.subheader("☀️ Radiasi Matahari")
    sr_std = col_sr.selectbox(f"Header Radiasi Matahari Standar",["-"] + option_std, key="sr_std")
    sr_uut = col_sr.selectbox(f"Header Radiasi Matahari UUT",["-"] + option_uut, key="sr_uut")
    if sr_std != "-" and sr_uut != "-":
        header_mapping[sr_std] = sr_uut
        df_standard[f"{sr_std}-terkoreksi"] = df_standard[sr_std]

    col_wt,col_wpanci = st.columns(2)
    col_wt.subheader("🌊 Suhu Air")
    tw_std = col_wt.selectbox(f"Header Suhu Air Standar",["-"] + option_std, key="tw_std")
    tw_uut = col_wt.selectbox(f"Header Suhu Air UUT",["-"] + option_uut, key="tw_uut")
    if tw_std != "-" and tw_uut != "-":
        header_mapping[tw_std] = tw_uut
        df_standard[f"koreksi-{tw_std}"] = df_standard[tw_std].apply(lambda x: cari_koreksi_scipy(id_std, "WT", x))
        df_standard[f"{tw_std}-terkoreksi"] = df_standard[tw_std] + df_standard[f"koreksi-{tw_std}"]
    
    col_wpanci.subheader("🍃 Kec. Angin Panci")
    wpanci_std = col_wpanci.selectbox(f"Header Suhu Air Standar",["-"] + option_std, key="wpanci_std")
    wpanci_uut = col_wpanci.selectbox(f"Header Suhu Air UUT",["-"] + option_uut, key="wpanci_uut")
    if wpanci_std != "-" and wpanci_uut != "-":
        header_mapping[wpanci_std] = wpanci_uut
        df_standard[f"koreksi-{wpanci_std}"] = df_standard[wpanci_std].apply(lambda x: cari_koreksi_scipy(id_std, "WS", x))
        df_standard[f"{wpanci_std}-terkoreksi"] = df_standard[wpanci_std] + df_standard[f"koreksi-{wpanci_std}"]


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
    df_merged = df_merged.dropna(subset=cols_to_check).reset_index(drop=True)

    time_list = df_merged[ts_col_std]
    if len(time_list) != 0 :
        st.subheader("🕒 Rentang Data")
        st.write("Pilih rentang waktu")
        available_times = df_merged[ts_col_std].dt.strftime('%H:%M').unique().tolist()
        #st.write(available_times)
        col_t1,col_t2 = st.columns(2)
        start_date = col_t1.date_input("Tanggal mulai:",value= time_list.min().date(), min_value=time_list.min().date(), max_value=time_list.max().date())
        start_time = col_t2.selectbox("Pilih waktu", available_times, key="start_time")

        end_date = col_t1.date_input("Tanggal selesai:", value=df_merged[ts_col_std].max().date(), min_value=time_list.min().date(), max_value=time_list.max().date())
        end_time = col_t2.selectbox("Pilih waktu", available_times,index=len(available_times)-1, key="end_time")

        start_datetime = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
        df_merged_filtered = df_merged[(df_merged[ts_col_std] >= start_datetime)&((df_merged[ts_col_std] <= end_datetime))].reset_index(drop=True)
        st.write(f'ℹ️ Data dipilih mulai {start_datetime} sampai {end_datetime}')
        #st.dataframe(df_merged_filtered)

    st.subheader("📊 Hasil Kalibrasi Sementara per Parameter")
    if len(header_mapping) != 0:
        # if "lhks_df" not in st.session_state:
        #     st.session_state.lhks_df = []
        lhks_df = pd.DataFrame()
        tabs = st.tabs(header_mapping.keys())
        count = 0
        for tab, param_col in zip(tabs,header_mapping.items()):
            std_col = param_col[0]
            uut_col = param_col[1]
            with tab:
                if std_col in df_merged_filtered.columns and uut_col in df_merged_filtered.columns:
                    tab.write(f"### Perbandingan: {std_col} vs {uut_col}")

                    if uut_col.lower().startswith("wd"):
                        df_merged_filtered[f"koreksi_{uut_col}"] = (df_merged_filtered[f"{std_col}-terkoreksi"] - df_merged_filtered[uut_col] + 180) % 360 -180
                    else:
                        df_merged_filtered[f"koreksi_{uut_col}"] = df_merged_filtered[f"{std_col}-terkoreksi"] - df_merged_filtered[uut_col]
                    
                    col1, col2, col3 = tab.columns(3)
                    col1.metric(f"Rata-rata Standar", f"{df_merged_filtered[f"{std_col}-terkoreksi"].mean():.2f}",f"{df_merged_filtered[f"{std_col}-terkoreksi"].std():.2g}", border=True)
                    col2.metric(f"Rata-rata UUT", f"{df_merged_filtered[uut_col].mean():.2f}", f"{df_merged_filtered[uut_col].std():.2g}", border=True)
                    col3.metric(f"Koreksi", f"{df_merged_filtered[f"koreksi_{uut_col}"].mean():.2g}",f"{df_merged_filtered[f"koreksi_{uut_col}"].std():.2g}",border=True)

                    tab.line_chart(
                        df_merged_filtered, 
                        x=ts_col_std, 
                        y=[f"{std_col}-terkoreksi",uut_col],
                        )
                    
                    #Buat Unduhan untuk Grafik
                    fig, ax = plt.subplots(figsize=(15, 7))
                    sns.lineplot(x=df_merged_filtered[ts_col_std], y=df_merged_filtered[f"{std_col}-terkoreksi"], label=f"Standar", ax=ax, linewidth=2.5)
                    sns.lineplot(x=df_merged_filtered[ts_col_std], y=df_merged_filtered[uut_col], label=f"UUT", ax=ax, linewidth=2.5)

                    ax.set_title(f"Tren {std_col} dan {uut_col}")
                    ax.legend()
                    ax.grid(True)
                    plt.xticks(rotation=45)
                    #st.pyplot(fig)
                 
                    # Konversi DataFrame ke CSV string
                    if std_col.lower().startswith("sr"):
                        df_summary = df_merged_filtered[[ts_col_std, f"{std_col}", uut_col, f"koreksi_{uut_col}"]].copy()
                    else:
                        df_summary = df_merged_filtered[[ts_col_std, f"{std_col}",f"koreksi-{std_col}",f"{std_col}-terkoreksi", uut_col, f"koreksi_{uut_col}"]].copy()

                    buf = io.BytesIO()
                    fig.savefig(buf, format="png")
                    buf.seek(0)

                    csv_buffer = io.BytesIO()
                    with pd.ExcelWriter(csv_buffer, engine='openpyxl') as writer:
                        df_summary.to_excel(writer, index=False, sheet_name='Data')
                        csv_buffer.seek(0)
                
                    # Tombol download
                    col_btn1,col_btn2,spacer = tab.columns([1, 1, 3])
                    with col_btn1:
                        col_btn1.download_button(label="📈 Unduh Grafik",data=buf,file_name=f"grafik_tren_{uut_col}.png",mime="image/png", key=f'excel-{std_col}')
                    with col_btn2:
                        col_btn2.download_button(label="📄 Unduh Tabel", data=csv_buffer, file_name=f"data-komparasi-{uut_col}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f'data-{std_col}')

                    with tab.expander("Lihat tabel komparasi"):
                        st.dataframe(df_summary)

                    #Himpuun df_summary
                    if count > 0:
                        cut_time = df_summary.drop(columns='Timestamp')
                        lhks_df= pd.concat([lhks_df,cut_time],axis=1) 
                    else:
                        df_summary = df_summary.add_suffix(f'_{count}')
                        lhks_df= pd.concat([lhks_df,df_summary],axis=1) 
                    count += 1    
                    # st.write(count) 
        
        #Membuat Dataframe Gabungan
        st.subheader("📊 Hasil Kalibrasi Sementara Gabungan")
        now_stamp = datetime.now().strftime('%d%m%Y-%H%M%S')
        summary_buffer = io.BytesIO()
        with pd.ExcelWriter(summary_buffer, engine='openpyxl') as writer:
                lhks_df.to_excel(writer, index=False, sheet_name='Data Gabungan')
                summary_buffer.getvalue()

        with st.expander("Klik untuk mengunduh data gabungan"):
            filename = st.text_input("Mau dinamain apa filenya?")
            if filename != '':
                st.download_button(label="📄 Unduh File", data=summary_buffer, file_name=f"{now_stamp}-{filename}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
           
        st.dataframe(lhks_df)        
else:
    st.info("📁 Silakan upload kedua file CSV terlebih dahulu.")