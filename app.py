import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import streamlit_js_eval

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Giro Visite CRM Pro", layout="wide")

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2))

@st.cache_data(ttl=60)
def fetch_data(url):
    try:
        df = pd.read_csv(url, sep=None, engine='python')
        df.columns = df.columns.str.strip().str.lower()
        colonne_crm = ['contatto', 'referente', 'posizione referente', 'mail', 'telefono', 'cellulare', 'note', 'visitare']
        for col in colonne_crm:
            if col not in df.columns: df[col] = ""
        for c in ['latitude', 'longitude', 'frequenza (giorni)']:
            if c in df.columns: df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'), errors='coerce')
        df['visitare'] = df['visitare'].replace("", "SI").fillna("SI").astype(str).str.upper()
        df['ultima visita'] = pd.to_datetime(df['ultima visita'], dayfirst=True, errors='coerce')
        return df.dropna(subset=['nome cliente', 'latitude', 'longitude'])
    except: return pd.DataFrame()

# --- 2. STATO DELL'APP ---
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")

# Database dei Report (Cronologia)
if 'df_reports' not in st.session_state:
    st.session_state.df_reports = pd.DataFrame(columns=['cliente', 'data', 'nota_visita', 'esito'])

if 'start_lat' not in st.session_state: st.session_state.start_lat, st.session_state.start_lon = 43.1924, 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio, st.session_state.h_fine = time(9, 0), time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA DI CALCOLO ---
def genera_agenda():
    if st.session_state.df_master.empty: return {}, datetime.now()
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_s = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            dt_l = st.session_state.spostamenti.get(dt_c, dt_c)
            df_s['g_p'] = (pd.to_datetime(dt_l) - df_s['ultima visita']).dt.days.fillna(999)
            urg = df_s[(df_s['visitare'] == 'SI') & (df_s['g_p'] >= df_s['frequenza (giorni)'])].to_dict('records')
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                dist = haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])
                arr = o_s + timedelta(minutes=(dist/50)*60)
                if (arr + timedelta(minutes=st.session_state.durata_v)) <= datetime.combine(dt_c, st.session_state.h_fine):
                    px['ora'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(px)
                    df_s.loc[df_s['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_l)
                    o_s, p_s = arr + timedelta(minutes=st.session_state.durata_v), (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return piano, lun_ref

# --- 4. INTERFACCIA ---
if not st.session_state.df_master.empty:
    piano, lun_base = genera_agenda()
    t_oggi, t_sett, t_ana, t_nuovo, t_par = st.tabs(["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"])

    with t_oggi:
        st.header(f"📍 Giro di Oggi")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = piano["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora']}** - {t['nome cliente']}")
                            st.caption(f"👤 {t.get('referente','')} | 📞 {t.get('cellulare','')}")
                            
                            col_b1, col_b2 = st.columns(2)
                            col_b1.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                            
                            # Funzione Report Visita
                            with col_b2.popover("📝 Report"):
                                with st.form(f"report_{t['nome cliente']}"):
                                    esito = st.selectbox("Esito", ["Positivo", "Da richiamare", "Negativo", "Solo Consegna"], key=f"es_{t['nome cliente']}")
                                    nota = st.text_area("Cosa è successo durante la visita?", key=f"no_{t['nome cliente']}")
                                    if st.form_submit_button("Salva e Concludi"):
                                        # 1. Aggiungi alla cronologia
                                        nuovo_rep = {'cliente': t['nome cliente'], 'data': datetime.now().strftime("%d/%m/%Y %H:%M"), 'nota_visita': nota, 'esito': esito}
                                        st.session_state.df_reports = pd.concat([st.session_state.df_reports, pd.DataFrame([nuovo_rep])], ignore_index=True)
                                        # 2. Aggiorna data ultima visita nel master
                                        idx_m = st.session_state.df_master[st.session_state.df_master['nome cliente'] == t['nome cliente']].index[0]
                                        st.session_state.df_master.at[idx_m, 'ultima visita'] = pd.to_datetime(datetime.now().date())
                                        st.success("Report salvato!")
                                        st.rerun()
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita programmata.")

    with t_ana:
        st.header("👤 Anagrafica e Cronologia")
        cerca = st.text_input("🔍 Cerca cliente:", "").lower()
        lista = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        if lista:
            scelto = st.selectbox("Seleziona:", lista)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            
            # Visualizzazione Report Vecchi
            st.subheader("📜 Cronologia Report Visite")
            reps = st.session_state.df_reports[st.session_state.df_reports['cliente'] == scelto].sort_index(ascending=False)
            if not reps.empty:
                for _, r in reps.iterrows():
                    with st.expander(f"📅 {r['data']} - Esito: {r['esito']}"):
                        st.write(r['nota_visita'])
            else: st.caption("Nessun report precedente per questo cliente.")
            
            st.divider()
            with st.form("edit_crm_full"):
                st.subheader("⚙️ Modifica Dati Base")
                c1, c2 = st.columns(2)
                with c1:
                    un = st.text_input("Nome", d['nome cliente']); ui = st.text_input("Indirizzo", d['indirizzo'])
                    um = st.text_input("Mail", d.get('mail','')); uc = st.text_input("Cellulare", d.get('cellulare',''))
                with c2:
                    uf = st.number_input("Freq (gg)", value=int(d['frequenza (giorni)']))
                    ur = st.text_input("Referente", d.get('referente','')); up = st.text_input("Posizione", d.get('posizione referente',''))
                    uv = st.toggle("Abilita nel Giro", value=(d['visitare'] == 'SI'))
                if st.form_submit_button("💾 Salva Anagrafica"):
                    st.session_state.df_master.at[idx, 'nome cliente'], st.session_state.df_master.at[idx, 'indirizzo'] = un, ui
                    st.session_state.df_master.at[idx, 'mail'], st.session_state.df_master.at[idx, 'cellulare'] = um, uc
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'], st.session_state.df_master.at[idx, 'referente'] = uf, ur
                    st.session_state.df_master.at[idx, 'posizione referente'], st.session_state.df_master.at[idx, 'visitare'] = up, ('SI' if uv else 'NO')
                    st.success("Salvato!"); st.rerun()

    with t_nuovo:
        st.header("➕ Nuovo Cliente")
        with st.form("nuovo_crm"):
            nn = st.text_input("Ragione Sociale *")
            ni = st.text_input("Indirizzo")
            nf = st.number_input("Frequenza (gg)", value=30)
            if st.form_submit_button("✅ Aggiungi"):
                if nn:
                    rigo = {'nome cliente': nn, 'indirizzo': ni, 'frequenza (giorni)': nf, 'visitare': 'SI', 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([rigo])], ignore_index=True)
                    st.success(f"{nn} inserito!"); st.rerun()

    with t_par:
        st.header("⚙️ Parametri")
        st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
        if st.button("Reset Totale"):
            st.cache_data.clear()
            del st.session_state.df_master; st.rerun()
else: st.error("Carica il foglio Google.")
