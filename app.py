import streamlit as st
import pandas as pd

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Labor Business - Gestão Financeira", layout="wide")

# 1. SISTEMA DE LOGIN (Simples para começar)
def check_password():
    """Retorna True se o usuário inseriu a senha correta."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔐 Acesso Labor Business")
        user = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        
        if st.button("Entrar"):
            # Aqui usamos as credenciais que você solicitou
            if user == "Kowalski" and password == "Karin@1980":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")
        return False
    return True

if check_password():
    # --- INTERFACE DO DASHBOARD ---
    st.sidebar.title("Labor Business")
    st.sidebar.write(f"Bem-vindo, Kowalski")
    
    # Botão de Logout
    if st.sidebar.button("Sair"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.title("📊 Resumo de Gestão de Caixa")
    
    # 2. SIMULAÇÃO DE DADOS (Depois conectaremos com seu Google Sheets)
    # Criei esses dados para você ver o visual agora mesmo
    df_saldos = pd.DataFrame({
        'Conta': ['Sicredi', 'Caixa Federal', 'Caixinha'],
        'Saldo': [113901.84, 67900.49, 4174.42]
    })
    
    total_geral = df_saldos['Saldo'].sum()

    # 3. LINHA SUPERIOR: SALDO TOTAL
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader(f"Saldo Total: R$ {total_geral:,.2f}")
        st.table(df_saldos)

    with col2:
        st.subheader("📈 Fluxo de Caixa")
        # Criando um gráfico de linha fictício similar ao do Nibo
        chart_data = pd.DataFrame({
            'Data': pd.date_range(start='2026-02-01', periods=10, freq='D'),
            'Saldo': [150000, 155000, 152000, 160000, 185000, 182000, 185976, 185976, 185976, 185976]
        })
        st.line_chart(chart_data.set_index('Data'))

    st.divider()

    # 4. ÁREA DE RECEBIMENTOS E PAGAMENTOS
    rec, pag = st.columns(2)
    
    with rec:
        st.success("### ↑ Recebimentos")
        st.info("Nenhum lançamento pendente") # Aqui entrará o filtro da planilha

    with pag:
        st.error("### ↓ Pagamentos")
        st.info("Nenhum lançamento pendente")

    # 5. REPLICABILIDADE (Dica para sua PF)
    st.sidebar.divider()
    st.sidebar.info("💡 Para usar na Pessoa Física, basta trocar a planilha de origem no código.")
