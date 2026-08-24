import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime, timedelta
import random
import hashlib
import json
import google.generativeai as genai

# -------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -------------------------------------------------------------
st.set_page_config(
    page_title="Médica HQ | Residencias & Revalida",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# CONFIGURACIÓN DE GEMINI API
# -------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    model = None

# -------------------------------------------------------------
# BASE DE DATOS LOCAL (SQLite Persistente)
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("medica_hq.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Tabla de Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            nombre TEXT
        )
    ''')
    
    # Tabla de Choices
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
    
    # Tabla de Historial / Errores
    c.execute('''
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
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
    
    # Migración automática de columna faltante
    try:
        c.execute("ALTER TABLE error_log ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Crear usuario inicial por defecto
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ("doctores", hash_password("medicos2026"), "Dra. Luana"))
        
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# CONTROL DE SESIÓN
# -------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

def login_form():
    st.title("🩺 Médica HQ | Ingreso a la Plataforma")
    st.caption("Plataforma de Alto Rendimiento para Residencias de Argentina y Revalida de Brasil")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        u_input = st.text_input("Usuario", key="login_user")
        p_input = st.text_input("Contraseña", type="password", key="login_pass")
        
        if st.button("Iniciar Sesión", use_container_width=True):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (u_input.lower(), hash_password(p_input)))
            usr = c.fetchone()
            conn.close()
            
            if usr:
                st.session_state.authenticated = True
                st.session_state.current_user = usr["username"]
                st.session_state.user_name = usr["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
                
    with col2:
        with st.expander("Crear una nueva cuenta"):
            new_u = st.text_input("Nuevo Usuario")
            new_n = st.text_input("Tu Nombre")
            new_p = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrarse"):
                if new_u and new_p:
                    conn = get_db_connection()
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO users VALUES (?, ?, ?)", (new_u.lower(), hash_password(new_p), new_n))
                        conn.commit()
                        st.success("Cuenta creada exitosamente. Ya podés iniciar sesión.")
                    except:
                        st.error("El usuario ya existe.")
                    conn.close()

if not st.session_state.authenticated:
    login_form()
    st.stop()

# -------------------------------------------------------------
# BARRA LATERAL
# -------------------------------------------------------------
st.sidebar.markdown(f"👤 **{st.session_state.user_name}** (`@{st.session_state.current_user}`)")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.rerun()

st.sidebar.markdown("---")
filtro_pais = st.sidebar.selectbox("Enfoque de Examen", ["🔀 Modo Dual / Integrado", "🇦🇷 Solo Argentina", "🇧🇷 Solo Brasil"])

menu = st.sidebar.radio(
    "Navegación Principal",
    [
        "🏠 Dashboard & Repaso SRS",
        "📅 Cronograma Semanal Detallado",
        "📚 Temario, Algoritmos & Quiz",
        "✨ Generador de Choices con IA",
        "📝 Banco de Choices & Simulacros",
        "📕 Cuaderno de Errores",
        "⚖️ Guía Comparativa AR vs BR",
        "📊 Estadísticas de Rendimiento",
        "⚙️ Cargar CSV / Exámenes"
    ]
)

# -------------------------------------------------------------
# 1. DASHBOARD & REPASO SRS
# -------------------------------------------------------------
if menu == "🏠 Dashboard & Repaso SRS":
    st.header(f"⚡ Bienvenido/a, {st.session_state.user_name}")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM error_log WHERE username = ?", (st.session_state.current_user,))
    total_hechas = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM error_log WHERE username = ? AND es_correcta = 1", (st.session_state.current_user,))
    total_correctas = c.fetchone()[0]
    conn.close()

    precision = int((total_correctas / total_hechas * 100)) if total_hechas > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Racha Activa", "14 Días")
    col2.metric("🎯 Precisión Personal", f"{precision}%")
    col3.metric("📝 Choices Realizados", str(total_hechas))
    col4.metric("📅 Estado de Meta", "Semana 1 / Tocogineco")

    st.markdown("---")
    st.subheader("🧠 Repaso Espaciado Programado para Hoy")
    
    today = str(datetime.now().date())
    conn = get_db_connection()
    due_choices = pd.read_sql("SELECT * FROM choices WHERE next_review <= ?", conn, params=(today,))
    conn.close()

    if len(due_choices) == 0:
        st.success("🎉 ¡Estás al día! No tenés preguntas pendientes de la curva del olvido.")
    else:
        st.info(f"Tenés **{len(due_choices)} choices** listos para consolidar memoria de largo plazo.")
        for idx, row in due_choices.iterrows():
            with st.expander(f"📌 {row['area']} | {row['tema']} ({row['examen_origen']})"):
                st.write(f"**{row['pregunta']}**")
                st.write(f"A) {row['opcion_a']}")
                st.write(f"B) {row['opcion_b']}")
                st.write(f"C) {row['opcion_c']}")
                st.write(f"D) {row['opcion_d']}")
                if st.button("Ver Respuesta Oficial", key=f"srs_btn_{row['id']}"):
                    st.success(f"**Opción Correcta: {row['correcta']}**")
                    st.write(row['justificacion'])

# -------------------------------------------------------------
# 2. CRONOGRAMA SEMANAL DETALLADO
# -------------------------------------------------------------
elif menu == "📅 Cronograma Semanal Detallado":
    st.header("📅 Cronograma de Estudio Detallado (Día por Día)")
    st.caption("Planificación estructurada de lunes a viernes (1 a 2 horas diarias) para compatibilizar trabajo y estudio.")

    cronograma_desglosado = {
        "Semana 1 (Tocoginecología: Trastornos Hipertensivos)": [
            {"Día": "Lunes", "Tema Específico": "Preeclampsia sin Criterios de Severidad: Diagnóstico y seguimiento ambulatorio.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Preeclampsia con Criterios de Severidad: Protocolo Labetalol/Hidralazina EV + Sulfato de Magnesio.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Eclampsia y Síndrome HELLP: Diagnóstico de laboratorio y manejo de urgencia obstétrica.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Hipertensión Crónica y Preeclampsia Sobreimpuesta: Guías MSAL 2024 vs. APS Brasil.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Repaso Integrador + Batería de choices de exámenes anteriores.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 2 (Tocoginecología: Hemorragias y Salud Sexual)": [
            {"Día": "Lunes", "Tema Específico": "Hemorragias de la 1ª Mitad: Aborto y Embarazo Ectópico (Metotrexato vs. Quirúrgico).", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Hemorragias de la 2ª Mitad: DPPNI vs. Placenta Previa vs. Rotura Uterina.", "Meta": "Cuadro diferencial + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Interrupción Voluntaria del Embarazo: Ley 27.610 (IVE/ILE) y Misoprostol.", "Meta": "Lectura Ley + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Anticoncepción de Emergencia y Criterios Médicos de Elegibilidad OMS.", "Meta": "Lectura Guía + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Hemorragia Postparto (Atonía Uterina) + Batería semanal de choices.", "Meta": "20 choices + Error Log"}
        ],
        "Semana 5 (Pediatría: Infecciones Respiratorias IRAB)": [
            {"Día": "Lunes", "Tema Específico": "Bronquiolitis Aguda: Criterios de gravedad (Score de Tal) y soporte hídrico.", "Meta": "Lectura SAP + 10 choices"},
            {"Día": "Martes", "Tema Específico": "Neumonía Adquirida en la Comunidad (NAC): Amoxicilina oral e internación.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Miércoles", "Tema Específico": "Laringitis y Crup: Dexametasona y Adrenalina nebulizada.", "Meta": "Algoritmo + 10 choices"},
            {"Día": "Jueves", "Tema Específico": "Crisis Asmática Pediátrica: Escalonamiento terapéutico GINA/SAP.", "Meta": "Lectura 30 min + 10 choices"},
            {"Día": "Viernes", "Tema Específico": "Batería integradora de IRAB pediátricas.", "Meta": "20 choices + Error Log"}
        ]
    }

    sem_select = st.selectbox("Seleccioná la semana a visualizar en detalle:", list(cronograma_desglosado.keys()))
    df_sem = pd.DataFrame(cronograma_desglosado[sem_select])
    st.dataframe(df_sem, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 3. TEMARIO, ALGORITMOS & QUIZ RÁPIDO
# -------------------------------------------------------------
elif menu == "📚 Temario, Algoritmos & Quiz":
    st.header("📚 Temario Clínico, Algoritmos & Autoevaluación")
    
    tema_sel = st.selectbox(
        "Seleccioná el tema a estudiar:",
        [
            "Preeclampsia y Trastornos Hipertensivos",
            "IRAB Bronquiolitis y Vías Respiratorias Pediátricas",
            "Trauma Torácico y Protocolo ATLS",
            "Dengue y Arbovirosis Urbanas",
            "Leyes Sanitarias de Argentina (26.529 / 26.657 / 27.610)"
        ]
    )

    t1, t2, t3, t4 = st.tabs(["🧠 Resumen & Algoritmo", "⚡ High-Yield Pearls", "⚖️ Comparativa AR vs BR", "📝 Quiz Rápido del Tema (5 Preguntas)"])

    with t1:
        st.subheader("Algoritmo Clínico")
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
            
        if st.button("✨ Generar Algoritmo Personalizado con IA sobre este tema"):
            if model:
                with st.spinner("Diseñando diagrama de flujo clínico..."):
                    prompt = f"Generá un diagrama de flujo en código Mermaid.js sobre el diagnóstico y tratamiento de: {tema_sel}. Devolvé únicamente el bloque de código Mermaid."
                    res = model.generate_content(prompt)
                    st.code(res.text, language="mermaid")
            else:
                st.error("API de Gemini no configurada.")

    with t2:
        st.subheader("⚡ High-Yield Pearls")
        st.write("• **Preeclampsia Severa:** PA $\\ge 160/110\\text{ mmHg}$. Primera línea: Labetalol EV o Hidralazina EV.")
        st.write("• **Prevención de Convulsiones:** Sulfato de Magnesio EV (Esquema Zuspan o Sibai).")
        st.write("• **Antídoto Magnesio:** Gluconato de Calcio al 10% EV.")

    with t3:
        st.subheader("⚖️ Diferencias Normativas Argentina vs. Brasil")
        st.write("• **Argentina:** Inicio de PAP a los 25 años (FASGO 2024); Vacuna VSR obligatoria en semanas 32-36.")
        st.write("• **Brasil:** Tamizaje cervical con rastreo molecular DNA-HPV según directrices del Ministerio de Salud.")

    with t4:
        st.subheader("🎯 Quiz Rápido de Comprobación (Solo este tema)")
        filtro_palabra = "Preeclampsia" if "Preeclampsia" in tema_sel else ("IRAB" if "IRAB" in tema_sel else "Trauma")
        conn = get_db_connection()
        quiz_q = pd.read_sql("SELECT * FROM choices WHERE tema LIKE ? LIMIT 5", conn, params=(f"%{filtro_palabra}%",))
        conn.close()

        if len(quiz_q) == 0:
            st.info("No hay choices cargados en la base de datos para este tema específico. ¡Podés crearlos con la pestaña 'Generador de Choices con IA'!")
        else:
            for idx, q_row in quiz_q.iterrows():
                st.markdown(f"**Pregunta {idx+1}:** {q_row['pregunta']}")
                ans = st.radio(
                    f"Opciones para P{idx+1}:",
                    [f"A) {q_row['opcion_a']}", f"B) {q_row['opcion_b']}", f"C) {q_row['opcion_c']}", f"D) {q_row['opcion_d']}"],
                    key=f"quiz_tema_{q_row['id']}"
                )
                if st.button(f"Comprobar P{idx+1}", key=f"btn_q_{q_row['id']}"):
                    if ans[0] == q_row['correcta']:
                        st.success(f"¡Correcto! Opción {q_row['correcta']}")
                    else:
                        st.error(f"Incorrecto. La respuesta correcta es la opción {q_row['correcta']}.")
                    st.info(q_row['justificacion'])
                st.markdown("---")

# -------------------------------------------------------------
# 4. GENERADOR AUTOMÁTICO DE CHOICES CON IA (GEMINI)
# -------------------------------------------------------------
elif menu == "✨ Generador de Choices con IA":
    st.header("✨ Generador Automático de Choices Médicos con IA")
    st.caption("Creá preguntas inéditas basadas en casos clínicos reales ajustadas a los programas de Argentina y Brasil.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        tema_ia = st.text_input("Tema a evaluar:", value="Preeclampsia Severa y Manejo de Crisis")
        area_ia = st.selectbox("Especialidad:", ["Tocoginecología", "Pediatría", "Clínica Médica", "Cirugía General", "Salud Pública y Leyes"])
    with col_g2:
        enfoque_ia = st.selectbox("Estilo de Examen:", ["🇦🇷 Examen Único / CABA (Argentina)", "🇧🇷 Revalida INEP (Brasil)"])
        cant_q = st.slider("Cantidad de preguntas a generar:", 1, 5, 3)

    if st.button("🚀 Generar y Guardar Choices con IA"):
        if not model:
            st.error("Error al conectar con la API de Gemini.")
        else:
            with st.spinner("La IA está redactando casos clínicos con distractores y justificación médica..."):
                prompt = f"""
                Actuá como miembro del comité evaluador médico de residencias médicas ({enfoque_ia}).
                Generá {cant_q} preguntas de opción múltiple de alta calidad médica sobre: '{tema_ia}' en el área de '{area_ia}'.
                
                Devolvé ÚNICAMENTE un arreglo JSON válido (sin bloques de markdown adicionales) con este formato exacto:
                [
                  {{
                    "pregunta": "Caso clínico detallado...",
                    "opcion_a": "Texto opción A",
                    "opcion_b": "Texto opción B",
                    "opcion_c": "Texto opción C",
                    "opcion_d": "Texto opción D",
                    "correcta": "A", 
                    "justificacion": "Explicación médica detallada citando guías vigentes."
                  }}
                ]
                """
                try:
                    response = model.generate_content(prompt)
                    clean_json = response.text.replace("```json", "").replace("```", "").strip()
                    generated_list = json.loads(clean_json)

                    conn = get_db_connection()
                    c = conn.cursor()
                    guardados = 0
                    for item in generated_list:
                        new_id = f"IA-{random.randint(10000, 99999)}"
                        c.execute('''
                            INSERT INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            new_id, f"✨ IA Generada ({enfoque_ia[:8]})", area_ia, tema_ia, "Prioridad A",
                            item["pregunta"], item["opcion_a"], item["opcion_b"], item["opcion_c"], item["opcion_d"],
                            item["correcta"].upper(), item["justificacion"], "https://drive.google.com",
                            str(datetime.now().date()), 1, 2.5, 0
                        ))
                        guardados += 1
                    conn.commit()
                    conn.close()

                    st.success(f"🎉 ¡Se generaron y guardaron {guardados} choices exitosamente en tu banco de preguntas!")
                    for item in generated_list:
                        with st.expander(f"Caso Clínico Generado: {item['pregunta'][:80]}..."):
                            st.write(item['pregunta'])
                            st.write(f"A) {item['opcion_a']}")
                            st.write(f"B) {item['opcion_b']}")
                            st.write(f"C) {item['opcion_c']}")
                            st.write(f"D) {item['opcion_d']}")
                            st.success(f"Respuesta Correcta: {item['correcta']}")
                            st.info(item['justificacion'])
                except Exception as e:
                    st.error(f"Error procesando la respuesta de la IA: {e}")

# -------------------------------------------------------------
# 5. BANCO DE CHOICES & SIMULACROS
# -------------------------------------------------------------
elif menu == "📝 Banco de Choices & Simulacros":
    st.header("📝 Banco de Choices & Simulacros")

    modo_practica = st.radio(
        "Modalidad de Estudio:",
        ["📚 Por Área Específica", "🎲 Simulacro Aleatorio (Cualquier Tema)"],
        horizontal=True
    )

    conn = get_db_connection()
    if modo_practica == "📚 Por Área Específica":
        area_sel = st.selectbox("Seleccioná el Área Médica:", ["Tocoginecología", "Pediatría", "Clínica Médica", "Cirugía General", "Salud Pública y Leyes"])
        choices_df = pd.read_sql("SELECT * FROM choices WHERE area = ?", conn, params=(area_sel,))
    else:
        choices_df = pd.read_sql("SELECT * FROM choices", conn)
        choices_df = choices_df.sample(frac=1).reset_index(drop=True)
    conn.close()

    if len(choices_df) == 0:
        st.warning("No se encontraron preguntas para los filtros seleccionados.")
    else:
        q_idx = st.selectbox(
            "Seleccionar Pregunta a Resolver:",
            range(len(choices_df)),
            format_func=lambda x: f"P#{x+1}: {choices_df.iloc[x]['tema']} ({choices_df.iloc[x]['examen_origen']})"
        )
        q = choices_df.iloc[q_idx]

        st.markdown(f"#### `{q['examen_origen']}` | **{q['area']}** - *{q['tema']}*")
        st.write(f"### {q['pregunta']}")

        opciones = [
            f"A) {q['opcion_a']}",
            f"B) {q['opcion_b']}",
            f"C) {q['opcion_c']}",
            f"D) {q['opcion_d']}"
        ]

        resp_usr = st.radio("Opciones disponibles:", opciones, key=f"prax_{q['id']}")
        flag_duda = st.checkbox("🏷️ Marcar con Duda / Flag", key=f"fl_{q['id']}")

        if st.button("Confirmar Respuesta", key=f"sub_{q['id']}"):
            letra_elegida = resp_usr[0]
            es_correcta = 1 if letra_elegida == q['correcta'] else 0

            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO error_log (username, choice_id, fecha, respuesta_dada, es_correcta, flag_duda, motivo_error, regla_oro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (st.session_state.current_user, q['id'], datetime.now(), letra_elegida, es_correcta, 1 if flag_duda else 0, "", ""))
            conn.commit()
            conn.close()

            if es_correcta:
                st.success(f"🎉 ¡CORRECTO! Opción {q['correcta']}")
            else:
                st.error(f"❌ INCORRECTO. La respuesta oficial era la opción {q['correcta']}.")

            st.info(f"**Fundamento Clínico:** {q['justificacion']}")

# -------------------------------------------------------------
# 6. CUADERNO DE ERRORES DEL USUARIO
# -------------------------------------------------------------
elif menu == "📕 Cuaderno de Errores":
    st.header(f"📕 Libro de Errores | {st.session_state.user_name}")
    st.caption("Solo se muestran las preguntas falladas o marcadas con duda en tu cuenta.")

    conn = get_db_connection()
    errores_df = pd.read_sql('''
        SELECT e.id as log_id, e.fecha, e.respuesta_dada, e.es_correcta, e.flag_duda, e.motivo_error, e.regla_oro,
               c.pregunta, c.correcta, c.justificacion, c.area, c.tema, c.examen_origen
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
        WHERE e.username = ? AND (e.es_correcta = 0 OR e.flag_duda = 1)
        ORDER BY e.fecha DESC
    ''', conn, params=(st.session_state.current_user,))
    conn.close()

    if len(errores_df) == 0:
        st.success("✨ ¡Felicitaciones! No tenés errores ni dudas registradas.")
    else:
        st.info(f"Tenés **{len(errores_df)} preguntas registradas** para análisis.")
        for idx, row in errores_df.iterrows():
            with st.expander(f"❌ {row['area']} | {row['tema']} ({row['examen_origen']}) | Marcaste: {row['respuesta_dada']} | Correcta: {row['correcta']}"):
                st.write(f"**Enunciado:** {row['pregunta']}")
                st.write(f"**Justificación:** {row['justificacion']}")
                
                motivo = st.selectbox(
                    "¿Por qué fallaste?",
                    ["Error de lectura / Apuro", "Duda 50/50", "Falta de teoría", "Confusión de dosis"],
                    key=f"mot_{row['log_id']}"
                )
                regla = st.text_input("💡 Tu regla para evitarlo la próxima:", value=row['regla_oro'] if row['regla_oro'] else "", key=f"reg_{row['log_id']}")
                
                if st.button("Guardar en mi Bitácora", key=f"save_b_{row['log_id']}"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE error_log SET motivo_error = ?, regla_oro = ? WHERE id = ?", (motivo, regla, row['log_id']))
                    conn.commit()
                    conn.close()
                    st.success("Guardado en tu perfil.")

# -------------------------------------------------------------
# 7. GUÍA COMPARATIVA AR VS BR
# -------------------------------------------------------------
elif menu == "⚖️ Guía Comparativa AR vs BR":
    st.header("⚖️ Matriz Comparativa Oficial: Argentina vs. Brasil")
    st.caption("Diferencias normativas del Ministerio de Salud y del SUS.")

    comparativas = [
        {"Área": "Ginecología", "Tema": "Inicio de Citología (PAP)", "🇦🇷 Argentina": "A partir de los 25 años (FASGO 2024)", "🇧🇷 Brasil": "A partir de los 25 años / Foco en prueba molecular DNA-HPV"},
        {"Área": "Obstetricia", "Tema": "Vacuna Virus Sincicial (VSR)", "🇦🇷 Argentina": "Obligatoria en gestantes sem 32 a 36", "🇧🇷 Brasil": "No incorporada universalmente al PNI gestacional"},
        {"Área": "Salud Pública", "Tema": "Marco Legal de Salud Mental", "🇦🇷 Argentina": "Ley 26.657: Internación involuntaria solo por 'riesgo cierto e inminente'", "🇧🇷 Brasil": "Ley 10.216: Reforma Psiquiátrica y RAPS"},
        {"Área": "Salud Pública", "Tema": "Leyes Orgánicas Sanitarias", "🇦🇷 Argentina": "Ley 26.529 (Derechos) + Ley 27.610 (IVE/ILE)", "🇧🇷 Brasil": "Leyes 8.080 (SUS) y 8.142 (Participación Comunitaria)"},
        {"Área": "Infectología", "Tema": "Tuberculosis de Primera Línea", "🇦🇷 Argentina": "Pautas Técnicas: GeneXpert MTB/RIF + RIPE", "🇧🇷 Brasil": "TRM-TB (Teste Rápido Molecular) + RHZE"}
    ]
    st.dataframe(pd.DataFrame(comparativas), use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 8. ESTADÍSTICAS DEL USUARIO
# -------------------------------------------------------------
elif menu == "📊 Estadísticas de Rendimiento":
    st.header(f"📊 Estadísticas Personales | {st.session_state.user_name}")

    conn = get_db_connection()
    metrics_df = pd.read_sql('''
        SELECT c.area, c.examen_origen, e.es_correcta
        FROM error_log e
        JOIN choices c ON e.choice_id = c.id
        WHERE e.username = ?
    ''', conn, params=(st.session_state.current_user,))
    conn.close()

    if len(metrics_df) == 0:
        st.info("Aún no tenés suficientes preguntas resueltas para generar gráficos.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Rendimiento por Especialidad")
            area_stats = metrics_df.groupby("area")["es_correcta"].agg(Total="count", Aciertos="sum").reset_index()
            area_stats["Porcentaje"] = (area_stats["Aciertos"] / area_stats["Total"]) * 100
            fig = px.bar(area_stats, x="area", y="Porcentaje", text_auto=".1f", color="Porcentaje", color_continuous_scale="Teal", labels={"Porcentaje": "% Acierto", "area": "Especialidad"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Proporción Global de Aciertos")
            fig_p = px.pie(values=[metrics_df['es_correcta'].sum(), len(metrics_df)-metrics_df['es_correcta'].sum()], names=["Aciertos", "Errores"], color_discrete_sequence=["#2ecc71", "#e74c3c"])
            st.plotly_chart(fig_p, use_container_width=True)

# -------------------------------------------------------------
# 9. CARGA DE EXÁMENES CSV
# -------------------------------------------------------------
elif menu == "⚙️ Cargar CSV / Exámenes":
    st.header("⚙️ Importar Lotes de Preguntas CSV")
    st.caption("Subí tu archivo de preguntas generado.")

    uploaded_csv = st.file_uploader("Subir archivo CSV", type=["csv"])
    if uploaded_csv is not None:
        df_up = pd.read_csv(uploaded_csv)
        st.write("Vista previa:")
        st.dataframe(df_up.head(3))
        if st.button("Guardar en la Base de Datos"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in df_up.iterrows():
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
            st.success(f"¡Se importaron {len(df_up)} preguntas exitosamente!")
