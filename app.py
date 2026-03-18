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

# Cabeçalho real da sua aba Lancamentos
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
# Suporta a estrutura hierárquica por pontos (ex: 3.01.01.001)
CABECALHO_CATEGORIAS = ["Codigo", "Nome_Categoria", "Tipo", "Permite_Lancamento"]
CABECALHO_CENTROS = ["ID", "Nome_Centro"]

# =========================================================
# FUNÇÕES DE FORMATAÇÃO E ESTRUTURA HIERÁRQUICA
# =========================================================
def formatar_moeda_br(valor):
    """Formata float para string padrão brasileiro R$ 00.000,00"""
    try:
        total_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return total_fmt
    except:
        return "R$ 0,00"

def identificar_nivel(codigo):
    """
    Identifica o nível contábil pela quantidade de blocos no código:
    3             -> Nível 1
    3.01          -> Nível 2
    3.01.01       -> Nível 3
    3.01.01.001   -> Nível 4 (Analítico)
    """
    cod_str = str(codigo).strip()
    if not cod_str or cod_str == "None" or cod_str == "nan":
        return 0
    return len(cod_str.split('.'))

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
    """Corrige headers problemáticos e inconsistências no arquivo OFX."""
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
    """Extrai conteúdo de uma tag OFX de forma tolerante."""
    padrao = rf"<{tag}>(.*?)(?:</{tag}>|\n|$)"
    m = re.search(padrao, bloco, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    valor = m.group(1).strip()
    return html.unescape(valor)


def formatar_data_ofx(dt_raw):
    """Converte datas OFX bancárias para o formato DD/MM/YYYY."""
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
    """Converte strings financeiras variadas para float puro."""
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
    """Lógica completa de processamento do arquivo OFX bancário."""
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
    """Retorna a worksheet da aba, criando-a se necessário."""
    try:
        return sh.worksheet(nome_aba)
    except Exception:
        ws = sh.add_worksheet(title=nome_aba, rows=5000, cols=20)
        ws.append_row(cabecalho)
        return ws

def carregar_dados_aba(sh, nome_aba, cabecalho):
    """Lê todos os registros de uma aba específica."""
    ws = obter_aba(sh, nome_aba, cabecalho)
    registros = ws.get_all_records()
    if not registros:
        return pd.DataFrame(columns=cabecalho)
    return pd.DataFrame(registros)

def gravar_transacoes_na_planilha(df_import):
    """Grava as transações importadas evitando duplicidade."""
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

        if not df_planilha.empty:
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
        try:
            sh = gc.open_by_key(ID_DA_PLANILHA)
            
            # Carregamento em tempo real dos cadastros
            df_contas = carregar_dados_aba(sh, NOME_ABA_CONTAS, CABECALHO_CONTAS)
            df_categorias = carregar_dados_aba(sh, NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS)
            df_centros = carregar_dados_aba(sh, NOME_ABA_CENTROS, CABECALHO_CENTROS)
            df_lancamentos = carregar_dados_aba(sh, NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

            # Forçar Codigo para String para evitar erros de ordenação (TypeError)
            if not df_categorias.empty and "Codigo" in df_categorias.columns:
                df_categorias["Codigo"] = df_categorias["Codigo"].astype(str)

            # FILTRO: Apenas categorias analíticas que permitem lançamento
            if not df_categorias.empty and "Permite_Lancamento" in df_categorias.columns:
                df_categorias_analiticas = df_categorias[df_categorias["Permite_Lancamento"].astype(str).str.upper() == "SIM"].copy()
            else:
                df_categorias_analiticas = df_categorias.copy()

            st.sidebar.title("Navegação")
            menu = st.sidebar.radio(
                "Ir para:",
                ["Resumo", "Relatório Mensal", "Importar Extrato", "Conciliação Bancária", "Cadastros"]
            )

            # ---------------------------------------------------------
            # MENU: IMPORTAR EXTRATO
            # ---------------------------------------------------------
            if menu == "Importar Extrato":
                st.title("📥 Importação de Extratos (.OFX)")
                uploaded_file = st.file_uploader("Upload do arquivo bancário", type=["ofx"])

                if uploaded_file:
                    df_import = processar_ofx(uploaded_file)

                    if not df_import.empty:
                        st.subheader("Transações Detectadas")
                        
                        conta_sel = st.selectbox(
                            "Vincular à Conta Bancária:", 
                            df_contas["Nome_Conta"].tolist() if not df_contas.empty and "Nome_Conta" in df_contas.columns else ["Nenhuma conta cadastrada"]
                        )
                        
                        df_import["Conta_ID"] = conta_sel

                        col_exib = ["Data", "Descricao", "Valor", "Tipo"]
                        st.dataframe(df_import[col_exib], use_container_width=True)

                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("Total de Lançamentos", len(df_import))
                        with c2:
                            total_import = df_import["Valor"].sum()
                            st.metric("Soma do Extrato", formatar_moeda_br(total_import))

                        if st.button("🚀 Confirmar Gravação"):
                            if conta_sel == "Nenhuma conta cadastrada":
                                st.error("Cadastre uma conta antes de importar.")
                            else:
                                gravar_transacoes_na_planilha(df_import)
                                st.rerun()

            # ---------------------------------------------------------
            # MENU: CONCILIAÇÃO BANCÁRIA
            # ---------------------------------------------------------
            elif menu == "Conciliação Bancária":
                st.title("🤝 Conciliação de Pendências")
                st.info("Apenas categorias marcadas como 'Analíticas' (Permite Lançamento: SIM) são exibidas.")

                if not df_lancamentos.empty:
                    mask = (df_lancamentos["Categoria_ID"] == "") | (df_lancamentos["Centro_Custo_ID"] == "")
                    df_pendente = df_lancamentos[mask].copy()

                    if df_pendente.empty:
                        st.success("🎉 Não existem lançamentos pendentes!")
                    else:
                        st.write(f"Pendentes: {len(df_pendente)}")
                        
                        # USANDO APENAS AS CATEGORIAS ANALÍTICAS NO SELETOR
                        l_cats = [""] + df_categorias_analiticas["Nome_Categoria"].tolist() if not df_categorias_analiticas.empty and "Nome_Categoria" in df_categorias_analiticas.columns else [""]
                        
                        # CORREÇÃO PARA KeyError: 'Nome_Centro'
                        if not df_centros.empty and "Nome_Centro" in df_centros.columns:
                            l_cens = [""] + df_centros["Nome_Centro"].tolist()
                        else:
                            l_cens = [""]

                        with st.form("form_concilia"):
                            atualizados = []
                            for idx, row in df_pendente.iterrows():
                                cols = st.columns([1, 2.5, 1, 1.5, 1.5])
                                cols[0].text(row["Data"])
                                cols[1].text(row["Descricao"])
                                cols[2].text(formatar_moeda_br(row["Valor"]))
                                
                                sel_cat = cols[3].selectbox(f"Categoria", l_cats, key=f"cat_{idx}")
                                sel_cen = cols[4].selectbox(f"Centro Custo", l_cens, key=f"cen_{idx}")
                                
                                if sel_cat != "" or sel_cen != "":
                                    atualizados.append({
                                        "linha": idx + 2,
                                        "categoria": sel_cat if sel_cat != "" else row["Categoria_ID"],
                                        "centro": sel_cen if sel_cen != "" else row["Centro_Custo_ID"]
                                    })
                                st.divider()

                            if st.form_submit_button("💾 Salvar Conciliações"):
                                ws_lanc = obter_aba(sh, NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)
                                for acao in atualizados:
                                    ws_lanc.update_cell(acao["linha"], 4, acao["categoria"])
                                    ws_lanc.update_cell(acao["linha"], 5, acao["centro"])
                                st.success("Conciliação salva com sucesso!")
                                st.rerun()

            # ---------------------------------------------------------
            # MENU: RESUMO
            # ---------------------------------------------------------
            elif menu == "Resumo":
                st.title("📊 Resumo Financeiro")
                if not df_contas.empty and "Nome_Conta" in df_contas.columns:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("Saldos por Conta")
                        saldos_lista = []
                        for _, row in df_contas.iterrows():
                            conta_nome = row["Nome_Conta"]
                            saldo_inicial = para_float(row["Saldo_Inicial"])
                            movimentacao = para_float(df_lancamentos[df_lancamentos["Conta_ID"] == conta_nome]["Valor"].sum())
                            saldos_lista.append({"Conta": conta_nome, "Saldo Atual": saldo_inicial + movimentacao})
                        
                        df_resumo_saldos = pd.DataFrame(saldos_lista)
                        st.table(df_resumo_saldos.assign(Saldo_Atual=df_resumo_saldos["Saldo Atual"].apply(formatar_moeda_br))[["Conta", "Saldo_Atual"]])
                    
                    with c2:
                        total_patrimonio = sum([x["Saldo Atual"] for x in saldos_lista])
                        st.metric("Patrimônio Líquido", formatar_moeda_br(total_patrimonio))
                else:
                    st.warning("Cadastre suas contas bancárias para ver os saldos.")

            # ---------------------------------------------------------
            # MENU: RELATÓRIO MENSAL (DRE HIERÁRQUICO)
            # ---------------------------------------------------------
            elif menu == "Relatório Mensal":
                st.title("📊 Realizado Mensal (Estrutura Hierárquica)")
                if not df_lancamentos.empty and not df_categorias.empty:
                    df_lancamentos["Mes_Ano"] = pd.to_datetime(df_lancamentos["Data"], dayfirst=True).dt.strftime('%m/%Y')
                    df_lancamentos["Valor"] = df_lancamentos["Valor"].astype(float)
                    
                    map_codigos = dict(zip(df_categorias["Nome_Categoria"], df_categorias["Codigo"]))
                    df_lancamentos["Codigo"] = df_lancamentos["Categoria_ID"].map(map_codigos).astype(str)
                    
                    df_pivot_ana = df_lancamentos.pivot_table(
                        index="Codigo", columns="Mes_Ano", values="Valor", aggfunc="sum", fill_value=0
                    )
                    
                    colunas_meses = sorted(df_pivot_ana.columns.tolist())
                    relatorio_final = []
                    
                    # Ordenação garantida como string
                    df_cats_ord = df_categorias.sort_values(by="Codigo")
                    
                    for _, cat in df_cats_ord.iterrows():
                        codigo_pai = str(cat["Codigo"])
                        nome_cat = cat["Nome_Categoria"]
                        nivel = identificar_nivel(codigo_pai)
                        
                        linha_dre = {"Código": codigo_pai, "Descrição": ("  " * (nivel - 1)) + nome_cat}
                        
                        for mes in colunas_meses:
                            # Filtra no pivot todos os códigos que iniciam com o código da categoria atual
                            mask = df_pivot_ana.index.astype(str).str.startswith(codigo_pai)
                            valor_total = df_pivot_ana[mask][mes].sum()
                            linha_dre[mes] = valor_total
                        
                        relatorio_final.append(linha_dre)
                    
                    df_dre = pd.DataFrame(relatorio_final)
                    st.dataframe(df_dre.style.format({m: formatar_moeda_br for m in colunas_meses}), use_container_width=True)
                else:
                    st.info("Dados insuficientes para gerar o DRE.")

            # ---------------------------------------------------------
            # MENU: CADASTROS
            # ---------------------------------------------------------
            elif menu == "Cadastros":
                st.title("⚙️ Gestão de Cadastros")
                tab1, tab2, tab3 = st.tabs(["Contas Bancárias", "Plano de Contas", "Centros de Custo"])
                
                with tab1:
                    st.subheader("Nova Conta")
                    with st.form("form_add_conta"):
                        f_n = st.text_input("Nome da Conta")
                        f_b = st.text_input("Banco")
                        f_s = st.number_input("Saldo Inicial", format="%.2f")
                        if st.form_submit_button("Salvar Conta"):
                            obter_aba(sh, NOME_ABA_CONTAS, CABECALHO_CONTAS).append_row([len(df_contas)+1, f_n, f_b, f_s])
                            st.success("Conta salva!")
                            st.rerun()
                    st.dataframe(df_contas)

                with tab2:
                    st.subheader("Estrutura de Categorias")
                    st.write("Hierarquia por pontos: 3 (Nível 1) -> 3.01 (Nível 2) -> 3.01.01 (Nível 3) -> 3.01.01.001 (Analítico)")
                    with st.form("form_add_cat"):
                        f_c = st.text_input("Código (ex: 3.01.01.001)")
                        f_n = st.text_input("Nome da Categoria")
                        f_t = st.selectbox("Tipo", ["Receita", "Despesa"])
                        # Checkbox para definir se aceita lançamentos direto
                        permite = st.checkbox("Esta categoria aceita lançamentos diretos? (Analítica)", value=True)
                        
                        if st.form_submit_button("Salvar Categoria"):
                            txt_permite = "SIM" if permite else "NÃO"
                            obter_aba(sh, NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS).append_row([str(f_c), f_n, f_t, txt_permite])
                            st.success("Categoria salva!")
                            st.rerun()
                    
                    if not df_categorias.empty and "Codigo" in df_categorias.columns:
                        df_categorias["Codigo"] = df_categorias["Codigo"].astype(str)
                        st.dataframe(df_categorias.sort_values(by="Codigo"))
                    else:
                        st.error("A coluna 'Codigo' não foi encontrada ou está vazia.")

                with tab3:
                    st.subheader("Novos Centros de Custo")
                    with st.form("form_add_cen"):
                        f_n = st.text_input("Nome")
                        if st.form_submit_button("Salvar"):
                            obter_aba(sh, NOME_ABA_CENTROS, CABECALHO_CENTROS).append_row([len(df_centros)+1, f_n])
                            st.success("Centro salvo!")
                            st.rerun()
                    st.dataframe(df_centros)

        except gspread.exceptions.APIError as e:
            st.error("❌ Erro de Autenticação/Permissão com o Google Sheets.")
            st.info("Certifique-se de que a planilha está compartilhada com o e-mail da sua Service Account.")
            st.write(f"Detalhes técnicos: {e}")
