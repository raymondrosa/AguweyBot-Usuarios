# ============================================
# AGUWEYBOT - VERSIÓN PARA STREAMLIT CLOUD
# CREACIÓN DIRECTA EN GITHUB - MAYO 2026
# ============================================

import streamlit as st
import base64
import time
import io
import json
import requests
import re
from datetime import datetime
from typing import Optional, List, Dict

# Documentos
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
import chardet

# Audio
try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# ============================================
# CONFIGURACIÓN
# ============================================

st.set_page_config(
    page_title="AguweyBot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Obtener API keys de los secrets
try:
    MISTRAL_API_KEY = st.secrets["MISTRAL_API_KEY"]
except:
    MISTRAL_API_KEY = None

OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", None)

# URLs API
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "ministral-3b-latest"

# ============================================
# ESTILOS CSS
# ============================================

def aplicar_estilos():
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0a0c10, #1a1f2a);
    }
    .main .block-container {
        background-color: rgba(10, 12, 16, 0.85);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        margin: 1rem auto;
        border: 1px solid #00ffff;
        box-shadow: 0 0 30px rgba(0, 255, 255, 0.2);
        max-width: 1200px !important;
    }
    h1 {
        color: #00ffff !important;
        text-align: center;
        text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
        margin-bottom: 0.5rem;
    }
    .subtitle {
        text-align: center;
        color: #e0e5f0;
        margin-bottom: 2rem;
    }
    .respuesta-aguwey {
        background: linear-gradient(145deg, #1e2a3a, #15232e);
        border-left: 6px solid #00ffff;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        color: white;
        font-size: 1rem;
        line-height: 1.6;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(165deg, #0e1219, #0a0e14);
        border-right: 2px solid #00ffff;
    }
    .stButton > button {
        background: linear-gradient(145deg, #00cccc, #00ffff);
        color: black !important;
        font-weight: bold;
        border: none;
        border-radius: 20px;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 255, 255, 0.3);
    }
    .stAlert {
        background-color: rgba(0, 255, 255, 0.1);
        border-left: 4px solid #00ffff;
    }
    .fixed-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(10, 12, 16, 0.95);
        border-top: 2px solid #00ffff;
        padding: 0.5rem;
        text-align: center;
        color: #e0e5f0;
        z-index: 999;
        font-size: 0.8rem;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================
# CLASES Y FUNCIONES
# ============================================

class DatosArchivo:
    def __init__(self):
        self.nombre: str = ""
        self.contenido_completo: str = ""
        self.tipo: str = ""
        self.num_caracteres: int = 0
        self.resumen: str = ""

def truncar_contexto(texto: str, max_caracteres: int = 4000) -> str:
    if len(texto) <= max_caracteres:
        return texto
    return texto[:max_caracteres] + "\n...[texto truncado]..."

def leer_archivo_completo(uploaded_file):
    if uploaded_file is None:
        return None, "No hay archivo"
    
    try:
        nombre = uploaded_file.name.lower()
        datos = DatosArchivo()
        datos.nombre = uploaded_file.name
        
        # Procesar PDF
        if nombre.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            texto_completo = []
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                if texto and texto.strip():
                    texto_completo.append(f"--- PÁGINA {i+1} ---\n{texto}")
            datos.contenido_completo = "\n\n".join(texto_completo)
            datos.tipo = "pdf"
            datos.resumen = f"📄 PDF con {len(reader.pages)} páginas"
        
        # Procesar Excel
        elif nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file)
            datos.contenido_completo = f"📊 ARCHIVO EXCEL: {uploaded_file.name}\n"
            datos.contenido_completo += f"Filas: {len(df)}, Columnas: {len(df.columns)}\n"
            datos.contenido_completo += f"Columnas: {', '.join(df.columns.tolist())}\n\n"
            datos.contenido_completo += df.to_string()
            datos.tipo = "excel"
            datos.resumen = f"📊 Excel con {len(df)} filas y {len(df.columns)} columnas"
        
        # Procesar CSV
        elif nombre.endswith(".csv"):
            raw_data = uploaded_file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding'] or 'utf-8'
            df = pd.read_csv(io.BytesIO(raw_data), encoding=encoding)
            datos.contenido_completo = f"📊 ARCHIVO CSV: {uploaded_file.name}\n"
            datos.contenido_completo += f"Filas: {len(df)}, Columnas: {len(df.columns)}\n\n"
            datos.contenido_completo += df.to_string()
            datos.tipo = "csv"
            datos.resumen = f"📊 CSV con {len(df)} filas"
        
        # Procesar TXT
        elif nombre.endswith(".txt"):
            contenido = uploaded_file.read()
            result = chardet.detect(contenido)
            encoding = result['encoding'] or 'utf-8'
            datos.contenido_completo = contenido.decode(encoding)
            datos.tipo = "txt"
            palabras = len(datos.contenido_completo.split())
            datos.resumen = f"📝 TXT con {palabras} palabras"
        
        # Procesar Word
        elif nombre.endswith(".docx"):
            doc = Document(uploaded_file)
            texto_completo = [p.text for p in doc.paragraphs if p.text.strip()]
            datos.contenido_completo = "\n".join(texto_completo)
            datos.tipo = "docx"
            palabras = len(datos.contenido_completo.split())
            datos.resumen = f"📝 Word con {palabras} palabras"
        
        else:
            return None, f"❌ Tipo no soportado: .{nombre.split('.')[-1]}"
        
        datos.num_caracteres = len(datos.contenido_completo)
        return datos, None
        
    except Exception as e:
        return None, f"❌ Error al procesar: {str(e)}"

def generar_respuesta_mistral(messages):
    if not MISTRAL_API_KEY:
        return "❌ Error: No se encontró la API key de Mistral. Configúrala en los secrets."
    
    try:
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        data = {
            "model": MODEL_NAME,
            "messages": formatted_messages,
            "temperature": 0.2,
            "max_tokens": 2000
        }
        
        response = requests.post(
            MISTRAL_API_URL,
            headers=headers,
            json=data,
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"❌ Error API ({response.status_code}): {response.text[:200]}"
            
    except requests.exceptions.Timeout:
        return "❌ Error: Tiempo de espera agotado"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ============================================
# MAIN
# ============================================

def main():
    aplicar_estilos()
    
    # Título
    st.markdown("<h1>🤖 AguweyBot</h1>", unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Asistente inteligente con análisis de documentos</p>', unsafe_allow_html=True)
    
    # Inicializar session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "datos_archivo" not in st.session_state:
        st.session_state.datos_archivo = None
    if "primer_mensaje" not in st.session_state:
        st.session_state.primer_mensaje = True
    if "modelo" not in st.session_state:
        st.session_state.modelo = "Mistral"
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 🚀 AguweyBot")
        st.markdown("---")
        
        # Selector de modelo
        st.markdown("### 🧠 Modelo IA")
        modelo_seleccionado = st.radio(
            "Selecciona el modelo:",
            ["Mistral", "Qwen 2.5", "Gemma 4"],
            index=0,
            key="modelo_selector"
        )
        st.session_state.modelo = modelo_seleccionado
        
        st.markdown("---")
        
        # Estado de APIs
        st.markdown("### 🔑 Estado")
        if MISTRAL_API_KEY:
            st.success("✅ Mistral API conectada")
        else:
            st.error("❌ Mistral API no configurada")
            st.info("Configura MISTRAL_API_KEY en los secrets")
        
        st.markdown("---")
        
        # Subir archivo
        st.markdown("### 📎 Subir documento")
        uploaded_file = st.file_uploader(
            "Elige un archivo",
            type=["pdf", "xlsx", "xls", "csv", "txt", "docx"],
            label_visibility="collapsed"
        )
        
        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📖 Procesar", use_container_width=True):
                    with st.spinner("📖 Leyendo archivo..."):
                        datos, error = leer_archivo_completo(uploaded_file)
                        if error:
                            st.error(error)
                        else:
                            st.session_state.datos_archivo = datos
                            st.success(f"✅ {datos.resumen}")
                            st.balloons()
            with col2:
                if st.button("🗑️ Limpiar", use_container_width=True):
                    st.session_state.datos_archivo = None
                    st.rerun()
        
        if st.session_state.datos_archivo:
            with st.expander("📁 Archivo activo", expanded=True):
                datos = st.session_state.datos_archivo
                st.markdown(f"""
                **Nombre:** {datos.nombre}
                **Tipo:** {datos.resumen}
                **Tamaño:** {datos.num_caracteres:,} caracteres
                """)
        
        st.markdown("---")
        
        # Información
        with st.expander("ℹ️ Información"):
            st.markdown("""
            **Formatos soportados:**
            - 📄 PDF
            - 📊 Excel (xlsx, xls)
            - 📈 CSV
            - 📝 Word (docx)
            - 📃 TXT
            
            **Consejos:**
            - Sube el archivo primero
            - Haz clic en "Procesar"
            - Haz preguntas específicas
            """)
        
        st.markdown("---")
        
        # Botón nueva conversación
        if st.button("🔄 Nueva conversación", use_container_width=True):
            st.session_state.messages = []
            st.session_state.datos_archivo = None
            st.rerun()
    
    # Mostrar historial de mensajes
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(f'<div class="respuesta-aguwey">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f"**Tú:** {msg['content']}")
    
    # Mensaje de bienvenida
    if st.session_state.primer_mensaje and not st.session_state.messages:
        st.info("""
        👋 **¡Bienvenido a AguweyBot!**
        
        ### 📝 Cómo usar:
        1. **Sube un archivo** en el panel izquierdo
        2. **Haz clic en "Procesar"** para analizarlo
        3. **Escribe tu pregunta** sobre el contenido
        
        ### 💡 Ejemplos de preguntas:
        - "Resume este documento"
        - "¿Cuáles son los puntos principales?"
        - "Analiza los datos de la tabla"
        - "Extrae las conclusiones importantes"
        
        ### 🔧 Modelos disponibles:
        - **Mistral** (rápido y eficiente)
        - **Qwen 2.5** (potente, requiere OpenRouter)
        - **Gemma 4** (gratuito, requiere OpenRouter)
        """)
        st.session_state.primer_mensaje = False
    
    # Input del usuario
    prompt = st.chat_input("Escribe tu pregunta aquí...")
    
    if prompt:
        # Agregar mensaje del usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(f"**Tú:** {prompt}")
        
        with st.chat_message("assistant"):
            with st.spinner("🤔 Analizando y generando respuesta..."):
                try:
                    # Preparar mensajes para la API
                    messages = [{"role": "system", "content": """Eres AguweyBot, un asistente experto en análisis de documentos.

REGLAS IMPORTANTES:
1. Usa TODO el contenido del archivo para responder
2. Responde de manera clara, concisa y profesional
3. Usa emojis para hacer las respuestas más amigables
4. Si no encuentras algo en el archivo, dilo honestamente
5. No inventes información
6. Si hay datos numéricos, analízalos completamente"""}]
                    
                    # Agregar historial reciente
                    for m in st.session_state.messages[-5:]:
                        messages.append({"role": m["role"], "content": m["content"]})
                    
                    # Agregar contenido del archivo si existe
                    if st.session_state.datos_archivo:
                        datos = st.session_state.datos_archivo
                        contenido_truncado = truncar_contexto(datos.contenido_completo, 3500)
                        contexto = f"""
📁 **ARCHIVO CARGADO:** {datos.nombre}
📊 **TIPO:** {datos.resumen}
📏 **TAMAÑO:** {datos.num_caracteres:,} caracteres

========== CONTENIDO DEL ARCHIVO ==========
{contenido_truncado}
========== FIN DEL CONTENIDO ==========

📝 **PREGUNTA DEL USUARIO:** {prompt}

🔍 **INSTRUCCIÓN:** Responde basándote ESTRICTAMENTE en el contenido del archivo proporcionado arriba.
"""
                        messages.append({"role": "user", "content": contexto})
                    
                    # Generar respuesta según el modelo seleccionado
                    if st.session_state.modelo == "Mistral":
                        respuesta = generar_respuesta_mistral(messages)
                    elif st.session_state.modelo in ["Qwen 2.5", "Gemma 4"]:
                        respuesta = f"🚧 El modelo {st.session_state.modelo} está en desarrollo. Por favor usa el modelo Mistral por ahora. 🔧"
                    else:
                        respuesta = "❌ Modelo no disponible"
                    
                    # Mostrar respuesta
                    st.markdown(f'<div class="respuesta-aguwey">{respuesta}</div>', unsafe_allow_html=True)
                    
                    # Guardar respuesta
                    st.session_state.messages.append({"role": "assistant", "content": respuesta})
                    
                except Exception as e:
                    st.error(f"❌ Error inesperado: {str(e)}")
    
    # Footer
    st.markdown("""
    <div class="fixed-footer">
        <strong>CC-SA</strong> Prof. Raymond Rosa Ávila • AguweyBot v7.0 • 2026
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
