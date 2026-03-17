import streamlit as st
import pandas as pd
from datetime import datetime
from ofxtools.Parser import OFXTree
import gspread
from google.oauth2.service_account import Credentials

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# 1. DADOS DE CONEXÃO (Service Account e ID da Planilha)
# Integrado conforme solicitado para evitar resumos
GOOGLE_CREDENTIALS = {
    "type": "service_account",
    "project_id": "pesquisa-labor",
    "private_key_id": "416de83105d1c71307292b2a2a5549f4369daf76",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDNOsAqEdsC3Kzo\nnqEDNTq7bBeGZ6cViY6U3nzKxTJkssKa3izdWNiM2G90dC20Raie/FOlu8vJZ2QK\nXSH5rFdYf7bIbS4SP9Me3tEdbQcTncG1D/U8krAEar03dbiel48rIXsZJkqqd0Ev\nIEFQuYmJPaPumMP4tLgKnAIB95xDpBBZdsXAA61LaxBzE4h4C5dbdDhFoRwA+S92\nEQimUe9HQKO7rPPnkCAK8nY60KHcmcUmzyRBuiVwfAh7LII/l3l7MfU4EJHCsQFi\noe3svWjUfeWaDQap3zi0ggwoWOEsNgvSnf9DvQ8Mkhz0BeNrtxaCTOEoXoZrYFdA\nEU6grcMlAgMBAAECggEANgZVN73jjWlSCxpXAGUuxM+7kaIPldfUNNQsvaQTk/aK\nzAHYhZwxxUHkdR9wOJhtvwxlaKd7CdWxvBiwLO11QNK95xz2l889YE7/dWOSDVPl\n/ifpQrzKoR8IGGVg6D61bYEuynwOA7nI6wLurrVowzv6v4BvdjT8ja5ryODJvfQl\neQZLM4f73Ddrc+dtLPNbP9Oo+m6mdxvlOdrfvY6JNTcHEAq98okYiV7lMaOvoE/T\nluUeRIkNTol3khe+IgoQ1ppGLG1AIwcQqIn8ucQZ1Mp2jdmBHxXGnUgqC48QIual\ngI81HHnklkYnMG5lFcteBEixxZcZZTcRWK/2dqQuMQKBgQD0z5q2L+vvOJHRvTdO\nTAu8jI2wBZaCkFA/kMlcwXwYqoCTB/zbWIG9lG9YePc/4Td4rnGp7heHqvYORLDQ\K4hmDrvHdmri1W4UvDU33Q653XCrufhsiCh7ODBuVAvpOhHY+83ZNVCVa21GakNM\nsZYBBqk1U1XScTY8SyMn3eU49wKBgQDWnAadg5Sx1+tacH2KDwateQeFm4N+Oqu4\nya2e1Ez7p18TB9O9MRxYz43DHRC+GgT+UWrf+l/uzD+rVgLYN6tQ5+8iM48PfnTo\nBrgiF4FIU4XnyDf+QW0OC4CTn9Bi0Nxuj/3T2o/VzlUDUClt40F+qn1qcqtK6dW5\nJIOPyAbZwwKBgQDY4nfxQkFm3Roq09SElFCtiWQZdsniABJoTlBm0a+sdpmUKTZ1\n6VJ/71o56mk5+cBYNUvTvXCxK9/zwh1XP8oGiLUJwDpvnaB51EfdpwVd2vXv3cFd\n/b7Hc39Mrz8iL+UR8/tpnJc42USlZo0bDBWV8R3FdYAKAWyIPBT4Q9jI/wKBgCRo\nR78FCX66MJUhLEr1jZ50P9Bst3v8nBE3NZsSTRUMKdbipwsbf8GZRGVrUuHNLDew\nvD7PDONIBy0b5FOl7gxFrI3SzVxFibOrICW4cxhAAyF1F/qsQsH1NZTVsdZxtFOV\nXexI0cnlvQpY2Q5pVT0V0zzxwxlsXfOQvDjyKCddAoGBAJdJ2s1NdQCow2Xi/DaN\nWrn208PyGqyE5NbcgG5/Q0cpEhMcgqbojKxfVOC1NRybp7L7y/CmCanRA/Cz1b/a\nESHSa3GCoYOA0n0+H3Jd0PRRNEG7uQk1QgxrmMO7ZRQUTuVIFH5absTT2q4sGRd4\nzWaxzc1p8KKDDryqMu+G3H2A\n-----END PRIVATE KEY-----\n",
    "client_email": "streamlit-labor@pesquisa-labor.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}

ID_DA_PLANILHA = "1FLCbuzrg1UL1yatdIas6aDBBjhc__mebdhUYxIt0NQk"

def conectar_planilha():
    """Realiza a conexão com o Google Sheets usando a Service Account."""
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        # Se estiver no Streamlit Cloud, tenta pegar dos secrets, senão usa o dicionário fixo
        if "gcp_service_account" in st.secrets:
            # O Streamlit já carrega o dicionário formatado do bloco [gcp_service_account]
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        else:
            creds = Credentials.from_service_account_info(GOOGLE_CREDENTIALS, scopes=scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro na conexão com Google: {e}")
        return None

# 2. SISTEMA DE LOGIN
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

# 3. PROCESSAMENTO DE ARQUIVO OFX
def processar_ofx(arquivo_ofx):
    """Lê o arquivo OFX e extrai as transações."""
    try:
        parser = OFXTree()
        parser.parse(arquivo_ofx)
        rec = parser.convert()
        stmt = rec.statements[0]
        
        transacoes = []
        for tx in stmt.banktranlist:
            transacoes.append({
                "Data": tx.dtposted.date().strftime('%d/%m/%Y'),
                "Valor": float(tx.trnamt),
                "FITID": tx.fitid,
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

    # --- ABA: RESUMO ---
    if menu == "Resumo":
        st.title("📊 Resumo de Gestão de Caixa")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Saldos Atuais")
            df_saldos = pd.DataFrame({
                'Conta': ['Sicredi - Conta Corrente', 'Caixa Econômica Federal', 'Caixinha'],
                'Saldo': [113901.84, 67900.49, 4174.42]
            })
            st.table(df_saldos)
            st.metric("Total Geral", f"R$ {df_saldos['Saldo'].sum():,.2f}")

        with col2:
            st.subheader("📈 Tendência de Fluxo de Caixa")
            chart_data = pd.DataFrame({
                'Data': pd.date_range(start='2026-02-01', periods=10, freq='D'),
                'Saldo': [150000, 155000, 152000, 160000, 185000, 182000, 185976, 185976, 185976, 185976]
            })
            st.line_chart(chart_data.set_index('Data'))

    # --- ABA: IMPORTAR EXTRATO ---
    elif menu == "Importar Extrato":
        st.title("📥 Importação de Extratos Bancários")
        st.info("Utilize arquivos .ofx para garantir a unicidade dos lançamentos (FITID).")
        
        uploaded_file = st.file_uploader("Selecione o arquivo .ofx", type=['ofx'])
        
        if uploaded_file:
            df_import = processar_ofx(uploaded_file)
            
            if not df_import.empty:
                st.subheader("Transações Identificadas")
                st.dataframe(df_import, use_container_width=True)
                
                if st.button("🚀 Gravar Dados na Planilha"):
                    gc = conectar_planilha()
                    if gc:
                        try:
                            # Abre a planilha pelo ID fornecido
                            sh = gc.open_by_key(ID_DA_PLANILHA) 
                            ws = sh.get_worksheet(0) # Acessa a primeira aba
                            
                            # Busca dados existentes para evitar duplicidade pelo FITID
                            dados_atuais = pd.DataFrame(ws.get_all_records())
                            
                            if not dados_atuais.empty and 'FITID' in dados_atuais.columns:
                                # Filtra apenas o que NÃO está na planilha
                                novos_dados = df_import[~df_import['FITID'].astype(str).isin(dados_atuais['FITID'].astype(str))]
                            else:
                                novos_dados = df_import
                            
                            if not novos_dados.empty:
                                ws.append_rows(novos_dados.values.tolist())
                                st.success(f"Sucesso! {len(novos_dados)} novas transações foram gravadas.")
                            else:
                                st.warning("Aviso: Todas as transações deste arquivo já existem na planilha.")
                        except Exception as e:
                            st.error(f"Erro ao gravar na planilha: {e}")
                            st.info("Dica: Certifique-se de que compartilhou a planilha com o e-mail do robô.")

    # --- ABA: RELATÓRIO MENSAL (Conforme imagem do Nibo) ---
    elif menu == "Relatório Mensal":
        st.title("📊 Painel de Acompanhamento (DRE)")
        
        centro_filtro = st.multiselect("Filtrar por Centro de Custo", ["Administrativo", "Produção", "Vendas"])
        
        # Modelo baseado no layout da imagem enviada
        dados_relatorio = {
            "RESULTADO": [
                "RECEITAS OPERACIONAIS (A)", 
                "  ↑ Receita Plano Funerário", 
                "  ↑ Receita Comissão Médicos", 
                "CUSTOS OPERACIONAIS (B)", 
                "  ↓ Impostos sobre receita",
                "  ↓ Folha de Pagamento",
                "MARGEM DE CONTRIBUIÇÃO (A+B)"
            ],
            "Jan": [106551, 93967, 3654, -24682, -3198, -16542, 81869],
            "Fev": [135882, 77900, 3691, -43475, -9138, -14898, 92407],
            "Mar": [94237, 60537, 598, -8251, 0, -4594, 85986]
        }
        df_dre = pd.DataFrame(dados_relatorio)
        st.dataframe(df_dre, use_container_width=True, hide_index=True)

    # --- ABA: CADASTROS ---
    elif menu == "Cadastros":
        st.title("⚙️ Cadastros e Configurações")
        tab1, tab2, tab3 = st.tabs(["Plano de Contas", "Centro de Custos", "Contas Bancárias"])
        
        with tab1:
            st.subheader("Cadastro de Categorias")
            nome_cat = st.text_input("Nome da Conta")
            tipo_cat = st.selectbox("Tipo de Conta", ["Receita Operacional", "Custo Variável", "Despesa Fixa"])
            if st.button("Confirmar Categoria"):
                st.success(f"Categoria {nome_cat} pronta para ser integrada.")

        with tab2:
            st.subheader("Cadastro de Centro de Custos")
            novo_cc = st.text_input("Nome do Centro de Custo")
            if st.button("Confirmar Centro"):
                st.success(f"Centro de Custo {novo_cc} pronto para ser integrado.")

        with tab3:
            st.subheader("Contas Bancárias Ativas")
            st.write("- Sicredi - Conta Corrente")
            st.write("- Caixa Econômica Federal")
            st.write("- Caixinha")
