import streamlit as st
import pandas as pd
from datetime import datetime
from ofxtools.Parser import OFXTree # Necessário instalar: pip install ofxtools

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# 1. SISTEMA DE LOGIN
def check_password():
    """Retorna True se o usuário inseriu a senha correta."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    if not st.session_state["authenticated"]:
        st.title("🔐 Sistema Labor Business")
        user = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        
        if st.button("Entrar"):
            # Credenciais solicitadas
            if user == "Kowalski" and password == "Karin@1980":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Acesso negado")
        return False
    return True

# 2. FUNÇÃO TÉCNICA PARA LER OFX
def processar_ofx(arquivo_ofx):
    """Lê o arquivo OFX e retorna um DataFrame pronto para processamento."""
    try:
        parser = OFXTree()
        parser.parse(arquivo_ofx)
        rec = parser.convert()
        stmt = rec.statements[0] # Considera o primeiro extrato do arquivo
        
        transacoes = []
        for tx in stmt.banktranlist:
            transacoes.append({
                "Data": tx.dtposted.date(),
                "Valor": float(tx.trnamt),
                "FITID": tx.fitid, # Identificador Único (Chave para não duplicar)
                "Descrição": tx.memo if tx.memo else tx.name
            })
        
        return pd.DataFrame(transacoes)
    except Exception as e:
        st.error(f"Erro ao ler arquivo OFX: {e}")
        return pd.DataFrame()

# EXECUÇÃO DO APP
if check_password():
    st.sidebar.title("Navegação")
    menu = st.sidebar.radio("Ir para:", ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"])

    # --- ABA: RESUMO (Dashboard Inicial) ---
    if menu == "Resumo":
        st.title("📊 Resumo de Gestão de Caixa")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Saldos Atuais")
            # Dados exemplificados para visualização
            df_saldos = pd.DataFrame({
                'Conta': ['Sicredi', 'Caixa Federal', 'Caixinha'],
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

    # --- ABA: IMPORTAR EXTRATO (Agora com suporte a OFX) ---
    elif menu == "Importar Extrato":
        st.title("📥 Importação de Extratos")
        st.info("O arquivo OFX é o ideal para evitar duplicidade através do código FITID.")
        
        # Suporte a OFX, CSV e XLSX
        uploaded_file = st.file_uploader("Escolha o arquivo do banco", type=['ofx', 'csv', 'xlsx'])
        
        if uploaded_file:
            if uploaded_file.name.endswith('.ofx'):
                # Processamento específico de OFX
                df_import = processar_ofx(uploaded_file)
            elif uploaded_file.name.endswith('.xlsx'):
                df_import = pd.read_excel(uploaded_file)
            else:
                df_import = pd.read_csv(uploaded_file)
            
            if not df_import.empty:
                st.subheader("Dados Detectados no Arquivo")
                st.write(df_import)
                
                if st.button("Validar e Salvar no Sistema"):
                    # Aqui, ao conectar no Sheets/Banco, faremos a busca pelo FITID
                    st.warning("Próxima etapa: Validar se esses FITIDs já existem no seu banco de dados para evitar duplicidade.")
            else:
                st.error("Não foi possível extrair dados deste arquivo.")

    # --- ABA: RELATÓRIO MENSAL (DRE conforme imagem) ---
    elif menu == "Relatório Mensal":
        st.title("📊 Painel de Acompanhamento (Realizado)")
        
        # Filtros conforme solicitado (Centro de Custos)
        centro_filtro = st.multiselect("Filtrar por Centro de Custo", ["Administrativo", "Produção", "Vendas"])
        
        # Estrutura baseada na imagem do Nibo enviada
        dados_relatorio = {
            "RESULTADO": [
                "RECEITAS OPERACIONAIS (A)", 
                "  ↑ Receita Plano Funerário", 
                "  ↑ Receita Serviços", 
                "CUSTOS OPERACIONAIS (B)", 
                "  ↓ Impostos sobre receita",
                "MARGEM DE CONTRIBUIÇÃO (A+B)"
            ],
            "Jan": [106551, 93967, 12584, -24682, -3198, 81869],
            "Fev": [135882, 77900, 57982, -43475, -9138, 92407],
            "Mar": [94237, 60537, 33700, -8251, 0, 85986]
        }
        df_dre = pd.DataFrame(dados_relatorio)
        st.dataframe(df_dre, use_container_width=True, hide_index=True)

    # --- ABA: CADASTROS ---
    elif menu == "Cadastros":
        st.title("⚙️ Configurações e Planos")
        tab1, tab2, tab3 = st.tabs(["Plano de Contas", "Centro de Custos", "Contas Bancárias"])
        
        with tab1:
            st.subheader("Estrutura de Categorias")
            nome_cat = st.text_input("Nome da Nova Conta (ex: Aluguel)")
            tipo_cat = st.selectbox("Classificação", ["Receita", "Custo Variável", "Despesa Fixa"])
            if st.button("Salvar no Plano de Contas"):
                st.success(f"Categoria '{nome_cat}' registrada.")

        with tab2:
            st.subheader("Centros de Custos")
            novo_cc = st.text_input("Nome do Centro de Custo")
            if st.button("Salvar Centro de Custo"):
                st.success(f"Centro '{novo_cc}' registrado.")

        with tab3:
            st.subheader("Gestão de Contas e Bancos")
            st.write("Contas Ativas:")
            st.bullet_list(["Sicredi (Principal)", "Caixa Econômica", "Caixinha Interno"])
