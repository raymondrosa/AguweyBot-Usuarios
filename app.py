# app_simple.py - Versión sin autenticación para prueba
import streamlit as st

st.set_page_config(page_title="AguweyBot Test", page_icon="🤖")

st.title("🤖 AguweyBot - Test de Instalación")
st.success("✅ La app se está ejecutando correctamente!")

# Verificar versiones
import sys
st.write(f"Python version: {sys.version}")

import pandas as pd
st.write(f"Pandas version: {pd.__version__}")

# Resto de tu código aquí...
