import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re
import html
import numpy as np # Adicionado para cálculo de média
from io import BytesIO

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

# Cabeçalho real da sua aba Lancamentos - ADICIONADO STATUS
CABECALHO_LANCAMENTOS = [
    "Data",
    "Descricao",
    "Valor",
    "Categoria_ID",
    "Centro_Custo_ID",
    "Conta_ID",
    "Documento_ID",
    "Status"
]

CABECALHO_CONTAS = ["ID", "Nome_Conta", "Banco", "Saldo_Inicial"]
# Suporta a estrutura hierárquica por pontos (ex: 3.01.01.001) e coluna Nível
CABECALHO_CATEGORIAS = ["Codigo", "Nome_Categoria", "Tipo", "Permite_Lancamento", "Nivel"]
# AJUSTADO PARA O PADRÃO DA SUA PLANILHA (image_7b4dbe.png)
CABECALHO_CENTROS = ["ID", "Centros_Custos"]

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

# =========================================================
# GOOGLE SHEETS COM SUPORTE A CACHE (USO EM MEMÓRIA)
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

@st.cache_data(ttl=600)  # Mantém os dados em memória por 10 minutos
def carregar_dados_cache(nome_aba, cabecalho):
    """
    Lê todos os registros de uma aba específica e armazena em cache.
    Resolve o erro 429 de Quota Exceeded e agiliza a navegação.
    """
    gc = conectar_planilha()
    if not gc:
        return pd.DataFrame(columns=cabecalho)
    
    try:
        sh = gc.open_by_key(ID_DA_PLANILHA)
        try:
            ws = sh.worksheet(nome_aba)
        except Exception:
            # Tenta criar a aba com o cabeçalho correto se ela não existir
            st.warning(f"Aba {nome_aba} não encontrada. Criando com cabeçalho padrão.")
            ws = sh.add_worksheet(title=nome_aba, rows=5000, cols=20)
            ws.append_row(cabecalho)
        
        # get_all_values evita interpretações automáticas erradas de tipos numéricos
        dados = ws.get_all_values()
        if len(dados) <= 1:
            return pd.DataFrame(columns=cabecalho)
        
        df = pd.DataFrame(dados[1:], columns=dados[0])
        
        # Saneamento preventivo nas colunas de Valor
        if "Valor" in df.columns:
            df["Valor"] = df["Valor"].apply(para_float)
        if "Saldo_Inicial" in df.columns:
            df["Saldo_Inicial"] = df["Saldo_Inicial"].apply(para_float)
            
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados da aba {nome_aba}: {e}")
        return pd.DataFrame(columns=cabecalho)

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
    if valor is None or valor == "":
        return 0.0

    if isinstance(valor, str):
        s = valor.strip().replace("R$", "").replace(" ", "")
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except:
            return 0.0
    
    try:
        return float(valor)
    except:
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
                "Tipo": str(trntype).strip(),
                "Status": "PENDENTE"
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
# PLANILHA - OPERAÇÕES DE GRAVAÇÃO (SEM CACHE)
# =========================================================
def gravar_transacoes_na_planilha(df_import):
    """Grava as transações importadas evitando duplicidade."""
    gc = conectar_planilha()
    if not gc:
        return

    try:
        sh = gc.open_by_key(ID_DA_PLANILHA)
        ws = sh.worksheet(NOME_ABA_LANCAMENTOS)

        df_planilha = carregar_dados_cache(NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

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
        
        st.cache_data.clear()
        st.success(f"Sucesso. {len(novos)} lançamentos gravados.")

    except Exception as e:
        st.error(f"Erro ao gravar na planilha: {e}")


# =========================================================
# INTERFACE
# =========================================================
if check_password():
    df_contas = carregar_dados_cache(NOME_ABA_CONTAS, CABECALHO_CONTAS)
    df_categorias = carregar_dados_cache(NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS)
    df_centros = carregar_dados_cache(NOME_ABA_CENTROS, CABECALHO_CENTROS)
    df_lancamentos = carregar_dados_cache(NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

    COL_NOME_CEN = "Centros_Custos" if "Centros_Custos" in df_centros.columns else "Nome_Centro"
    l_cens_seletor = df_centros[COL_NOME_CEN].tolist() if not df_centros.empty and COL_NOME_CEN in df_centros.columns else []

    if not df_categorias.empty and "Codigo" in df_categorias.columns:
        df_categorias["Codigo"] = df_categorias["Codigo"].astype(str)

    if not df_categorias.empty and "Permite_Lancamento" in df_categorias.columns:
        df_categorias_analiticas = df_categorias[df_categorias["Permite_Lancamento"].astype(str).str.upper() == "SIM"].copy()
    else:
        df_categorias_analiticas = df_categorias.copy()

    st.sidebar.title("Navegação")
    if st.sidebar.button("🔄 Sincronizar Planilha"):
        st.cache_data.clear()
        st.rerun()

    menu = st.sidebar.radio(
        "Ir para:",
        ["Resumo", "Relatório Mensal", "Importar Extrato", "Conciliação Bancária", "Lançamentos Conciliados", "Cadastros"]
    )

    # ---------------------------------------------------------
    # MENU: RELATÓRIO MENSAL (SEM FILTRO DE NÍVEL)
    # ---------------------------------------------------------
    if menu == "Relatório Mensal":
        st.title("📊 Realizado Mensal (Estrutura Hierárquica)")
        
        if not df_lancamentos.empty and not df_categorias.empty:
            
            # --- FILTROS NO TOPO ---
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                centro_filtro = st.selectbox("Filtrar por Centro de Custo:", ["Todos"] + l_cens_seletor)
            
            with col_f2:
                ocultar_zerados = st.checkbox("Ocultar lançamentos zerados", value=False)
            
            # Filtros Base: Ignorar transferências
            df_dre_input = df_lancamentos[df_lancamentos["Categoria_ID"] != "TRANSFERÊNCIA"].copy()
            
            if centro_filtro != "Todos":
                df_dre_input = df_dre_input[df_dre_input["Centro_Custo_ID"] == centro_filtro]
            
            if df_dre_input.empty:
                st.warning("Nenhum lançamento encontrado para os filtros selecionados.")
                st.stop()
            
            # Adiciona colunas de mês/ano e código para pivoteamento
            df_dre_input["Mes_Ano"] = pd.to_datetime(df_dre_input["Data"], dayfirst=True).dt.strftime('%m/%Y')
            map_codigos = dict(zip(df_categorias["Nome_Categoria"], df_categorias["Codigo"]))
            df_dre_input["Codigo"] = df_dre_input["Categoria_ID"].map(map_codigos).astype(str)
            
            # Cria a tabela dinâmica (pivot table)
            df_pivot_ana = df_dre_input.pivot_table(
                index="Codigo", columns="Mes_Ano", values="Valor", aggfunc="sum", fill_value=0
            )
            
            colunas_meses = sorted(df_pivot_ana.columns.tolist())
            relatorio_final = []
            
            # Garante que a coluna Nivel existe e é numérica
            df_categorias["Nivel"] = pd.to_numeric(df_categorias["Nivel"], errors='coerce').fillna(4).astype(int)
            df_cats_ord = df_categorias.sort_values(by="Codigo")
            
            for _, cat in df_cats_ord.iterrows():
                codigo_pai = str(cat["Codigo"])
                nome_cat = cat["Nome_Categoria"]
                nivel = int(cat["Nivel"])
                
                # Formatação da descrição com base no nível (indentação)
                prefixo = "  " * (nivel - 1)
                linha_dre = {"Nível": nivel, "Código": codigo_pai, "Descrição": prefixo + nome_cat}
                
                valores_linha = []
                for mes in colunas_meses:
                    mask = df_pivot_ana.index.astype(str).str.startswith(codigo_pai)
                    valor_total = df_pivot_ana[mask][mes].sum()
                    linha_dre[mes] = valor_total
                    valores_linha.append(valor_total)
                
                total_linha = sum(valores_linha)
                
                if ocultar_zerados and total_linha == 0:
                    continue
                
                linha_dre["Total Acumulado"] = total_linha
                valores_positivos = [v for v in valores_linha if v != 0]
                media_linha = sum(valores_positivos) / len(valores_positivos) if valores_positivos else 0
                linha_dre["Média Mensal"] = media_linha
                
                relatorio_final.append(linha_dre)
            
            df_dre = pd.DataFrame(relatorio_final)
            
            if df_dre.empty:
                st.warning("Nenhum dado a exibir.")
                st.stop()

            # Exportação
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_dre.to_excel(writer, index=False, sheet_name='Relatorio_Mensal')
            st.download_button(label="📥 Exportar para Excel", data=output.getvalue(), file_name="relatorio_mensal.xlsx", mime="application/vnd.ms-excel")

            colunas_formato = colunas_meses + ["Total Acumulado", "Média Mensal"]
            
            def aplicar_cores(row):
                n = row["Nível"]
                if n == 1: return ['background-color: #002060; color: white; font-weight: bold'] * len(row)
                if n == 2: return ['background-color: #BDD7EE; color: black; font-weight: bold'] * len(row)
                if n == 3: return ['background-color: #D9D9D9; color: black; font-weight: bold'] * len(row)
                return ['background-color: white; color: black'] * len(row)

            st.dataframe(
                df_dre.style.apply(aplicar_cores, axis=1).format({m: formatar_moeda_br for m in colunas_formato}), 
                use_container_width=True, 
                height=600
            )
        else:
            st.info("Dados insuficientes para gerar o DRE.")

    # ---------------------------------------------------------
    # DEMAIS MENUS (MANTIDOS ORIGINAIS)
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
                    saldo_inicial = row["Saldo_Inicial"] 
                    movimentacao = df_lancamentos[df_lancamentos["Conta_ID"] == conta_nome]["Valor"].sum()
                    saldos_lista.append({"Conta": conta_nome, "Saldo Atual": saldo_inicial + movimentacao})
                
                df_resumo_saldos = pd.DataFrame(saldos_lista)
                st.table(df_resumo_saldos.assign(Saldo_Atual=df_resumo_saldos["Saldo Atual"].apply(formatar_moeda_br))[["Conta", "Saldo_Atual"]])
            
            with c2:
                total_patrimonio = sum([x["Saldo Atual"] for x in saldos_lista])
                st.metric("Patrimônio Líquido", formatar_moeda_br(total_patrimonio))
        else:
            st.warning("Cadastre suas contas bancárias para ver os saldos.")

    elif menu == "Importar Extrato":
        st.title("📥 Importação de Extratos (.OFX)")
        uploaded_file = st.file_uploader("Upload do arquivo bancário", type=["ofx"])
        if uploaded_file:
            df_import = processar_ofx(uploaded_file)
            if not df_import.empty:
                st.subheader("Transações Detectadas")
                conta_sel = st.selectbox(
                    "Vincular à Conta Bancária:", 
                    df_contas["Nome_Conta"].tolist() if not df_contas.empty else ["Nenhuma conta cadastrada"]
                )
                df_import["Conta_ID"] = conta_sel
                st.dataframe(df_import[["Data", "Descricao", "Valor", "Tipo"]], use_container_width=True)
                if st.button("🚀 Confirmar Gravação"):
                    if conta_sel != "Nenhuma conta cadastrada":
                        gravar_transacoes_na_planilha(df_import)
                        st.rerun()

    elif menu == "Conciliação Bancária":
        st.title("🤝 Conciliação de Pendências")
        if not df_lancamentos.empty:
            mask = (df_lancamentos["Status"].astype(str).str.upper() != "CONCILIADO")
            df_pendente = df_lancamentos[mask].copy()
            if df_pendente.empty:
                st.success("🎉 Não existem lançamentos pendentes!")
            else:
                l_cats = ["", "TRANSFERÊNCIA"] + df_categorias_analiticas["Nome_Categoria"].tolist()
                l_contas = df_contas["Nome_Conta"].tolist()
                l_cens = [""] + l_cens_seletor
                for idx, row in df_pendente.iterrows():
                    with st.container():
                        c = st.columns([1, 2, 1, 1.5, 1.5, 0.8])
                        c[0].text(row["Data"])
                        c[1].text(row["Descricao"])
                        c[2].text(formatar_moeda_br(row["Valor"]))
                        sel_cat = c[3].selectbox(f"Categoria", l_cats, key=f"cat_p_{idx}")
                        if sel_cat == "TRANSFERÊNCIA":
                            sel_cen = c[4].selectbox(f"Conta Destino", l_contas, key=f"cen_p_{idx}")
                        else:
                            sel_cen = c[4].selectbox(f"Centro Custo", l_cens, key=f"cen_p_{idx}")
                        if c[5].button("✅ Confirmar", key=f"btn_p_{idx}"):
                            if sel_cat != "" and sel_cen != "":
                                gc = conectar_planilha()
                                ws_l = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_LANCAMENTOS)
                                ws_l.update_cell(idx + 2, 4, sel_cat)
                                ws_l.update_cell(idx + 2, 5, sel_cen)
                                ws_l.update_cell(idx + 2, 8, "CONCILIADO")
                                st.cache_data.clear()
                                st.rerun()
                        st.divider()

    elif menu == "Lançamentos Conciliados":
        st.title("✅ Lançamentos Conciliados")
        if not df_lancamentos.empty:
            mask_conciliado = (df_lancamentos["Status"].astype(str).str.upper() == "CONCILIADO")
            df_conciliado = df_lancamentos[mask_conciliado].copy()
            if not df_conciliado.empty:
                l_cats = ["", "TRANSFERÊNCIA"] + df_categorias_analiticas["Nome_Categoria"].tolist()
                l_contas = df_contas["Nome_Conta"].tolist()
                l_cens = [""] + l_cens_seletor
                for idx, row in df_conciliado.iterrows():
                    with st.container():
                        c = st.columns([1, 2, 1, 1.5, 1.5, 0.8])
                        c[0].text(row["Data"])
                        c[1].text(row["Descricao"])
                        c[2].text(formatar_moeda_br(row["Valor"]))
                        idx_cat = l_cats.index(row["Categoria_ID"]) if row["Categoria_ID"] in l_cats else 0
                        sel_cat = c[3].selectbox(f"Categoria", l_cats, index=idx_cat, key=f"cat_c_{idx}")
                        if c[5].button("💾 Salvar", key=f"btn_c_{idx}"):
                            gc = conectar_planilha()
                            ws_l = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_LANCAMENTOS)
                            ws_l.update_cell(idx + 2, 4, sel_cat)
                            st.cache_data.clear()
                            st.rerun()
                        st.divider()

    elif menu == "Cadastros":
        st.title("⚙️ Gestão de Cadastros")
        tab1, tab2, tab3 = st.tabs(["Contas Bancárias", "Plano de Contas", "Centros de Custo"])
        with tab1:
            with st.form("form_add_conta"):
                f_n = st.text_input("Nome da Conta")
                f_b = st.text_input("Banco")
                f_s = st.number_input("Saldo Inicial", format="%.2f")
                if st.form_submit_button("Salvar Conta"):
                    gc = conectar_planilha()
                    ws_c = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_CONTAS)
                    ws_c.append_row([len(df_contas)+1, f_n, f_b, f_s])
                    st.cache_data.clear()
                    st.rerun()
            st.dataframe(df_contas)
        with tab2:
            with st.form("form_add_cat"):
                f_c = st.text_input("Código")
                f_n = st.text_input("Nome")
                f_t = st.selectbox("Tipo", ["Receita", "Despesa"])
                perm = st.checkbox("Analítica?", value=True)
                niv = st.number_input("Nível", 1, 4, 4)
                if st.form_submit_button("Salvar"):
                    gc = conectar_planilha()
                    ws_cat = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_CATEGORIAS)
                    ws_cat.append_row([str(f_c), f_n, f_t, "SIM" if perm else "NÃO", niv])
                    st.cache_data.clear()
                    st.rerun()
            st.dataframe(df_categorias.sort_values(by="Codigo"))
        with tab3:
            with st.form("form_add_cen"):
                f_n = st.text_input("Nome")
                if st.form_submit_button("Salvar"):
                    gc = conectar_planilha()
                    ws_cen = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_CENTROS)
                    ws_cen.append_row([len(df_centros)+1, f_n])
                    st.cache_data.clear()
                    st.rerun()
            st.dataframe(df_centros)
