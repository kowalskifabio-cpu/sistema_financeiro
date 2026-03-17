import streamlit as st
import pandas as pd
from datetime import datetime

# CONFIGURAÇÃO
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# LOGIN (Mantido conforme solicitado)
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
                st.error("Acesso negado")
        return False
    return True

if check_password():
    st.sidebar.title("Navegação")
    menu = st.sidebar.radio("Ir para:", ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"])

    # --- ABA: IMPORTAR EXTRATO (A inteligência contra duplicidade) ---
    if menu == "Importar Extrato":
        st.title("📥 Importação de Dados")
        st.info("Dica: Use arquivos .csv ou .xlsx do seu banco.")
        
        uploaded_file = st.file_uploader("Escolha o arquivo do banco", type=['csv', 'xlsx'])
        
        if uploaded_file:
            df_import = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
            st.write("Dados detectados:", df_import.head())
            
            if st.button("Validar e Salvar"):
                # LÓGICA ANTI-DUPLICIDADE:
                # O sistema deve checar se (Data + Valor + Descrição) já existe no Google Sheets
                st.warning("Implementaremos a verificação de 'Hash' para evitar duplicidade na fase de conexão com Sheets.")

    # --- ABA: RELATÓRIO MENSAL (Igual à sua imagem) ---
    elif menu == "Relatório Mensal":
        st.title("📊 Painel de Acompanhamento (DRE/Fluxo)")
        
        # Filtros de Centro de Custo
        centro_filtro = st.multiselect("Filtrar por Centro de Custo", ["Administrativo", "Produção", "Vendas"])
        
        # Simulando a tabela da imagem
        dados_relatorio = {
            "RESULTADO": ["RECEITAS OPERACIONAIS", "  Receita Serviços", "  Receita Vendas", "CUSTOS OPERACIONAIS", "MARGEM DE CONTRIBUIÇÃO"],
            "Jan": [106551, 93967, 12584, -24682, 81869],
            "Fev": [135882, 77900, 57982, -43475, 92407],
            "Mar": [94237, 60537, 33700, -8251, 85986]
        }
        df_dre = pd.DataFrame(dados_relatorio)
        st.table(df_dre)

    # --- ABA: CADASTROS ---
    elif menu == "Cadastros":
        st.title("⚙️ Configurações do Sistema")
        tab1, tab2 = st.tabs(["Plano de Contas", "Contas Bancárias"])
        
        with tab1:
            st.subheader("Cadastrar Nova Categoria")
            nome_cat = st.text_input("Nome da Conta (ex: Aluguel)")
            tipo_cat = st.selectbox("Tipo", ["Receita", "Custo", "Despesa"])
            if st.button("Salvar Categoria"):
                st.success(f"{nome_cat} adicionado ao Plano de Contas!")

        with tab2:
            st.subheader("Contas Bancárias")
            st.write("Atuais: Sicredi, Caixa, Caixinha")
