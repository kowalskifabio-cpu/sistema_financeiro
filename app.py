import streamlit as st
import pandas as pd
from datetime import datetime
from ofxtools.Parser import OFXTree
import gspread
from google.oauth2.service_account import Credentials
import io

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# ID DA PLANILHA (Fornecido pelo usuário)
ID_DA_PLANILHA = "1FLCbuzrg1UL1yatdIas6aDBBjhc__mebdhUYxIt0NQk"

def conectar_planilha():
    """Realiza a conexão com o Google Sheets usando a Service Account."""
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        else:
            st.error("Erro: Bloco [gcp_service_account] não encontrado nos Secrets.")
            return None
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro na conexão com Google: {e}")
        return None

def check_password():
    """Gerencia a autenticação do usuário."""
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
    """Lê o arquivo OFX sem usar .decode(), tratando o conteúdo de forma universal."""
    try:
        # Lê o conteúdo bruto e converte para string de forma segura
        raw_bytes = uploaded_file.read()
        
        # Tenta decodificar apenas se for necessário; caso contrário, trata como texto
        try:
            content = raw_bytes.decode('utf-8')
        except (UnicodeDecodeError, AttributeError):
            content = raw_bytes if isinstance(raw_bytes, str) else raw_bytes.decode('iso-8859-1')
            
        lines = content.splitlines()
        
        # Limpeza do cabeçalho OFX (Corrigindo o erro do C6 Bank) 
        clean_lines = []
        for line in lines:
            if ":" in line and "<" not in line:
                key, value = line.split(":", 1)
                clean_lines.append(f"{key.strip()}:{value.replace(' ', '').strip()}")
            else:
                clean_lines.append(line)
        
        clean_content = "\n".join(clean_lines)
        
        # Processamento do OFX
        parser = OFXTree()
        parser.parse(io.StringIO(clean_content))
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

# --- EXECUÇÃO DO APLICATIVO ---
if check_password():
    st.sidebar.title("Navegação")
    menu = st.sidebar.radio("Ir para:", ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"])

    if menu == "Resumo":
        st.title("📊 Resumo de Gestão de Caixa")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Saldos Atuais")
            df_saldos = pd.DataFrame({
                'Conta': ['Sicredi - CC', 'Caixa Federal', 'Caixinha'],
                'Saldo': [113901.84, 67900.49, 4174.42]
            })
            st.table(df_saldos)
            st.metric("Total Geral", f"R$ {df_saldos['Saldo'].sum():,.2f}")
        with col2:
            st.subheader("📈 Tendência de Fluxo")
            chart_data = pd.DataFrame({
                'Data': pd.date_range(start='2026-02-01', periods=10, freq='D'),
                'Saldo': [150000, 155000, 152000, 160000, 185000, 182000, 185976, 185976, 185976, 185976]
            })
            st.line_chart(chart_data.set_index('Data'))

    elif menu == "Importar Extrato":
        st.title("📥 Importação de Extratos (.OFX)")
        uploaded_file = st.file_uploader("Selecione o arquivo .ofx", type=['ofx'])
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
                            dados_atuais = pd.DataFrame(ws.get_all_records())
                            if not dados_atuais.empty and 'FITID' in dados_atuais.columns:
                                novos_dados = df_import[~df_import['FITID'].astype(str).isin(dados_atuais['FITID'].astype(str))]
                            else:
                                novos_dados = df_import
                            if not novos_dados.empty:
                                ws.append_rows(novos_dados.values.tolist())
                                st.success(f"Sucesso! {len(novos_dados)} transações adicionadas.")
                            else:
                                st.warning("As transações já constam na planilha.")
                        except Exception as e:
                            st.error(f"Erro ao gravar na planilha: {e}")

    elif menu == "Relatório Mensal":
        st.title("📊 Painel de Acompanhamento (DRE)")
        dados_relatorio = {
            "RESULTADO": ["RECEITAS OPERACIONAIS (A)", "  ↑ Receita Serviços", "CUSTOS OPERACIONAIS (B)", "MARGEM DE CONTRIBUIÇÃO (A+B)"],
            "Jan": [106551, 93967, -24682, 81869],
            "Fev": [135882, 77900, -43475, 92407],
            "Mar": [94237, 60537, -8251, 85986]
        }
        st.dataframe(pd.DataFrame(dados_relatorio), use_container_width=True, hide_index=True)

    elif menu == "Cadastros":
        st.title("⚙️ Configurações")
        st.write("Bancos cadastrados: Sicredi, Caixa Federal, Caixinha.")
