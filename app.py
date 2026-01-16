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
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA CALCOLO 8 SETTIMANE ---
def calcola_piano_completo():
    if st.session_state.df_master.empty: return {}, datetime.now()
    oggi = datetime.now()
    lun_ref = oggi - timedelta(days=oggi.weekday())
    df_sim = st.session_state.df_master.copy()
    piano = {f"Settimana {i}": {g: [] for g in range(5)} for i in range(1, 9)}
    for s in range(1, 9):
        for g in range(5):
            dt_c = (lun_ref + timedelta(weeks=s-1, days=g)).date()
            dt_l = st.session_state.spostamenti.get(dt_c, dt_c)
            df_sim['g_p'] = (pd.to_datetime(dt_l) - df_sim['ultima visita']).dt.days.fillna(999)
            urg = df_sim[(df_sim['visitare'] == 'SI') & (df_sim['g_p'] >= df_sim['frequenza (giorni)'])].to_dict('records')
            o_s, p_s = datetime.combine(dt_c, st.session_state.h_inizio), (st.session_state.start_lat, st.session_state.start_lon)
            while urg:
                px = min(urg, key=lambda x: haversine(p_s[0], p_s[1], x['latitude'], x['longitude']))
                arr = o_s + timedelta(minutes=(haversine(p_s[0], p_s[1], px['latitude'], px['longitude'])/50)*60)
                fine = arr + timedelta(minutes=st.session_state.durata_v)
                if fine <= datetime.combine(dt_c, st.session_state.h_fine):
                    px['ora_arrivo'] = arr.strftime("%H:%M")
                    piano[f"Settimana {s}"][g].append(px)
                    df_sim.loc[df_sim['nome cliente'] == px['nome cliente'], 'ultima visita'] = pd.to_datetime(dt_l)
                    o_s, p_s = fine, (px['latitude'], px['longitude'])
                    urg.remove(px)
                else: break
    return piano, lun_ref

# --- 4. INTERFACCIA ---
if not st.session_state.df_master.empty:
    agenda, lun_base = calcola_piano_completo()
    tabs = st.tabs(["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"])

    # --- TAB 1: GIRO OGGI ---
    with tabs[0]:
        st.header(f"📍 Oggi: {datetime.now().strftime('%d/%m/%Y')}")
        idx_g = datetime.now().weekday()
        if idx_g < 5:
            tappe = agenda["Settimana 1"][idx_g]
            if tappe:
                c1, c2 = st.columns([1, 2])
                with c1:
                    for t in tappe:
                        with st.container(border=True):
                            st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                            st.caption(f"👤 {t.get('referente','')} | 📞 {t.get('cellulare','')}")
                            cb1, cb2 = st.columns(2)
                            cb1.link_button("🚗 Naviga", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", use_container_width=True)
                            with cb2.popover("📝 Report"):
                                with st.form(f"r_{t['nome cliente']}"):
                                    es = st.selectbox("Esito", ["Positivo", "Richiamare", "Negativo"], key=f"es_{t['nome cliente']}")
                                    no = st.text_area("Note", key=f"no_{t['nome cliente']}")
                                    if st.form_submit_button("Salva"):
                                        nuovo_r = {'cliente': t['nome cliente'], 'data': datetime.now().strftime("%d/%m/%Y"), 'nota_visita': no, 'esito': es}
                                        st.session_state.df_reports = pd.concat([st.session_state.df_reports, pd.DataFrame([nuovo_r])], ignore_index=True)
                                        idx_m = st.session_state.df_master[st.session_state.df_master['nome cliente'] == t['nome cliente']].index[0]
                                        st.session_state.df_master.at[idx_m, 'ultima visita'] = pd.to_datetime(datetime.now().date())
                                        st.rerun()
                with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
            else: st.info("Nessuna visita.")

    # --- TAB 2: AGENDA 8 SETTIMANE ---
    with tabs[1]:
        s_sel = st.selectbox("Settimana:", [f"Settimana {i}" for i in range(1, 9)])
        cols = st.columns(5)
        for i, col in enumerate(cols):
            with col:
                dt_g = (lun_base + timedelta(weeks=int(s_sel.split()[-1])-1, days=i)).date()
                st.subheader(dt_g.strftime("%A")); st.caption(dt_g.strftime("%d/%m"))
                for v in agenda[s_sel][i]:
                    with st.container(border=True): st.caption(v['ora_arrivo']); st.write(v['nome cliente'])

    # --- TAB 3: ANAGRAFICA & STORICO ---
    with tabs[2]:
        st.header("👤 Scheda Cliente")
        cerca = st.text_input("🔍 Cerca cliente:", "").lower()
        nomi = [n for n in sorted(st.session_state.df_master['nome cliente'].unique()) if cerca in n.lower()]
        if nomi:
            scelto = st.selectbox("Seleziona:", nomi)
            idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
            d = st.session_state.df_master.loc[idx]
            
            # 1. Visualizza Storico Report
            st.subheader("📜 Storico Visite")
            reps = st.session_state.df_reports[st.session_state.df_reports['cliente'] == scelto]
            if not reps.empty:
                for _, r in reps.iloc[::-1].iterrows():
                    with st.expander(f"📅 {r['data']} - {r['esito']}"): st.write(r['nota_visita'])
            else: st.caption("Nessun report presente.")
            
            st.divider()
            # 2. Modifica Anagrafica (RIPRISTINATO)
            with st.form("edit_full"):
                st.subheader("⚙️ Modifica Anagrafica")
                ca, cb = st.columns(2)
                with ca:
                    un = st.text_input("Ragione Sociale", d['nome cliente'])
                    ui = st.text_input("Indirizzo", d['indirizzo'])
                    uf = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                    um = st.text_input("Mail", d.get('mail',''))
                with cb:
                    ur = st.text_input("Referente", d.get('referente',''))
                    up = st.text_input("Posizione", d.get('posizione referente',''))
                    uc = st.text_input("Cellulare", d.get('cellulare',''))
                    uv = st.toggle("Abilita nel Giro", value=(d['visitare'] == 'SI'))
                if st.form_submit_button("💾 Salva Dati"):
                    st.session_state.df_master.at[idx, 'nome cliente'], st.session_state.df_master.at[idx, 'indirizzo'] = un, ui
                    st.session_state.df_master.at[idx, 'frequenza (giorni)'], st.session_state.df_master.at[idx, 'mail'] = uf, um
                    st.session_state.df_master.at[idx, 'referente'], st.session_state.df_master.at[idx, 'posizione referente'] = ur, up
                    st.session_state.df_master.at[idx, 'cellulare'], st.session_state.df_master.at[idx, 'visitare'] = uc, ('SI' if uv else 'NO')
                    st.success("Dati aggiornati!"); st.rerun()

    # --- TAB 4: NUOVO CLIENTE ---
    with tabs[3]:
        st.header("➕ Nuovo Cliente")
        new_lat, new_lon = 0.0, 0.0
        if st.button("📍 Geocalizza Posizione"):
            gps = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_new')
            if gps: new_lat, new_lon = gps['latitude'], gps['longitude']; st.success("Posizione acquisita!")
        with st.form("new_c"):
            nn = st.text_input("Ragione Sociale *")
            ni = st.text_input("Indirizzo")
            nla = st.number_input("Lat", value=new_lat if new_lat != 0 else st.session_state.start_lat, format="%.6f")
            nlo = st.number_input("Lon", value=new_lon if new_lon != 0 else st.session_state.start_lon, format="%.6f")
            if st.form_submit_button("✅ Aggiungi"):
                if nn:
                    r = {'nome cliente': nn, 'indirizzo': ni, 'latitude': nla, 'longitude': nlo, 'visitare': 'SI', 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01')}
                    st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([r])], ignore_index=True)
                    st.rerun()

    # --- TAB 5: PARAMETRI ---
    with tabs[4]:
        st.header("⚙️ Parametri")
        st.session_state.h_inizio = st.time_input("Inizio", st.session_state.h_inizio)
        st.session_state.h_fine = st.time_input("Fine", st.session_state.h_fine)
        st.session_state.durata_v = st.slider("Minuti Visita", 15, 120, st.session_state.durata_v)
        st.divider()
        st.subheader("🔄 Sposta Giorno")
        d_da = st.date_input("Da:", datetime.now()); d_a = st.date_input("A:", datetime.now() + timedelta(days=1))
        if st.button("Scambia"): st.session_state.spostamenti[d_da] = d_a; st.session_state.spostamenti[d_a] = d_da; st.rerun()
        if st.button("Ricarica Database"): del st.session_state.df_master; st.rerun()
