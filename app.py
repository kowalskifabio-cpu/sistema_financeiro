import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re
import html

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(page_title="Labor Business Pro", layout="wide")

# =========================================================
# CONFIGURAÇÕES GERAIS
# =========================================================
ID_DA_PLANILHA = "1FLCbuzrg1UL1yatdIas6aDBBjhc__mebdhUYxIt0NQk"
NOME_ABA_LANCAMENTOS = "Lancamentos"
NOME_ABA_CONTAS = "Contas"
NOME_ABA_CATEGORIAS = "Categorias"
NOME_ABA_CENTROS = "Centros_Custo"

# Cabeçalhos reais das abas
CABECALHO_LANCAMENTOS = [
    "Data",
    "Descricao",
    "Valor",
    "Categoria_ID",
    "Centro_Custo_ID",
    "Conta_ID",
    "Documento_ID"
]

CABECALHO_CONTAS = ["ID", "Nome_Conta", "Banco", "Saldo_Inicial"]
CABECALHO_CATEGORIAS = ["ID", "Nome_Categoria", "Tipo"]
CABECALHO_CENTROS = ["ID", "Nome_Centro"]

# =========================================================
# GOOGLE SHEETS
# =========================================================
def conectar_planilha():
    """Conecta ao Google Sheets usando st.secrets."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Bloco [gcp_service_account] não encontrado nos Secrets.")
            return None

        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client

    except Exception as e:
        st.error(f"Erro na conexão com Google Sheets: {type(e).__name__}: {e}")
        return None

# =========================================================
# LOGIN
# =========================================================
def obter_credenciais_login():
    try:
        username = st.secrets["auth"]["username"]
        password = st.secrets["auth"]["password"]
        return username, password
    except Exception:
        st.error(
            "Credenciais de autenticação não encontradas nos Secrets. "
            "Crie o bloco [auth] com username e password."
        )
        return None, None


def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔐 Sistema Labor Business")
    user = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")

    username_correto, password_correta = obter_credenciais_login()

    if st.button("Entrar"):
        if not username_correto or not password_correta:
            st.stop()

        if user == username_correto and password == password_correta:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")

    return False


# =========================================================
# OFX - PARSER TOLERANTE
# =========================================================
def decodificar_ofx_bytes(conteudo_bytes):
    """Tenta decodificar com múltiplos encodings comuns de OFX bancário."""
    for enc in ["cp1252", "latin-1", "utf-8"]:
        try:
            return conteudo_bytes.decode(enc)
        except Exception:
            continue
    raise ValueError("Não foi possível decodificar o arquivo OFX.")


def limpar_header_ofx(texto_ofx):
    """
    Corrige headers problemáticos como:
    ENCODING: UTF - 8 -> ENCODING:UTF-8
    """
    linhas = texto_ofx.splitlines()
    linhas_limpas = []

    for linha in linhas:
        linha_strip = linha.strip()

        if ":" in linha_strip and "<" not in linha_strip:
            partes = linha_strip.split(":", 1)
            chave = partes[0].strip()
            valor = partes[1].strip().replace(" ", "")
            linhas_limpas.append(f"{chave}:{valor}")
        else:
            linhas_limpas.append(linha)

    return "\n".join(linhas_limpas)


def extrair_tag(bloco, tag):
    """
    Extrai conteúdo de uma tag OFX, tolerando ausência de fechamento em alguns casos.
    """
    padrao = rf"<{tag}>(.*?)(?:</{tag}>|\n|$)"
    m = re.search(padrao, bloco, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    valor = m.group(1).strip()
    return html.unescape(valor)


def formatar_data_ofx(dt_raw):
    """
    Converte datas OFX como 20260317071057[-3:BRT] para 17/03/2026.
    """
    if not dt_raw:
        return ""

    numeros = re.match(r"(\d{8,14})", str(dt_raw))
    if not numeros:
        return str(dt_raw)

    s = numeros.group(1)
    yyyy = s[0:4]
    mm = s[4:6]
    dd = s[6:8]
    return f"{dd}/{mm}/{yyyy}"


def para_float(valor):
    if valor is None:
        return 0.0

    valor = str(valor).strip()
    if valor == "":
        return 0.0

    valor = valor.replace(" ", "")

    try:
        return float(valor)
    except Exception:
        try:
            valor = valor.replace(".", "").replace(",", ".")
            return float(valor)
        except Exception:
            return 0.0


def processar_ofx(uploaded_file):
    """
    Parser tolerante para OFX bancário:
    - lê em bytes
    - decodifica com fallback
    - limpa header inconsistente
    - extrai blocos STMTTRN sem depender da ordem rígida das tags
    """
    try:
        uploaded_file.seek(0)
        conteudo = uploaded_file.read()

        if not conteudo:
            st.error("Arquivo OFX vazio.")
            return pd.DataFrame()

        texto_ofx = decodificar_ofx_bytes(conteudo)
        texto_ofx = limpar_header_ofx(texto_ofx)

        blocos = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", texto_ofx, re.IGNORECASE | re.DOTALL)

        if not blocos:
            st.warning("Nenhum bloco <STMTTRN> foi encontrado no OFX.")
            return pd.DataFrame()

        transacoes = []

        for bloco in blocos:
            fitid = extrair_tag(bloco, "FITID")
            trnamt = extrair_tag(bloco, "TRNAMT")
            dtposted = extrair_tag(bloco, "DTPOSTED")
            memo = extrair_tag(bloco, "MEMO")
            name = extrair_tag(bloco, "NAME")
            trntype = extrair_tag(bloco, "TRNTYPE")
            refnum = extrair_tag(bloco, "REFNUM")
            checknum = extrair_tag(bloco, "CHECKNUM")

            descricao = memo or name or trntype or ""
            documento = refnum or checknum or fitid or ""

            transacoes.append({
                "Data": formatar_data_ofx(dtposted),
                "Descricao": str(descricao).strip(),
                "Valor": para_float(trnamt),
                "Categoria_ID": "",
                "Centro_Custo_ID": "",
                "Conta_ID": "",
                "Documento_ID": str(documento).strip(),
                "FITID": str(fitid).strip(),
                "Tipo": str(trntype).strip()
            })

        df = pd.DataFrame(transacoes)

        if not df.empty:
            df = df[
                ~(
                    df["Data"].eq("") &
                    df["Descricao"].eq("") &
                    df["Valor"].eq(0.0) &
                    df["Documento_ID"].eq("")
                )
            ].copy()

        return df

    except Exception as e:
        st.error(f"Erro ao ler arquivo OFX: {type(e).__name__}: {e}")
        return pd.DataFrame()


# =========================================================
# PLANILHA - OPERAÇÕES
# =========================================================
def obter_aba(sh, nome_aba, cabecalho):
    try:
        return sh.worksheet(nome_aba)
    except Exception:
        ws = sh.add_worksheet(title=nome_aba, rows=2000, cols=20)
        ws.append_row(cabecalho)
        return ws

def carregar_dados_aba(sh, nome_aba, cabecalho):
    ws = obter_aba(sh, nome_aba, cabecalho)
    registros = ws.get_all_records()
    if not registros:
        return pd.DataFrame(columns=cabecalho)
    return pd.DataFrame(registros)

def gravar_transacoes_na_planilha(df_import):
    gc = conectar_planilha()
    if not gc:
        return

    try:
        sh = gc.open_by_key(ID_DA_PLANILHA)
        ws = obter_aba(sh, NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

        df_planilha = carregar_dados_aba(sh, NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

        if df_import.empty:
            st.warning("Não há dados para gravar.")
            return

        df_import = df_import.copy()
        df_import["FITID"] = df_import["FITID"].astype(str).str.strip()
        df_import["Documento_ID"] = df_import["Documento_ID"].astype(str).str.strip()

        if not df_planilha.empty:
            if "Documento_ID" in df_planilha.columns:
                df_planilha["Documento_ID"] = df_planilha["Documento_ID"].astype(str).str.strip()
                novos = df_import[~df_import["Documento_ID"].isin(df_planilha["Documento_ID"])]
            else:
                chave_import = df_import["Data"].astype(str) + "|" + df_import["Valor"].astype(str) + "|" + df_import["Descricao"].astype(str)
                chave_planilha = df_planilha["Data"].astype(str) + "|" + df_planilha["Valor"].astype(str) + "|" + df_planilha["Descricao"].astype(str)
                novos = df_import[~chave_import.isin(chave_planilha)]
        else:
            novos = df_import.copy()

        if novos.empty:
            st.warning("Nenhuma transação nova detectada.")
            return

        novos_para_gravar = novos[CABECALHO_LANCAMENTOS]
        ws.append_rows(novos_para_gravar.values.tolist(), value_input_option="USER_ENTERED")
        st.success(f"Sucesso. {len(novos)} lançamentos gravados.")

    except Exception as e:
        st.error(f"Erro ao gravar na planilha: {e}")


# =========================================================
# INTERFACE
# =========================================================
if check_password():
    gc = conectar_planilha()
    if gc:
        sh = gc.open_by_key(ID_DA_PLANILHA)
        
        # Carregar Cadastros de Apoio
        df_contas = carregar_dados_aba(sh, NOME_ABA_CONTAS, CABECALHO_CONTAS)
        df_categorias = carregar_dados_aba(sh, NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS)
        df_centros = carregar_dados_aba(sh, NOME_ABA_CENTROS, CABECALHO_CENTROS)
        df_lancamentos = carregar_dados_aba(sh, NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

        st.sidebar.title("Navegação")
        menu = st.sidebar.radio(
            "Ir para:",
            ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"]
        )

        if menu == "Importar Extrato":
            st.title("📥 Importação e Conciliação (.OFX)")
            uploaded_file = st.file_uploader("Upload do arquivo bancário", type=["ofx"])

            if uploaded_file:
                df_import = processar_ofx(uploaded_file)

                if not df_import.empty:
                    st.subheader("Conciliação Bancária")
                    
                    # Interface de Conciliação em massa para o arquivo
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        conta_sel = st.selectbox("Conta Bancária Origem", df_contas["Nome_Conta"].tolist() if not df_contas.empty else ["Nenhuma"])
                    with col_b:
                        cat_padrao = st.selectbox("Categoria Padrão", df_categorias["Nome_Categoria"].tolist() if not df_categorias.empty else ["Nenhuma"])
                    with col_c:
                        centro_padrao = st.selectbox("Centro de Custo Padrão", df_centros["Nome_Centro"].tolist() if not df_centros.empty else ["Nenhum"])

                    # Aplicar seleções ao dataframe de importação
                    df_import["Conta_ID"] = conta_sel
                    df_import["Categoria_ID"] = cat_padrao
                    df_import["Centro_Custo_ID"] = centro_padrao

                    st.dataframe(df_import[["Data", "Descricao", "Valor", "Tipo", "Documento_ID"]], use_container_width=True)

                    if st.button("🚀 Confirmar e Gravar na Planilha"):
                        gravar_transacoes_na_planilha(df_import)
                else:
                    st.warning("Nenhuma transação extraída.")

        elif menu == "Resumo":
            st.title("📊 Resumo Financeiro")
            if not df_contas.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Saldos Atuais")
                    # Calcular saldos dinâmicos
                    saldos_view = []
                    for _, conta in df_contas.iterrows():
                        nome = conta["Nome_Conta"]
                        inicial = para_float(conta["Saldo_Inicial"])
                        movimentacao = df_lancamentos[df_lancamentos["Conta_ID"] == nome]["Valor"].astype(float).sum()
                        saldos_view.append({"Conta": nome, "Saldo": inicial + movimentacao})
                    
                    df_saldos_final = pd.DataFrame(saldos_view)
                    st.table(df_saldos_final.style.format({"Saldo": "R$ {:,.2f}"}))
                
                with col2:
                    total_geral = sum([s["Saldo"] for s in saldos_view])
                    st.metric("Saldo Total Consolidado", f"R$ {total_geral:,.2f}")
            else:
                st.info("Cadastre uma conta bancária para ver os saldos.")

        elif menu == "Relatório Mensal":
            st.title("📊 Relatórios Realizado (DRE)")
            if not df_lancamentos.empty:
                # Criar coluna de mês/ano para o Pivot
                df_lancamentos["Mes_Ano"] = pd.to_datetime(df_lancamentos["Data"], dayfirst=True).dt.strftime('%Y-%m')
                df_lancamentos["Valor"] = df_lancamentos["Valor"].astype(float)
                
                relatorio_pivot = df_lancamentos.pivot_table(
                    index="Categoria_ID", 
                    columns="Mes_Ano", 
                    values="Valor", 
                    aggfunc="sum", 
                    fill_value=0
                )
                st.dataframe(relatorio_pivot.style.format("R$ {:,.2f}"), use_container_width=True)
            else:
                st.info("Sem dados de lançamentos para gerar o relatório.")

        elif menu == "Cadastros":
            st.title("⚙️ Gestão de Cadastros")
            tab_contas, tab_cats, tab_centros = st.tabs(["Contas Bancárias", "Plano de Contas", "Centros de Custo"])
            
            with tab_contas:
                st.subheader("Nova Conta")
                with st.form("form_contas"):
                    n_conta = st.text_input("Nome da Conta (ex: Sicredi)")
                    b_conta = st.text_input("Banco")
                    s_inicial = st.number_input("Saldo Inicial", format="%.2f")
                    if st.form_submit_button("Salvar Conta"):
                        ws_contas = obter_aba(sh, NOME_ABA_CONTAS, CABECALHO_CONTAS)
                        ws_contas.append_row([len(df_contas)+1, n_conta, b_conta, s_inicial])
                        st.success("Conta cadastrada!")
                        st.rerun()
                st.dataframe(df_contas)

            with tab_cats:
                st.subheader("Nova Categoria")
                with st.form("form_cats"):
                    n_cat = st.text_input("Nome da Categoria")
                    t_cat = st.selectbox("Tipo", ["Receita", "Despesa"])
                    if st.form_submit_button("Salvar Categoria"):
                        ws_cats = obter_aba(sh, NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS)
                        ws_cats.append_row([len(df_categorias)+1, n_cat, t_cat])
                        st.success("Categoria cadastrada!")
                        st.rerun()
                st.dataframe(df_categorias)

            with tab_centros:
                st.subheader("Novo Centro de Custo")
                with st.form("form_centros"):
                    n_centro = st.text_input("Nome do Centro de Custo")
                    if st.form_submit_button("Salvar Centro"):
                        ws_centros = obter_aba(sh, NOME_ABA_CENTROS, CABECALHO_CENTROS)
                        ws_centros.append_row([len(df_centros)+1, n_centro])
                        st.success("Centro cadastrado!")
                        st.rerun()
                st.dataframe(df_centros)
