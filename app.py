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
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🚀 Giro Oggi"
if 'cliente_selezionato' not in st.session_state: st.session_state.cliente_selezionato = None
if 'df_master' not in st.session_state:
    st.session_state.df_master = fetch_data("https://docs.google.com/spreadsheets/d/1uNqrdMEeAJwL3hAV1y82xU1nlLyEyQ0A8S-Fhe8QPTs/export?format=csv&gid=240777132")
if 'df_reports' not in st.session_state:
    st.session_state.df_reports = pd.DataFrame(columns=['cliente', 'data', 'nota_visita', 'esito'])

if 'start_lat' not in st.session_state: st.session_state.start_lat, st.session_state.start_lon = 43.1924, 13.5797
if 'h_inizio' not in st.session_state: st.session_state.h_inizio = time(9, 0)
if 'h_fine' not in st.session_state: st.session_state.h_fine = time(18, 0)
if 'durata_v' not in st.session_state: st.session_state.durata_v = 45
if 'spostamenti' not in st.session_state: st.session_state.spostamenti = {}

# --- 3. LOGICA CALCOLO ---
def calcola_piano():
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

# --- 4. NAVBAR ---
c_nav = st.columns(5)
menu = ["🚀 Giro Oggi", "📅 Agenda 8 Sett", "👤 Anagrafica", "➕ Nuovo Cliente", "⚙️ Parametri"]
for i, m in enumerate(menu):
    if c_nav[i].button(m, use_container_width=True, type="primary" if st.session_state.active_tab == m else "secondary"):
        st.session_state.active_tab = m
        st.rerun()
st.divider()

piano, lun_base = calcola_piano()

# --- 🚀 GIRO OGGI ---
if st.session_state.active_tab == "🚀 Giro Oggi":
    st.header(f"📍 Oggi: {datetime.now().strftime('%d/%m/%Y')}")
    idx_g = datetime.now().weekday()
    if idx_g < 5:
        tappe = piano["Settimana 1"][idx_g]
        if tappe:
            c1, c2 = st.columns([1, 2])
            with c1:
                for t in tappe:
                    with st.container(border=True):
                        st.write(f"🕒 **{t['ora_arrivo']}** - {t['nome cliente']}")
                        
                        # AZIONI RAPIDE
                        act = st.columns(4)
                        act[0].link_button("🚗", f"https://www.google.com/maps/dir/?api=1&destination={t['latitude']},{t['longitude']}", help="Naviga")
                        if t.get('cellulare'): act[1].link_button("📞", f"tel:{t['cellulare']}", help="Chiama")
                        if t.get('mail'): act[2].link_button("📧", f"mailto:{t['mail']}", help="Email")
                        if act[3].button("👤", key=f"go_{t['nome cliente']}", help="Scheda"):
                            st.session_state.cliente_selezionato = t['nome cliente']
                            st.session_state.active_tab = "👤 Anagrafica"
                            st.rerun()
                        
                        # REPORT
                        with st.popover("📝 Compila Report Visita", use_container_width=True):
                            with st.form(f"f_{t['nome cliente']}"):
                                es = st.selectbox("Esito", ["Positivo", "Richiamare", "Negativo"])
                                no = st.text_area("Note")
                                if st.form_submit_button("Salva Report"):
                                    nuovo = {'cliente': t['nome cliente'], 'data': datetime.now().strftime("%d/%m/%Y"), 'nota_visita': no, 'esito': es}
                                    st.session_state.df_reports = pd.concat([st.session_state.df_reports, pd.DataFrame([nuovo])], ignore_index=True)
                                    idx_m = st.session_state.df_master[st.session_state.df_master['nome cliente'] == t['nome cliente']].index[0]
                                    st.session_state.df_master.at[idx_m, 'ultima visita'] = pd.to_datetime(datetime.now().date())
                                    st.rerun()
            with c2: st.map(pd.DataFrame(tappe).rename(columns={'latitude':'lat','longitude':'lon'}))
        else: st.info("Nessuna visita programmata.")

# --- 👤 ANAGRAFICA ---
elif st.session_state.active_tab == "👤 Anagrafica":
    st.header("👤 Scheda Cliente")
    nomi = sorted(st.session_state.df_master['nome cliente'].unique())
    idx_p = nomi.index(st.session_state.cliente_selezionato) if st.session_state.cliente_selezionato in nomi else 0
    scelto = st.selectbox("Seleziona cliente:", nomi, index=idx_p)
    
    if scelto:
        idx = st.session_state.df_master[st.session_state.df_master['nome cliente'] == scelto].index[0]
        d = st.session_state.df_master.loc[idx]
        
        # BARRA CONTATTO DIRETTO
        st.write("### 📞 Contatto Rapido")
        c_act = st.columns(3)
        if d.get('cellulare'): c_act[0].link_button(f"📱 Chiama: {d['cellulare']}", f"tel:{d['cellulare']}", use_container_width=True)
        if d.get('telefono'): c_act[1].link_button(f"☎️ Fisso: {d['telefono']}", f"tel:{d['telefono']}", use_container_width=True)
        if d.get('mail'): c_act[2].link_button(f"📧 Email: {d['mail']}", f"mailto:{d['mail']}", use_container_width=True)
        
        st.divider()
        st.subheader("📜 Storico Visite")
        reps = st.session_state.df_reports[st.session_state.df_reports['cliente'] == scelto]
        if not reps.empty:
            for _, r in reps.iloc[::-1].iterrows():
                with st.expander(f"📅 {r['data']} - {r['esito']}"): st.write(r['nota_visita'])
        
        st.divider()
        with st.form("edit_full"):
            st.subheader("⚙️ Modifica Anagrafica")
            ca, cb = st.columns(2)
            with ca:
                un = st.text_input("Ragione Sociale", d['nome cliente'])
                ui = st.text_input("Indirizzo", d['indirizzo'])
                uf = st.number_input("Frequenza (gg)", value=int(d['frequenza (giorni)']))
                ut = st.text_input("Telefono Fisso", d.get('telefono',''))
            with cb:
                ur = st.text_input("Referente", d.get('referente',''))
                uc = st.text_input("Cellulare", d.get('cellulare',''))
                um = st.text_input("Mail", d.get('mail',''))
                uv = st.toggle("Abilita nel Giro", value=(d['visitare'] == 'SI'))
            unot = st.text_area("Note Generali", d.get('note',''))
            if st.form_submit_button("💾 Salva Modifiche"):
                for k, v in {"nome cliente":un, "indirizzo":ui, "frequenza (giorni)":uf, "mail":um, "telefono":ut, "referente":ur, "cellulare":uc, "note":unot, "visitare":('SI' if uv else 'NO')}.items():
                    st.session_state.df_master.at[idx, k] = v
                st.success("Salvato!"); st.rerun()

# --- ⚙️ PARAMETRI (I 5 PARAMETRI) ---
elif st.session_state.active_tab == "⚙️ Parametri":
    st.header("⚙️ Impostazioni Sistema")
    if st.button("🎯 Rileva la mia posizione attuale (GPS partenza)"):
        g = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_param')
        if g:
            st.session_state.start_lat, st.session_state.start_lon = g['latitude'], g['longitude']
            st.success(f"Posizione di partenza aggiornata!")
    
    st.divider()
    c1, c2 = st.columns(2)
    st.session_state.h_inizio = c1.time_input("Ora Inizio Lavoro", st.session_state.h_inizio)
    st.session_state.h_fine = c2.time_input("Ora Fine Lavoro", st.session_state.h_fine)
    st.session_state.durata_v = st.slider("Durata media visita (min)", 15, 120, st.session_state.durata_v)
    
    st.divider()
    st.subheader("🔄 Sposta Giorno")
    col_d1, col_d2 = st.columns(2)
    d_da = col_d1.date_input("Sposta da:", datetime.now())
    d_a = col_d2.date_input("A giorno:", datetime.now() + timedelta(days=1))
    if st.button("🔄 Esegui Scambio"):
        st.session_state.spostamenti[d_da] = d_a
        st.session_state.spostamenti[d_a] = d_da
        st.success("Giri scambiati!"); st.rerun()
    
    st.divider()
    if st.button("🔄 Reset Totale (Ricarica da Google)"):
        st.cache_data.clear()
        del st.session_state.df_master; st.rerun()

# --- (ALTRI TAB: AGENDA E NUOVO CLIENTE INVARIATI) ---
elif st.session_state.active_tab == "📅 Agenda 8 Sett":
    st.header("Pianificazione Strategica")
    s_sel = st.selectbox("Settimana:", [f"Settimana {i}" for i in range(1, 9)])
    cols = st.columns(5)
    for i, col in enumerate(cols):
        with col:
            dt_g = (lun_base + timedelta(weeks=int(s_sel.split()[-1])-1, days=i)).date()
            st.subheader(f"{'🔄 ' if dt_g in st.session_state.spostamenti else ''}{dt_g.strftime('%A')}")
            for v in agenda[s_sel][i]:
                with st.container(border=True):
                    st.write(f"**{v['nome cliente']}**")
                    if st.button("👤", key=f"ag_{v['nome cliente']}_{i}"):
                        st.session_state.cliente_selezionato = v['nome cliente']
                        st.session_state.active_tab = "👤 Anagrafica"; st.rerun()

elif st.session_state.active_tab == "➕ Nuovo Cliente":
    st.header("➕ Nuovo Cliente")
    if st.button("📍 Geocalizza Ora"):
        gps = streamlit_js_eval(js_expressions="window.navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:set_component_value', value: pos.coords}, '*') })", key='gps_new')
        if gps: st.session_state.start_lat, st.session_state.start_lon = gps['latitude'], gps['longitude']; st.success("Posizione acquisita!")
    with st.form("new_c"):
        nn = st.text_input("Ragione Sociale")
        if st.form_submit_button("✅ Aggiungi"):
            if nn:
                r = {'nome cliente': nn, 'visitare': 'SI', 'frequenza (giorni)': 30, 'ultima visita': pd.Timestamp('2000-01-01'), 'latitude': st.session_state.start_lat, 'longitude': st.session_state.start_lon}
                st.session_state.df_master = pd.concat([st.session_state.df_master, pd.DataFrame([r])], ignore_index=True)
                st.rerun()
