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

        # corrige apenas linhas do header OFX clássico
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
            documento = refnum or checknum or ""

            transacoes.append({
                "Data": formatar_data_ofx(dtposted),
                "Valor": para_float(trnamt),
                "FITID": str(fitid).strip(),
                "Descrição": str(descricao).strip(),
                "Tipo": str(trntype).strip(),
                "Documento": str(documento).strip()
            })

        df = pd.DataFrame(transacoes)

        if not df.empty:
            df = df[
                ~(
                    df["Data"].eq("") &
                    df["FITID"].eq("") &
                    df["Descrição"].eq("") &
                    df["Valor"].eq(0.0)
                )
            ].copy()

        return df

    except Exception as e:
        st.error(f"Erro ao ler arquivo OFX: {type(e).__name__}: {e}")
        return pd.DataFrame()


# =========================================================
# PLANILHA
# =========================================================
def garantir_cabecalho_planilha(ws):
    cabecalho_esperado = ["Data", "Valor", "FITID", "Descrição", "Tipo", "Documento"]

    try:
        valores = ws.get_all_values()

        if not valores:
            ws.append_row(cabecalho_esperado)
            return cabecalho_esperado

        primeira_linha = valores[0]
        if primeira_linha != cabecalho_esperado:
            st.warning(
                "A primeira linha da planilha está diferente do esperado. "
                f"Esperado: {cabecalho_esperado} | Encontrado: {primeira_linha}"
            )
        return primeira_linha

    except Exception as e:
        st.error(f"Erro ao validar cabeçalho da planilha: {type(e).__name__}: {e}")
        return None


def carregar_dados_planilha(ws):
    try:
        registros = ws.get_all_records()
        if not registros:
            return pd.DataFrame(columns=["Data", "Valor", "FITID", "Descrição", "Tipo", "Documento"])
        return pd.DataFrame(registros)
    except Exception as e:
        st.error(f"Erro ao carregar dados da planilha: {type(e).__name__}: {e}")
        return pd.DataFrame()


def gravar_transacoes_na_planilha(df_import):
    gc = conectar_planilha()
    if not gc:
        return

    try:
        sh = gc.open_by_key(ID_DA_PLANILHA)
        ws = sh.get_worksheet(0)

        garantir_cabecalho_planilha(ws)
        df_planilha = carregar_dados_planilha(ws)

        if df_import.empty:
            st.warning("Não há dados para gravar.")
            return

        colunas_necessarias = ["Data", "Valor", "FITID", "Descrição", "Tipo", "Documento"]
        colunas_faltantes = [c for c in colunas_necessarias if c not in df_import.columns]

        if colunas_faltantes:
            st.error(f"Colunas faltantes no arquivo importado: {colunas_faltantes}")
            return

        df_import = df_import.copy()
        df_import["FITID"] = df_import["FITID"].astype(str).str.strip()

        if not df_planilha.empty and "FITID" in df_planilha.columns:
            df_planilha["FITID"] = df_planilha["FITID"].astype(str).str.strip()
            novos = df_import[~df_import["FITID"].isin(df_planilha["FITID"])]
        else:
            novos = df_import.copy()

        if novos.empty:
            st.warning("Nenhuma transação nova. Todos os FITIDs já existem na planilha.")
            return

        novos = novos[["Data", "Valor", "FITID", "Descrição", "Tipo", "Documento"]]
        linhas = novos.values.tolist()

        ws.append_rows(linhas, value_input_option="USER_ENTERED")
        st.success(f"Sucesso. {len(novos)} lançamentos gravados na planilha.")

    except Exception as e:
        st.error(f"Erro ao acessar/gravar na planilha: {type(e).__name__}: {e}")


# =========================================================
# INTERFACE
# =========================================================
if check_password():
    st.sidebar.title("Navegação")
    menu = st.sidebar.radio(
        "Ir para:",
        ["Resumo", "Relatório Mensal", "Importar Extrato", "Cadastros"]
    )

    if menu == "Importar Extrato":
        st.title("📥 Importação de Extratos (.OFX)")
        uploaded_file = st.file_uploader("Upload do arquivo bancário", type=["ofx"])

        if uploaded_file:
            st.info(f"Arquivo carregado: {uploaded_file.name}")

            df_import = processar_ofx(uploaded_file)

            if not df_import.empty:
                st.subheader("Transações Detectadas")
                st.dataframe(df_import, use_container_width=True)

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Quantidade de transações", len(df_import))
                with col2:
                    try:
                        total = df_import["Valor"].sum()
                        total_fmt = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        st.metric("Soma dos valores", total_fmt)
                    except Exception:
                        pass

                if st.button("🚀 Gravar na Planilha"):
                    gravar_transacoes_na_planilha(df_import)
            else:
                st.warning("Nenhuma transação foi extraída do arquivo OFX.")

    elif menu == "Resumo":
        st.title("📊 Resumo Financeiro")
        st.write("Saldos e fluxo de caixa.")

    elif menu == "Relatório Mensal":
        st.title("📊 Relatórios DRE")
        st.write("Acompanhamento mensal de resultados.")

    elif menu == "Cadastros":
        st.title("⚙️ Configurações")
        st.write("Plano de contas e bancos.")
