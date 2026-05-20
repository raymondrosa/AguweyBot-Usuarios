import streamlit as st
import requests
import io
import chardet
from PyPDF2 import PdfReader
from datetime import datetime

st.set_page_config(page_title="AguweyBot", page_icon="🤖", layout="wide")

# ============================================
# ESTILOS
# ============================================
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
    border: 1px solid #00ffff;
    box-shadow: 0 0 30px rgba(0, 255, 255, 0.2);
}
h1 {
    color: #00ffff !important;
    text-align: center;
    text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
}
.chat-message {
    background: linear-gradient(145deg, #1e2a3a, #15232e);
    border-left: 6px solid #00ffff;
    border-radius: 12px;
    padding: 1rem;
    margin: 0.5rem 0;
    color: white;
}
[data-testid="stSidebar"] {
    background: linear-gradient(165deg, #0e1219, #0a0e14);
    border-right: 2px solid #00ffff;
}
.stButton > button {
    background: linear-gradient(145deg, #00cccc, #00ffff);
    color: black !important;
    font-weight: bold;
    border-radius: 20px;
}
</style>
""", unsafe_allow_html=True)

# ============================================
# INICIALIZACIÓN
# ============================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "document_content" not in st.session_state:
    st.session_state.document_content = None
if "document_name" not in st.session_state:
    st.session_state.document_name = None

# API Keys
MISTRAL_API_KEY = st.secrets.get("MISTRAL_API_KEY", "")
if not MISTRAL_API_KEY:
    st.error("❌ Configura MISTRAL_API_KEY en los secrets")

# ============================================
# FUNCIONES
# ============================================
def leer_archivo(uploaded_file):
    """Lee archivo y extrae texto"""
    try:
        nombre = uploaded_file.name.lower()
        contenido = ""
        
        if nombre.endswith('.pdf'):
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    contenido += text + "\n"
            return contenido, f"PDF leído: {len(reader.pages)} páginas"
        
        elif nombre.endswith('.txt'):
            raw_data = uploaded_file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding'] or 'utf-8'
            contenido = raw_data.decode(encoding)
            return contenido, f"TXT leído: {len(contenido.split())} palabras"
        
        else:
            return None, f"Formato no soportado: {nombre.split('.')[-1]}"
            
    except Exception as e:
        return None, f"Error: {str(e)}"

def preguntar_mistral(pregunta, contexto):
    """Pregunta a Mistral API"""
    if not MISTRAL_API_KEY:
        return "❌ API key no configurada"
    
    try:
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = """Eres AguweyBot, un asistente experto en análisis de documentos.
Responde SOLO basado en el contenido del documento proporcionado.
Si la respuesta no está en el documento, di que no lo encuentras.
Sé claro, conciso y profesional."""
        
        user_content = f"""
DOCUMENTO:
{contexto[:3000]}

PREGUNTA: {pregunta}

INSTRUCCIÓN: Responde basado ESTRICTAMENTE en el documento.
"""
        
        data = {
            "model": "ministral-3b-latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "max_tokens": 1000
        }
        
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"❌ Error API: {response.status_code}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ============================================
# INTERFAZ
# ============================================
st.title("🤖 AguweyBot")
st.markdown('<p style="text-align: center">Asistente inteligente para análisis de documentos</p>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("## 📎 Documentos")
    
    uploaded_file = st.file_uploader(
        "Sube un documento",
        type=["pdf", "txt"],
        help="Formatos soportados: PDF, TXT"
    )
    
    if uploaded_file:
        if st.button("📖 Procesar documento", use_container_width=True):
            with st.spinner("Leyendo documento..."):
                contenido, mensaje = leer_archivo(uploaded_file)
                if contenido:
                    st.session_state.document_content = contenido
                    st.session_state.document_name = uploaded_file.name
                    st.success(f"✅ {mensaje}")
                    st.balloons()
                else:
                    st.error(f"❌ {mensaje}")
    
    if st.session_state.document_content:
        st.markdown("---")
        st.markdown("### 📄 Documento activo")
        st.info(f"**Archivo:** {st.session_state.document_name}")
        st.info(f"**Tamaño:** {len(st.session_state.document_content):,} caracteres")
        
        if st.button("🗑️ Limpiar documento", use_container_width=True):
            st.session_state.document_content = None
            st.session_state.document_name = None
            st.rerun()
    
    st.markdown("---")
    st.markdown("### ℹ️ Info")
    st.markdown("""
    **Formatos soportados:**
    - 📄 PDF
    - 📃 TXT
    
    **Consejos:**
    1. Sube un documento
    2. Haz clic en "Procesar"
    3. Pregunta sobre su contenido
    """)
    
    if st.button("🔄 Nueva conversación", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Mostrar mensajes
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(f'<div class="chat-message">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f"**Tú:** {msg['content']}")

# Input
if prompt := st.chat_input("Escribe tu pregunta aquí..."):
    # Agregar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(f"**Tú:** {prompt}")
    
    # Verificar si hay documento
    if not st.session_state.document_content:
        respuesta = "⚠️ **Primero debes subir y procesar un documento.**\n\n1. Ve al panel izquierdo\n2. Sube un archivo PDF o TXT\n3. Haz clic en 'Procesar documento'\n4. Luego haz tu pregunta"
    else:
        with st.chat_message("assistant"):
            with st.spinner("🤔 Analizando el documento..."):
                respuesta = preguntar_mistral(prompt, st.session_state.document_content)
                st.markdown(f'<div class="chat-message">{respuesta}</div>', unsafe_allow_html=True)
    
    st.session_state.messages.append({"role": "assistant", "content": respuesta})

# Footer
st.markdown("""
<div style="position: fixed; bottom: 0; left: 0; right: 0; background: rgba(10,12,16,0.95); border-top: 2px solid #00ffff; padding: 0.5rem; text-align: center; font-size: 0.8rem; color: #e0e5f0;">
    <strong>CC-SA</strong> Prof. Raymond Rosa Ávila • AguweyBot • 2026
</div>
""", unsafe_allow_html=True)
