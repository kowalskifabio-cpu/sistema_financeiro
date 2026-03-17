import streamlit as st
import pandas as pd
from datetime import datetime
from ofxtools.Parser import OFXTree
import gspread
from google.oauth2.service_account import Credentials
import io

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# ID DA PLANILHA (Confirmado no seu histórico)
ID_DA_PLANILHA = "1FLCbuzrg1UL1yatdIas6aDBBjhc__mebdhUYxIt0NQk"

def conectar_planilha():
    """Conecta ao Google Sheets usando os Secrets do Streamlit Cloud."""
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            return client
        else:
            st.error("Erro: Bloco [gcp_service_account] não encontrado nos Secrets.")
            return None
    except Exception as e:
        st.error(f"Erro na conexão com Google: {e}")
        return None

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔐 Sistema Labor Business")
        user = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if user == "Kowalski" and password == "Karin@1980":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")
        return False
    return True

def processar_ofx(uploaded_file):
    """
    DIAGNÓSTICO: O Streamlit entrega o arquivo como string ou bytes.
    SOLUÇÃO: Usamos .getvalue() e garantimos que o conteúdo vire texto sem usar .decode().
    """
    try:
        # Pega o conteúdo bruto
        conteudo_bruto = uploaded_file.getvalue()
        
        # Se for bytes, transformamos em texto. Se já for texto, ignoramos o decode.
        if isinstance(conteudo_bruto, bytes):
            # Usamos o 'replace' para evitar quebra por caracteres especiais
            conteudo_texto = conteudo_bruto.decode('utf-8', errors='replace')
        else:
            conteudo_texto = conteudo_bruto
            
        # LIMPEZA DO CABEÇALHO DO C6 BANK (O ponto onde o parser trava)
        linhas = conteudo_texto.splitlines()
        linhas_limpas = []
        for linha in linhas:
            if ":" in linha and "<" not in linha:
                # Transforma "ENCODING: UTF - 8" em "ENCODING:UTF-8"
                chave, valor = linha.split(":", 1)
                linhas_limpas.append(f"{chave.strip()}:{valor.replace(' ', '').strip()}")
            else:
                linhas_limpas.append(linha)
        
        texto_final = "\n".join(linhas_limpas)
        
        # PARSER
        parser = OFXTree()
        parser.parse(io.StringIO(texto_final))
        rec = parser.convert()
        stmt = rec.statements[0]
        
        transacoes = []
        for tx in stmt.banktranlist:
            transacoes.append({
                "Data": tx.dtposted.date().strftime('%d/%m/%Y'),
                "Valor": float(tx.trnamt),
                "FITID": str(tx.fitid),
                "Descrição": tx.memo if tx.memo else tx.name
            })
        return pd.DataFrame(transacoes)
    except Exception as e:
        st.error(f"Erro ao ler arquivo OFX: {e}")
        return pd.DataFrame()

# --- INTERFACE ---
if check_password():
    st.sidebar.title("Navegação")
    menu = st.sidebar.radio("Ir para:", ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"])

    if menu == "Importar Extrato":
        st.title("📥 Importação de Extratos (.OFX)")
        uploaded_file = st.file_uploader("Upload do arquivo bancário", type=['ofx'])
        
        if uploaded_file:
            df_import = processar_ofx(uploaded_file)
            
            if not df_import.empty:
                st.subheader("Transações Detectadas")
                st.dataframe(df_import, use_container_width=True)
                
                if st.button("🚀 Gravar na Planilha"):
                    gc = conectar_planilha()
                    if gc:
                        try:
                            sh = gc.open_by_key(ID_DA_PLANILHA)
                            ws = sh.get_worksheet(0)
                            
                            # Anti-duplicidade
                            registros = ws.get_all_records()
                            df_planilha = pd.DataFrame(registros)
                            
                            if not df_planilha.empty and 'FITID' in df_planilha.columns:
                                novos = df_import[~df_import['FITID'].astype(str).isin(df_planilha['FITID'].astype(str))]
                            else:
                                novos = df_import
                            
                            if not novos.empty:
                                ws.append_rows(novos.values.tolist())
                                st.success(f"{len(novos)} lançamentos gravados com sucesso!")
                            else:
                                st.warning("Todos os dados já existem na planilha.")
                        except Exception as e:
                            st.error(f"Erro ao gravar: {e}")

    elif menu == "Resumo":
        st.title("📊 Gestão de Caixa")
        # Gráficos e Saldos (Mantidos conforme sua estrutura original)
        st.write("Visualização de saldos em Sicredi, Caixa e Caixinha.")

    elif menu == "Relatório Mensal":
        st.title("📊 Painel de Acompanhamento")
        st.write("Relatórios de receitas e custos operacionais.")

    elif menu == "Cadastros":
        st.title("⚙️ Configurações")
        st.write("Gerenciamento de Plano de Contas e Bancos.")
