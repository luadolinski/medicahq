import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import json
from datetime import datetime, timedelta
import re
from pypdf import PdfReader

# -------------------------------------------------------------
# CONFIGURACIÓN GENERAL Y ESTILO
# -------------------------------------------------------------
st.set_page_config(
    page_title="Médica HQ | Residencias & Revalida",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# BASE DE DATOS LOCAL (SQLite Persistente)
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("medica_hq.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Tabla de preguntas
    c.execute('''
        CREATE TABLE IF NOT EXISTS choices (
            id TEXT PRIMARY KEY,
            examen_origen TEXT,
            area TEXT,
            tema TEXT,
            incidencia TEXT,
            pregunta TEXT,
            opcion_a TEXT,
            opcion_b TEXT,
            opcion_c TEXT,
            opcion_d TEXT,
            correcta TEXT,
            justificacion TEXT,
            drive_link TEXT,
            next_review DATE,
            interval_days INTEGER,
            ease_factor REAL,
            repetitions INTEGER
        )
    ''')
    # Tabla de historial y errores
    c.execute('''
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            choice_id TEXT,
            fecha TIMESTAMP,
            respuesta_dada TEXT,
            es_correcta INTEGER,
            flag_duda INTEGER,
            motivo_error TEXT,
            regla_oro TEXT,
            FOREIGN KEY (choice_id) REFERENCES choices (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# CARGA DE PREGUNTAS SEMILLA (High-Yield Inicial)
# -------------------------------------------------------------
def seed_initial_data():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM choices")
    if c.fetchone()[0] == 0:
        sample_questions = [
            ("AR-2026-N-01", "🇦🇷 Examen Único 2026", "Tocoginecología", "Preeclampsia y Trastornos Hipertensivos", "Prioridad A",
             "Primigesta de 33 semanas ingresa con TA 165/110 mmHg, cefalea intensa y epigastralgia. En orina presenta proteinuria +++. ¿Cuál es la conducta inicial prioritaria?",
             "Indicar reposo absoluto e iniciar alfametildopa 500 mg VO cada 8 h",
             "Administrar Labetalol EV y esquema de impregnación con Sulfato de Magnesio EV",
             "Indicar Hidroclorotiazida oral y Betametasona IM esperando 48 h",
             "Realizar cesárea de urgencia sin estabilización previa",
             "B", "En preeclampsia con criterios de severidad se debe controlar la crisis hipertensiva (Labetalol/Hidralazina EV) y prevenir convulsiones con Sulfato de Magnesio (esquema Zuspan/Sibai) previo a cualquier otra conducta.",
             "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0),
            
            ("AR-2026-C-02", "🇦🇷 CABA 2026", "Pediatría", "IRAB - Bronquiolitis", "Prioridad A",
             "Lactante de 4 meses con primer episodio de sibilancias, tiraje subcostal y SatO2 91% al aire ambiente. No presenta antecedentes patológicos. Según la SAP, ¿cuál es el pilar del tratamiento?",
             "Nebulizaciones continuas con Salbutamol e hidrocortisona EV",
             "Kinesioterapia respiratoria tres veces al día y amoxicilina oral",
             "Medidas de soporte, permeabilización de vía aérea y oxigenoterapia si SatO2 < 92%",
             "Indicar antibióticos macrólidos y bromuro de ipratropio reglado",
             "C", "En el primer episodio de bronquiolitis aguda, la recomendación de la SAP se basa en sostén hídrico, desobstrucción nasal y oxígeno si SatO2 < 92%. No se aconseja el uso rutinario de broncodilatadores ni kinesiología.",
             "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0),

            ("AR-2024-U-03", "🇦🇷 Examen Único 2024", "Cirugía General", "Trauma Torácico ATLS", "Prioridad A",
             "Varón de 22 años politraumatizado ingresa con TA 70/40, ingurgitación yugular, hipoventilación y timpanismo en hemitórax derecho, con tráquea desviada a la izquierda. ¿Cuál es el paso inmediato?",
             "Solicitar radiografía de tórax portátil urgente",
             "Realizar intubación orotraqueal con secuencia rápida",
             "Descompresión inmediata con aguja/catéter en el 4.º o 5.º espacio intercostal línea axilar anterior derecha",
             "Realizar ecografía FAST toracoabdominal",
             "C", "Es un Neumotórax a Tensión. Su diagnóstico es 100% clínico y no debe retrasarse con métodos complementarios. Requiere descompresión torácica inmediata con aguja/toracostomía de rescate.",
             "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0),

            ("BR-2023-R-04", "🇧🇷 Revalida INEP 2023", "Clínica Médica", "Dengue y Arbovirosis", "Prioridad A",
             "Paciente de 42 años con dengue ingresa al 5.° día afebril pero con dolor abdominal continuo y vómitos persistentes. TA 90/60 mmHg. ¿A qué grupo de riesgo pertenece y cuál es la conducta según el MS?",
             "Grupo A: Paracetamol e hidratación oral domiciliaria",
             "Grupo B: Observación en guardia y esperar hematocrito para decidir",
             "Grupo C: Internación inmediata e inicio de reposición hídrica parenteral agresiva con cristaloides",
             "Grupo D: Transfusión profiláctica de plaquetas inmediata",
             "C", "Presenta signos de alarma (dolor abdominal continuo y vómitos), clasificándose como Dengue Grupo C. Requiere internación y expansión inmediata con cristaloides sin supeditar el inicio al laboratorio.",
             "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0),

            ("AR-2026-P-05", "🇦🇷 PBA 2026", "Salud Pública y Leyes", "Ley 26.529 Derechos del Paciente", "Prioridad A",
             "Paciente lúcido de 45 años ingresa con peritonitis por apendicitis perforada y rechaza la cirugía tras ser informado de los riesgos. Según la Ley 26.529, ¿cuál es la conducta legal adecuada?",
             "Pedir autorización judicial urgente para operarlo de inmediato",
             "Respetar la decisión del paciente y dejar constancia fehaciente en la Historia Clínica con su firma",
             "Operar con consentimiento firmado por los familiares directos",
             "Convocar un comité de bioética para obligarlo al tratamiento",
             "B", "La Ley 26.529 consagra la autonomía de la voluntad: todo paciente competente puede aceptar o rechazar terapias, debiendo dejarse constancia firmada en la Historia Clínica.",
             "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0)
        ]
        c.executemany('''
            INSERT INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_questions)
        conn.commit()
    conn.close()

seed_initial_data()

# -------------------------------------------------------------
# LÓGICA DE REPASO ESPACIADO (SM-2 Simplificado)
# -------------------------------------------------------------
def update_sm2(choice_id, rating):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT interval_days, ease_factor, repetitions FROM choices WHERE id = ?", (choice_id,))
    row = c.fetchone()
    if row:
        interval, ef, reps = row["interval_days"], row["ease_factor"], row["repetitions"]
        if rating == "Difícil":
            reps = 0
            interval = 1
            ef = max(1.3, ef - 0.2)
        elif rating == "Bien":
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = int(interval * ef)
            reps += 1
        elif rating == "Muy Fácil":
            if reps == 0:
                interval = 3
            elif reps == 1:
                interval = 7
            else:
                interval = int(interval * ef * 1.3)
            reps += 1
            ef += 0.15

        next_date = datetime.now().date() + timedelta(days=interval)
        c.execute('''
            UPDATE choices 
            SET interval_days = ?, ease_factor = ?, repetitions = ?, next_review = ?
            WHERE id = ?
        ''', (interval, ef, reps, str(next_date), choice_id))
        conn.commit()
    conn.close()

# -------------------------------------------------------------
# BARRA LATERAL Y NAVEGACIÓN
# -------------------------------------------------------------
st.sidebar.title("🩺 Médica HQ")
st.sidebar.caption("Residencias Argentina & Revalida Brasil")

filtro_pais = st.sidebar.selectbox("Filtro de Examen Activo", ["🔀 Modo Dual / Integrado", "🇦🇷 Solo Argentina", "🇧🇷 Solo Brasil"])

menu = st.sidebar.radio(
    "Módulos de Estudio",
    [
        "🏠 Dashboard & Repaso de Hoy",
        "📅 Cronograma de Estudio",
        "📚 Temario & Algoritmos",
        "📝 Banco de Choices & Simulacros",
        "📕 Cuaderno de Errores",
        "⚖️ Guía Comparativa AR vs BR",
        "📊 Métricas & Rendimiento",
        "⚙️ Importar Exámenes (PDF / CSV)"
    ]
)

# -------------------------------------------------------------
# 1. DASHBOARD & REPASO DEL DÍA
# -------------------------------------------------------------
if menu == "🏠 Dashboard & Repaso de Hoy":
    st.header("⚡ Panel de Control Diario")
    
    conn = get_db_connection()
    total_q = pd.read_sql("SELECT COUNT(*) as count FROM choices", conn).iloc[0]['count']
    total_reviews = pd.read_sql("SELECT COUNT(*) as count FROM error_log", conn).iloc[0]['count']
    total_correct = pd.read_sql("SELECT COUNT(*) as count FROM error_log WHERE es_correcta = 1", conn).iloc[0]['count']
    conn.close()

    accuracy = int((total_correct / total_reviews * 100)) if total_reviews > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Racha de Estudio", "12 Días")
    col2.metric("🎯 Precisión Global", f"{accuracy}%")
    col3.metric("📝 Choices Resueltos", str(total_reviews))
    col4.metric("📚 Banco Total", f"{total_q} preguntas")

    st.markdown("---")
    st.subheader("🧠 Choices Programados para Repasar Hoy (Curva del Olvido)")
    
    today = str(datetime.now().date())
    conn = get_db_connection()
    due_q = pd.read_sql("SELECT * FROM choices WHERE next_review <= ?", conn, params=(today,))
    conn.close()

    if len(due_q) == 0:
        st.success("🎉 ¡Estás al día! No tenés preguntas pendientes de repaso espaciado para hoy.")
    else:
        st.info(f"Tenés **{len(due_q)} choices** que alcanzaron su intervalo de repaso.")
        for idx, row in due_q.iterrows():
            with st.expander(f"📌 {row['area']} | {row['tema']} ({row['examen_origen']})"):
                st.write(f"**{row['pregunta']}**")
                st.write(f"A) {row['opcion_a']}")
                st.write(f"B) {row['opcion_b']}")
                st.write(f"C) {row['opcion_c']}")
                st.write(f"D) {row['opcion_d']}")
                if st.button("Ver Justificación", key=f"dash_rev_{row['id']}"):
                    st.success(f"**Opción Correcta: {row['correcta']}**")
                    st.write(row['justificacion'])

# -------------------------------------------------------------
# 2. CRONOGRAMA DINÁMICO
# -------------------------------------------------------------
elif menu == "📅 Cronograma de Estudio":
    st.header("📅 Cronograma de Estudio (Agosto a Diciembre)")
    st.caption("Planificación estructurada de alta incidencia para trabajar y estudiar sin saturación[cite: 1, 2].")

    cronograma_data = [
        {"Semana": "Semana 1", "Bloque": "Tocoginecología", "Tema Principal": "Preeclampsia y Síndromes Hipertensivos del Embarazo[cite: 1, 2]", "Incidencia": "Prioridad A", "Estado": "Completado"},
        {"Semana": "Semana 2", "Bloque": "Tocoginecología", "Tema Principal": "Hemorragias 1° y 3° Trimestre + Ley IVE/ILE 27.610[cite: 2]", "Incidencia": "Prioridad A", "Estado": "En Curso"},
        {"Semana": "Semana 3", "Bloque": "Tocoginecología", "Tema Principal": "Infecciones Gestacionales (Sífilis/TORCH) + Vacuna VSR[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 4", "Bloque": "Tocoginecología", "Tema Principal": "Tamizaje Cérvix (PAP/DNA-HPV) + Anticoncepción[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 5", "Bloque": "Pediatría", "Tema Principal": "IRAB: Bronquiolitis, Neumonía y Crup[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 6", "Bloque": "Pediatría", "Tema Principal": "Diarrea Aguda (Planes OMS) y SUH[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 7", "Bloque": "Pediatría", "Tema Principal": "Puericultura, Hitos de Desarrollo y Sueño Seguro SAP[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 8", "Bloque": "Pediatría", "Tema Principal": "Calendario de Vacunación Nacional + Neonatología[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 9", "Bloque": "Clínica Médica", "Tema Principal": "Cardiología: HTA, Crisis HTA, SCA y FA[cite: 1, 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 10", "Bloque": "Clínica Médica", "Tema Principal": "Infectología: Dengue, Tuberculosis (GeneXpert) y VIH[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 11", "Bloque": "Clínica Médica", "Tema Principal": "Endocrino: Diabetes Tipo 2 y Cetoacidosis Diabética[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 12", "Bloque": "Clínica Médica", "Tema Principal": "Nefrología, Medio Interno y ACV Isquémico[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 13", "Bloque": "Clínica Médica", "Tema Principal": "Endemias Brasil (Chagas, Leishmania) y Meningitis[cite: 2]", "Incidencia": "Prioridad B", "Estado": "Pendiente"},
        {"Semana": "Semana 14", "Bloque": "Cirugía General", "Tema Principal": "Trauma ATLS (Neumotórax a Tensión, Choque, Quemaduras)[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 15", "Bloque": "Cirugía General", "Tema Principal": "Abdomen Agudo Inflamatorio (Apendicitis, Biliar, Diverticulitis)[cite: 1, 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 16", "Bloque": "Cirugía General", "Tema Principal": "Oclusión Intestinal, Hernias y Cadera Dolorosa[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 17", "Bloque": "Salud Pública & SUS", "Tema Principal": "Epidemiología Básica, Bioética y Salud Mental (Delirium/Agitación)[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 18", "Bloque": "Salud Pública & SUS", "Tema Principal": "Leyes Sanitarias AR (26.529/26.657/25.929) vs. Leyes SUS BR (8080/8142)[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"},
        {"Semana": "Semana 19-20", "Bloque": "Consolidación", "Tema Principal": "Baterías de Simulacros Intensivos + Cuaderno de Errores[cite: 2]", "Incidencia": "Prioridad A", "Estado": "Pendiente"}
    ]
    df_crono = pd.DataFrame(cronograma_data)
    st.dataframe(df_crono, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 3. TEMARIO & ALGORITMOS
# -------------------------------------------------------------
elif menu == "📚 Temario & Algoritmos":
    st.header("📚 Temario & Módulos Clínicos")
    
    tema_sel = st.selectbox(
        "Seleccioná el tema a estudiar:",
        [
            "Preeclampsia y Síndromes Hipertensivos del Embarazo[cite: 1, 2]",
            "IRAB: Bronquiolitis y Crisis Asmática Pediátrica[cite: 2]",
            "Trauma Torácico y Protocolo ATLS[cite: 2]",
            "Dengue y Arbovirosis Urbanas[cite: 2]",
            "Leyes Sanitarias de Argentina (26.529 / 26.657 / 27.610)[cite: 2]"
        ]
    )

    t1, t2, t3, t4 = st.tabs(["📄 Resumen & Drive", "🧠 Diagrama / Algoritmo", "⚡ High-Yield Pearls", "⚖️ Comparativa AR vs BR"])

    with t1:
        st.subheader("Material de Estudio")
        st.link_button("🔗 Abrir Carpeta de Resúmenes en Google Drive", "https://drive.google.com")
        st.info("Podés incrustar notas rápidas o resúmenes teóricos personales para este módulo.")

    with t2:
        st.subheader("Algoritmo Diagnóstico / Terapéutico")
        if "Preeclampsia" in tema_sel:
            st.markdown("""
            ```mermaid
            graph TD
                A[Gestante >= 20 sem con PA >= 140/90] --> B{Criterios de Severidad?<br>PA >= 160/110, Cefalea, Epigastralgia, Plaquetas < 100k}
                B -- SÍ --> C[Preeclampsia Severa]
                B -- NO --> D[Preeclampsia sin Severidad]
                C --> E[1° Labetalol 20mg EV o Hidralazina 5mg EV]
                C --> F[2° Sulfato de Magnesio: Ataque 4-5g EV + Mant 1-2g/h]
                C --> G[Planificar Finalización según Edad Gestacional]
            ```
            """, unsafe_allow_html=True)
            st.caption("Diagrama renderizado con lógica clínica estandarizada.")
        elif "Trauma" in tema_sel:
            st.markdown("""
            ```mermaid
            graph TD
                A[Trauma Torácico con Shock / Disnea] --> B{Clínica: Hipotensión + Yugulares Ingurgitadas + Timpanismo + Tráquea Desviada}
                B -- SÍ --> C[NEUMOTÓRAX A TENSIÓN]
                C --> D[Descompresión Inmediata con Aguja en 4°/5° EIC Línea Axilar Anterior]
                D --> E[Colocación de Tubo de Drenaje Pleural bajo Sello de Agua]
                B -- NO --> F[Evaluar Hemotórax / Taponamiento / FAST]
            ```
            """, unsafe_allow_html=True)

    with t3:
        st.subheader("⚡ High-Yield Pearls (Reglas de Fija Memoria)")
        if "Preeclampsia" in tema_sel:
            st.write("• **Crisis Hipertensiva:** Se define con cifras $\\ge 160/110\\text{ mmHg}$[cite: 2]. Fármacos de primera línea: Labetalol EV o Hidralazina EV[cite: 2].")
            st.write("• **Profilaxis de Eclampsia:** Sulfato de Magnesio endovenoso obligatorio (Esquema Zuspan o Sibai)[cite: 2].")
            st.write("• **Intoxicación por Magnesio:** Antídoto de rescate: Gluconato de Calcio al $10\\%$ EV.")
        elif "Trauma" in tema_sel:
            st.write("• **Neumotórax a Tensión:** Diagnóstico estrictamente clínico. Nunca retrasar la descompresión para pedir radiografía de tórax[cite: 2].")
            st.write("• **Tríada de Beck (Taponamiento Cardíaco):** Hipotensión arterial + Ruidos cardíacos apagados + Ingurgitación yugular[cite: 2].")

    with t4:
        st.subheader("⚖️ Diferencias Clave: Argentina vs. Brasil")
        comp_df = pd.DataFrame([
            {"Aspecto": "Tamizaje Cérvix", "🇦🇷 Argentina": "Papanicolaou a partir de los 25 años (FASGO 2024)[cite: 2]", "🇧🇷 Brasil": "Rastreo molecular DNA-HPV según directrices MS[cite: 2]"},
            {"Aspecto": "Vacunación VSR", "🇦🇷 Argentina": "Obligatoria en embarazadas semanas 32 a 36[cite: 2]", "🇧🇷 Brasil": "No incorporada universalmente al PNI gestacional"},
            {"Aspecto": "Leyes Sanitarias", "🇦🇷 Argentina": "Ley 26.529 (Derechos) y Ley 27.610 (IVE/ILE)[cite: 2]", "🇧🇷 Brasil": "Leyes 8.080 y 8.142 del SUS[cite: 2]"}
        ])
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 4. MOTOR DE CHOICES & SIMULACROS
# -------------------------------------------------------------
elif menu == "📝 Banco de Choices & Simulacros":
    st.header("📝 Práctica Interactiva de Choices")

    conn = get_db_connection()
    query = "SELECT * FROM choices"
    if filtro_pais == "🇦🇷 Solo Argentina":
        query += " WHERE examen_origen LIKE '%🇦🇷%'"
    elif filtro_pais == "🇧🇷 Solo Brasil":
        query += " WHERE examen_origen LIKE '%🇧🇷%'"
    choices_df = pd.read_sql(query, conn)
    conn.close()

    if len(choices_df) == 0:
        st.warning("No hay preguntas disponibles con el filtro seleccionado.")
    else:
        # Selector de pregunta
        q_idx = st.selectbox("Seleccionar Pregunta", range(len(choices_df)), format_func=lambda x: f"Pregunta #{x+1}: {choices_df.iloc[x]['tema']} ({choices_df.iloc[x]['examen_origen']})")
        q = choices_df.iloc[q_idx]

        st.markdown(f"#### `{q['examen_origen']}` | **{q['area']}** - *{q['tema']}*")
        st.write(f"### {q['pregunta']}")

        opciones = [
            f"A) {q['opcion_a']}",
            f"B) {q['opcion_b']}",
            f"C) {q['opcion_c']}",
            f"D) {q['opcion_d']}"
        ]

        respuesta_usr = st.radio("Opciones:", opciones, key=f"q_{q['id']}")
        flag_duda = st.checkbox("🏷️ Marcar con Banderita de Duda (Flag)", key=f"flag_{q['id']}")

        if st.button("Confirmar Respuesta", key=f"btn_{q['id']}"):
            letra_elegida = respuesta_usr[0]
            es_correcta = 1 if letra_elegida == q['correcta'] else 0

            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO error_log (choice_id, fecha, respuesta_dada, es_correcta, flag_duda, motivo_error, regla_oro)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (q['id'], datetime.now(), letra_elegida, es_correcta, 1 if flag_duda else 0, "", ""))
            conn.commit()
            conn.close()

            if es_correcta:
                st.success(f"🎉 ¡CORRECTO! Opción {q['correcta']}")
            else:
                st.error(f"❌ INCORRECTO. La respuesta oficial era la opción {q['correcta']}.")

            st.info(f"**Fundamento Clínico:** {q['justificacion']}")

            # Botones de Repaso Espaciado
            st.markdown("##### ¿Qué tan difícil te resultó esta pregunta?")
            col_a, col_b, col_c = st.columns(3)
            if col_a.button("🔴 Difícil (Repasar mañana)", key=f"d_{q['id']}"):
                update_sm2(q['id'], "Difícil")
                st.toast("Programada para repasar mañana.")
            if col_b.button("🟡 Bien (Repasar en 3 días)", key=f"b_{q['id']}"):
                update_sm2(q['id'], "Bien")
                st.toast("Programada para repasar en 3 días.")
            if col_c.button("🟢 Muy Fácil (Repasar en 7+ días)", key=f"e_{q['id']}"):
                update_sm2(q['id'], "Muy Fácil")
                st.toast("Programada para repasar en 7 días.")

# -------------------------------------------------------------
# 5. CUADERNO DE ERRORES (Metacognición)
# -------------------------------------------------------------
elif menu == "📕 Cuaderno de Errores":
    st.header("📕 Libro de Errores & Dudas (Cuaderno Blanco)")
    st.caption("Analizá tus fallas para evitar cometer el mismo error en el examen real[cite: 2].")

    conn = get_db_connection()
    errores_df = pd.read_sql('''
        SELECT e.id as log_id, e.fecha, e.respuesta_dada, e.es_correcta, e.flag_duda, e.motivo_error, e.regla_oro,
               c.pregunta, c.correcta, c.justificacion, c.area, c.tema, c.examen_origen
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
        WHERE e.es_correcta = 0 OR e.flag_duda = 1
        ORDER BY e.fecha DESC
    ''', conn)
    conn.close()

    if len(errores_df) == 0:
        st.success("✨ ¡No tenés errores ni dudas registradas actualmente!")
    else:
        st.info(f"Registros encontrados: **{len(errores_df)} preguntas** para análisis.")
        for idx, row in errores_df.iterrows():
            with st.expander(f"❌ {row['area']} - {row['tema']} ({row['examen_origen']}) | Respondido: {row['respuesta_dada']} | Correcto: {row['correcta']}"):
                st.write(f"**Pregunta:** {row['pregunta']}")
                st.write(f"**Justificación Oficial:** {row['justificacion']}")
                
                # Diagnóstico metacognitivo
                motivo = st.selectbox(
                    "¿Cuál fue la causa de este error?",
                    ["Error de lectura / Apuro", "Duda 50/50 y elegí mal", "Falta de teoría / Concepto no estudiado", "Confusión de dosis o algoritmo"],
                    key=f"motivo_{row['log_id']}"
                )
                regla = st.text_input("💡 Regla de Oro para no fallar la próxima:", value=row['regla_oro'] if row['regla_oro'] else "", key=f"regla_{row['log_id']}")
                
                if st.button("Guardar Análisis", key=f"save_err_{row['log_id']}"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE error_log SET motivo_error = ?, regla_oro = ? WHERE id = ?", (motivo, regla, row['log_id']))
                    conn.commit()
                    conn.close()
                    st.success("¡Análisis guardado exitosamente!")

# -------------------------------------------------------------
# 6. GUÍA COMPARATIVA AR VS BR
# -------------------------------------------------------------
elif menu == "⚖️ Guía Comparativa AR vs BR":
    st.header("⚖️ Matriz Comparativa Oficial: Argentina vs. Brasil")
    st.caption("Diferencias directas en normas del Ministerio de Salud / SUS[cite: 2].")

    comparativas = [
        {"Área": "Ginecología", "Tema": "Inicio de Citología (PAP)", "🇦🇷 Argentina": "A partir de los 25 años (FASGO 2024)[cite: 2]", "🇧🇷 Brasil": "A partir de los 25 años / Foco en prueba molecular DNA-HPV[cite: 2]"},
        {"Área": "Obstetricia", "Tema": "Vacuna Virus Sincicial (VSR)", "🇦🇷 Argentina": "Obligatoria en gestantes sem 32 a 36[cite: 2]", "🇧🇷 Brasil": "No incorporada de forma rutinaria al PNI gestacional"},
        {"Área": "Salud Pública", "Tema": "Marco Legal de Salud Mental", "🇦🇷 Argentina": "Ley 26.657: Internación involuntaria solo por 'riesgo cierto e inminente'[cite: 2]", "🇧🇷 Brasil": "Ley 10.216: Reforma Psiquiátrica y RAPS (Rede de Atenção Psicossocial)"},
        {"Área": "Salud Pública", "Tema": "Leyes Orgánicas Sanitarias", "🇦🇷 Argentina": "Ley 26.529 (Derechos del Paciente) + Ley 27.610 (IVE/ILE)[cite: 2]", "🇧🇷 Brasil": "Leyes 8.080 (SUS) y 8.142 (Participación Comunitaria)[cite: 2]"},
        {"Área": "Infectología", "Tema": "Tuberculosis de Primera Línea", "🇦🇷 Argentina": "Pautas Técnicas 2026: GeneXpert MTB/RIF + RIPE[cite: 2]", "🇧🇷 Brasil": "TRM-TB (Teste Rápido Molecular) + RHZE (Rifampicina, Isoniazida, Pirazinamida, Etambutol)"}
    ]
    st.dataframe(pd.DataFrame(comparativas), use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 7. MÉTRICAS & RENDIMIENTO
# -------------------------------------------------------------
elif menu == "📊 Métricas & Rendimiento":
    st.header("📊 Analítica y Rendimiento Clínico")

    conn = get_db_connection()
    metrics_df = pd.read_sql('''
        SELECT c.area, c.examen_origen, e.es_correcta
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
    ''', conn)
    conn.close()

    if len(metrics_df) == 0:
        st.info("Aún no hay respuestas registradas para generar gráficos.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Rendimiento por Especialidad")
            area_stats = metrics_df.groupby("area")["es_correcta"].agg(Total="count", Aciertos="sum").reset_index()
            area_stats["Porcentaje_Acierto"] = (area_stats["Aciertos"] / area_stats["Total"]) * 100
            fig_bar = px.bar(area_stats, x="area", y="Porcentaje_Acierto", text_auto=".1f", color="Porcentaje_Acierto", color_continuous_scale="Viridis", labels={"Porcentaje_Acierto": "% de Acierto", "area": "Especialidad"})
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            st.subheader("Distribución Global de Respuestas")
            aciertos_total = metrics_df["es_correcta"].sum()
            errores_total = len(metrics_df) - aciertos_total
            fig_pie = px.pie(values=[aciertos_total, errores_total], names=["Aciertos", "Errores"], color_discrete_sequence=["#2ca02c", "#d62728"])
            st.plotly_chart(fig_pie, use_container_width=True)

# -------------------------------------------------------------
# 8. IMPORTADOR MASIVO (Extractor Flexible de PDFs y Grillas)
# -------------------------------------------------------------
elif menu == "⚙️ Importar Exámenes (PDF / CSV)":
    st.header("⚙️ Importación Masiva de Exámenes")
    st.caption("Subí el cuadernillo de preguntas y pegá las respuestas de la grilla oficial[cite: 3, 6, 9].")

    tab_dual, tab_csv = st.tabs(["📄 Cuadernillo + Grilla Oficial", "📊 Cargar CSV / Excel"])

    with tab_dual:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            pdf_preguntas = st.file_uploader("1. Subir PDF del Cuadernillo (Preguntas)", type=["pdf"], key="cuadernillo")
            nombre_examen = st.text_input("Etiqueta del Examen:", value="🇦🇷 Examen Único")
        with col_c2:
            grilla_input_type = st.radio("2. Formato de la Grilla de Respuestas:", ["Texto / Pegar Grilla", "PDF de Grilla"])
            grilla_texto = ""
            if grilla_input_type == "Texto / Pegar Grilla":
                grilla_texto = st.text_area("Pegá acá la grilla (ej: 1 B 2 C 3 A... o 1-B, 2-C o tabla de respuestas)[cite: 5, 6, 10]:", height=150)
            else:
                pdf_grilla = st.file_uploader("Subir PDF de la Grilla", type=["pdf"], key="grilla_pdf")

        if st.button("🚀 Procesar, Cruzar y Guardar Preguntas"):
            if not pdf_preguntas:
                st.error("Por favor subí primero el PDF del cuadernillo.")
            else:
                # 1. Extracción de Grilla de Respuestas (Regex súper flexible)
                respuestas_dict = {}
                texto_grilla_completo = grilla_texto
                if grilla_input_type == "PDF de Grilla" and pdf_grilla:
                    reader_g = PdfReader(pdf_grilla)
                    texto_grilla_completo = "\n".join([p.extract_text() for p in reader_g.pages if p.extract_text()])

                if texto_grilla_completo:
                    # Captura formatos como '1 B', '1. B', '1) B', '1-B', '1:B' o tablas de dos columnas[cite: 5, 6, 10]
                    pares = re.findall(r'(\d{1,3})\s*[\.\-\:\)\s\t]+([a-dA-D])(?![a-zA-Z])', texto_grilla_completo)
                    for num, letra in pares:
                        respuestas_dict[int(num)] = letra.upper()

                # 2. Extracción de Texto del Cuadernillo
                reader_p = PdfReader(pdf_preguntas)
                raw_text = ""
                for page in reader_p.pages:
                    t = page.extract_text()
                    if t:
                        raw_text += "\n" + t

                # Limpieza de saltos de línea artificiales y normalización
                clean_text = re.sub(r'Examen\s+Único\s+\d{4}', '', raw_text, flags=re.IGNORECASE)
                clean_text = re.sub(r'Página\s+\d+\s+de\s+\d+', '', clean_text, flags=re.IGNORECASE)

                # Segmentador flexible: divide el PDF por números de pregunta '1)', '1.', '1 -'[cite: 3, 5, 11]
                question_blocks = re.split(r'\n(?=\s*\d{1,3}[\.\)\-]\s+)', clean_text)
                
                guardadas = 0
                conn = get_db_connection()
                c = conn.cursor()

                for block in question_blocks:
                    # Verificar si el bloque arranca con un número de pregunta
                    match_num = re.match(r'^\s*(\d{1,3})[\.\)\-]\s+(.*)', block, re.DOTALL)
                    if not match_num:
                        continue
                    
                    num_int = int(match_num.group(1))
                    contenido = match_num.group(2)

                    # Buscar las 4 opciones A, B, C, D dentro del bloque[cite: 3, 10, 11]
                    partes_opciones = re.split(r'\n?\s*[\(\[]?([a-dA-D])[\)\]\.\-]\s+', contenido)
                    
                    if len(partes_opciones) >= 9:
                        # Estructura: [enunciado, 'a', texto_a, 'b', texto_b, 'c', texto_c, 'd', texto_d]
                        enunciado = partes_opciones[0].strip().replace('\n', ' ')
                        op_dict = {}
                        for i in range(1, len(partes_opciones), 2):
                            letra = partes_opciones[i].upper()
                            texto_op = partes_opciones[i+1].strip().replace('\n', ' ')
                            op_dict[letra] = texto_op

                        op_a = op_dict.get('A', '')
                        op_b = op_dict.get('B', '')
                        op_c = op_dict.get('C', '')
                        op_d = op_dict.get('D', '')

                        if op_a and op_b:
                            correcta_oficial = respuestas_dict.get(num_int, "A")
                            
                            # Clasificación temática automática
                            p_low = (enunciado + " " + op_a).lower()
                            area = "Clínica Médica"
                            tema = "Módulo General"
                            if any(k in p_low for k in ["embaraz", "gestant", "parto", "preeclampsia", "uterin", "ive", "ile", "cérvix", "pap"]):
                                area = "Tocoginecología"
                                tema = "Obstetricia y Ginecología"
                            elif any(k in p_low for k in ["lactante", "niño", "pediat", "bronquiolitis", "vacuna", "deshidratación", "puericultura"]):
                                area = "Pediatría"
                                tema = "Pediatría y Puericultura"
                            elif any(k in p_low for k in ["trauma", "neumotórax", "apendicitis", "colecistitis", "hernia", "quirúrg", "atls"]):
                                area = "Cirugía General"
                                tema = "Cirugía y Trauma"
                            elif any(k in p_low for k in ["ley ", "derechos del paciente", "salud mental", "bioética", "epidemiolog"]):
                                area = "Salud Pública y Leyes"
                                tema = "Marco Legal y Bioética"

                            q_id = f"{nombre_examen[:6]}-{num_int}"
                            c.execute('''
                                INSERT OR REPLACE INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                q_id, nombre_examen, area, tema, "Prioridad A",
                                enunciado, op_a, op_b, op_c, op_d,
                                correcta_oficial, "Respuesta oficial según grilla del examen[cite: 6, 10].",
                                "https://drive.google.com", str(datetime.now().date()), 1, 2.5, 0
                            ))
                            guardadas += 1

                conn.commit()
                conn.close()

                if guardadas > 0:
                    st.success(f"🎉 ¡Éxito total! Se extrajeron {guardadas} preguntas completas y se vincularon con {len(respuestas_dict)} respuestas oficiales.")
                else:
                    st.warning("No se detectaron preguntas con el formato estándar. Si tu PDF es una imagen escaneada sin texto seleccionable, cargalo a través de la pestaña 'Cargar CSV / Excel'.")

    with tab_csv:
        st.subheader("Carga vía Planilla CSV")
        up_csv = st.file_uploader("Subir CSV", type=["csv"])
        if up_csv and st.button("Importar CSV"):
            df = pd.read_csv(up_csv)
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in df.iterrows():
                c.execute('''
                    INSERT OR REPLACE INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(r.get('id')), str(r.get('examen_origen')), str(r.get('area')), str(r.get('tema')),
                    str(r.get('incidencia', 'Prioridad A')), str(r.get('pregunta')), str(r.get('opcion_a')),
                    str(r.get('opcion_b')), str(r.get('opcion_c')), str(r.get('opcion_d')), str(r.get('correcta')),
                    str(r.get('justificacion', '')), str(r.get('drive_link', '')), str(datetime.now().date()), 1, 2.5, 0
                ))
            conn.commit()
            conn.close()
            st.success(f"Se cargaron {len(df)} preguntas del archivo.")
