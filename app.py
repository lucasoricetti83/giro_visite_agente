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
if 'df_reports' not in st.session_state:
    st.session_state.df_reports = pd.DataFrame(columns=['cliente', 'data', 'nota_visita', 'esito'])

if 'start_lat' not in st.session_state: st.session_state.start_lat, st.session_state.start_lon = 43.1924, 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio, st.session_state.h_fine = time(9, 0), time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA CALCOLO 8 SETTIMANE (SIMULATORE) ---
def calcola_piano_8_settimane():
    if st.session_state.df_master.empty: return {}, datetime.now()
    
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_sim = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    
    for s in range(1, 9):
        for g in range(5):
            dt_attuale = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            # Gestione scambio giorni dai parametri
            dt_logica = st.session_state.spostamenti.get(dt_attuale, dt_attuale)
            
            df_sim['g_passati'] = (pd.to_datetime(dt_logica) - df_sim['ultima visita']).dt.days.fillna(999)
            urgenti = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_passati'] >= df_sim['frequenza (giorni)'])].to_dict('records')
            
            ora_s = datetime.combine(dt_attuale, st.session_state.h_inizio)
            limite_s = datetime.combine(dt_attuale, st.session_state.h_fine)
            pos_s = (st.session_state.start_lat, st.session_state.start_lon)
            
            while urgenti:
                px = min(urgenti, key=lambda x: haversine(pos_s[0], pos_s[1], x['latitude'], x['longitude']))
                dist = haversine(pos_s[0], pos_s[1], px['latitude'], px['longitude'])
                arr = ora_s + timedelta(minutes=(dist/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                
                if fine <= limite_s:
                    info = px.copy()
                    info['ora_arrivo'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(info)
                    # Fondamentale: aggiorna l'ultima visita simulata per il prossimo calcolo
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_logica)
                    ora_s, pos_s = fine, (px['latitude'], px['longitude'])
                    urgenti.remove(px)
                else: break
    return piano, lun_ref

# --- 4. INTERFACCIA ---
if not st.session_state.df_master.empty:
    agenda_completa, lunedi_base = calcola_piano_8_settimane()
    t_oggi, t_sett, t_ana, t_nuovo, t_par = st.tabs(["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"])

    with t_oggi:
        st.header(f"📍 Giro di Oggi")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = agenda_completa["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                            st.caption(f"📞 {t.get('cellulare','')} | 👤 {t.get('referente','')}")
                            col_b1, col_b2 = st.columns(2)
                            col_b1.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                            with col_b2.popover("📝 Report"):
                                with st.form(f"rep_{t['nome cliente']}"):
                                    es = st.selectbox("Esito", ["Positivo", "Richiamare", "Negativo"], key=f"e_{t['nome cliente']}")
                                    no = st.text_area("Note visita", key=f"n_{t['nome cliente']}")
                                    if st.form_submit_button("Salva"):
                                        nuovo = {'cliente': t['nome cliente'], 'data': datetime.now().strftime("%d/%m/%Y"), 'nota_visita': no, 'esito': es}
                                        st.session_state.df_reports = pd.concat([st.session_state.df_reports, pd.DataFrame([nuovo])], ignore_index=True)
                                        idx_m = st.session_state.df_master[st.session_state.df_master['nome cliente'] == t['nome cliente']].index[0]
                                        st.session_state.df_master.at[idx_m, 'ultima visita'] = pd.to_datetime(datetime.now().date())
                                        st.rerun()
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita per oggi.")

    with t_sett:
        st.header("📅 Programmazione Prossime 8 Settimane")
        s_sel = st.selectbox("Scegli la settimana da pianificare:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        giorni_nomi = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
        for i, col in enumerate(cols):
            with col:
                data_g = (lunedi_base + timedelta(weeks=int(s_sel.split()[-1])-1, days=i)).date()
                st.subheader(giorni_nomi[i])
                st.caption(data_g.strftime("%d/%m"))
                st.divider()
                for v in agenda_completa[s_sel][i]:
                    with st.container(border=True):
                        st.caption(v['ora_arrivo'])
                        st.write(f"**{v['nome cliente']}**")

    with t_ana:
        st.header("👤 Anagrafica e Cronologia")
        cerca = st.text_input("🔍 Cerca cliente:", "").lower()
        lista = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        if lista:
            scelto = st.selectbox("Cliente:", lista)
            reps = st.session_state.df_reports[st.session_state.df_reports['cliente'] == scelto]
            if not reps.empty:
                st.subheader("📜 Storico Report")
                for _, r in reps.iloc[::-1].iterrows():
                    with st.expander(f"📅 {r['data']} - {r['esito']}"): st.write(r['nota_visita'])
            else: st.caption("Nessun report precedente.")
            st.divider()
            # Form modifica dati (già presente)
            st.info("Qui puoi modificare i dati anagrafici come prima.")

    with t_nuovo:
        st.header("➕ Nuovo Cliente")
        with st.form("new"):
            nome = st.text_input("Ragione Sociale")
            if st.form_submit_button("Aggiungi"):
                if nome:
                    rigo = {'nome cliente': nome, 'visitare': 'SI', 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([rigo])], ignore_index=True)
                    st.rerun()

    with t_par:
        st.header("⚙️ Parametri")
        st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
        if st.button("Reset Totale"):
            st.cache_data.clear()
            del st.session_state.df_master; st.rerun()
