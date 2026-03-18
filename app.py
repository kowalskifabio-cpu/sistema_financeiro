import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import re
import html
import numpy as np # Adicionado para cálculo de média

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

# Função descontinuada em favor da coluna 'Nivel' na planilha
# def identificar_nivel(codigo):
#     """
#     Identifica o nível contábil pela quantidade de blocos no código:
#     3            -> Nível 1
#     3.01          -> Nível 2
#     3.01.01       -> Nível 3
#     3.01.01.001   -> Nível 4 (Analítico)
#     """
#     cod_str = str(codigo).strip()
#     if not cod_str or cod_str == "None" or cod_str == "nan":
#         return 0
#     return len(cod_str.split('.'))

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
        # Retorna um DataFrame vazio com as colunas corretas para evitar erros no resto do script
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
    """
    Converte strings financeiras variadas para float puro.
    Lida com o erro onde centavos são multiplicados por 100 pela leitura incorreta.
    """
    if valor is None or valor == "":
        return 0.0

    # Se for string, limpa formatação brasileira
    if isinstance(valor, str):
        s = valor.strip().replace("R$", "").replace(" ", "")
        if "," in s:
            # Padrão brasileiro: remove ponto de milhar, troca vírgula por ponto
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except:
            return 0.0
    
    # Se já vier como número (float/int) do gspread
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

        # Para gravar, precisamos comparar com o que já existe (usando cache para rapidez)
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
        
        # LIMPANDO CACHE após gravação para que os novos dados apareçam
        st.cache_data.clear()
        st.success(f"Sucesso. {len(novos)} lançamentos gravados.")

    except Exception as e:
        st.error(f"Erro ao gravar na planilha: {e}")


# =========================================================
# INTERFACE
# =========================================================
if check_password():
    # CARREGAMENTO OTIMIZADO (Uso em memória via Cache)
    df_contas = carregar_dados_cache(NOME_ABA_CONTAS, CABECALHO_CONTAS)
    df_categorias = carregar_dados_cache(NOME_ABA_CATEGORIAS, CABECALHO_CATEGORIAS)
    df_centros = carregar_dados_cache(NOME_ABA_CENTROS, CABECALHO_CENTROS)
    df_lancamentos = carregar_dados_cache(NOME_ABA_LANCAMENTOS, CABECALHO_LANCAMENTOS)

    # Nome exato da coluna de Centros de Custo
    COL_NOME_CEN = "Centros_Custos" if "Centros_Custos" in df_centros.columns else "Nome_Centro"
    
    # Lista de Centros de Custo para filtros e seletores
    l_cens_seletor = df_centros[COL_NOME_CEN].tolist() if not df_centros.empty and COL_NOME_CEN in df_centros.columns else []

    # Forçar Codigo para String para evitar erros de ordenação (TypeError)
    if not df_categorias.empty and "Codigo" in df_categorias.columns:
        df_categorias["Codigo"] = df_categorias["Codigo"].astype(str)

    # FILTRO: Apenas categorias analíticas que permitem lançamento
    if not df_categorias.empty and "Permite_Lancamento" in df_categorias.columns:
        df_categorias_analiticas = df_categorias[df_categorias["Permite_Lancamento"].astype(str).str.upper() == "SIM"].copy()
    else:
        df_categorias_analiticas = df_categorias.copy()

    st.sidebar.title("Navegação")
    # Botão manual para forçar recarregamento da planilha se necessário
    if st.sidebar.button("🔄 Sincronizar Planilha"):
        st.cache_data.clear()
        st.rerun()

    menu = st.sidebar.radio(
        "Ir para:",
        ["Resumo", "Relatório Mensal", "Importar Extrato", "Conciliação Bancária", "Lançamentos Conciliados", "Cadastros"]
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
    # MENU: CONCILIAÇÃO BANCÁRIA (PENDÊNCIAS)
    # ---------------------------------------------------------
    elif menu == "Conciliação Bancária":
        st.title("🤝 Conciliação de Pendências")
        st.info("Utilize os seletores e clique em 'Confirmar' linha por linha para conciliar.")

        if not df_lancamentos.empty:
            # Filtra apenas o que não tem status CONCILIADO
            if "Status" in df_lancamentos.columns:
                mask = (df_lancamentos["Status"].astype(str).str.upper() != "CONCILIADO")
            else:
                mask = (df_lancamentos["Categoria_ID"] == "") | (df_lancamentos["Centro_Custo_ID"] == "")
            
            df_pendente = df_lancamentos[mask].copy()

            if df_pendente.empty:
                st.success("🎉 Não existem lançamentos pendentes!")
            else:
                st.write(f"Lançamentos para tratar: {len(df_pendente)}")
                
                l_cats = ["", "TRANSFERÊNCIA"] + df_categorias_analiticas["Nome_Categoria"].tolist() if not df_categorias_analiticas.empty else ["", "TRANSFERÊNCIA"]
                l_contas = df_contas["Nome_Conta"].tolist() if not df_contas.empty else []
                
                # Lista para seletores na conciliação (com vazio)
                l_cens = [""] + l_cens_seletor

                # Exibição linha por linha com botão de confirmação individual
                for idx, row in df_pendente.iterrows():
                    linha_index = idx + 2
                    
                    with st.container():
                        c = st.columns([1, 2, 1, 1.5, 1.5, 0.8])
                        c[0].text(row["Data"])
                        c[1].text(row["Descricao"])
                        c[2].text(formatar_moeda_br(row["Valor"]))
                        
                        sel_cat = c[3].selectbox(f"Categoria", l_cats, key=f"cat_p_{idx}")
                        
                        # Lógica de Transferência
                        if sel_cat == "TRANSFERÊNCIA":
                            sel_cen = c[4].selectbox(f"Conta Destino", l_contas, key=f"cen_p_{idx}")
                        else:
                            sel_cen = c[4].selectbox(f"Centro Custo", l_cens, key=f"cen_p_{idx}")
                        
                        if c[5].button("✅ Confirmar", key=f"btn_p_{idx}"):
                            if sel_cat == "" or sel_cen == "":
                                st.error("Selecione os campos necessários.")
                            elif sel_cat == "TRANSFERÊNCIA" and sel_cen == row["Conta_ID"]:
                                st.error("Conta destino deve ser diferente da origem.")
                            else:
                                gc = conectar_planilha()
                                ws_l = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_LANCAMENTOS)
                                ws_l.update_cell(linha_index, 4, sel_cat)
                                ws_l.update_cell(linha_index, 5, sel_cen)
                                ws_l.update_cell(linha_index, 8, "CONCILIADO")
                                
                                # Se for transferência, gera a contrapartida automática para manter o saldo
                                if sel_cat == "TRANSFERÊNCIA":
                                    contrapartida = [
                                        row["Data"],
                                        f"CONTRA-PARTIDA: {row['Descricao']}",
                                        -row["Valor"], # Inverte o sinal para a outra conta
                                        "TRANSFERÊNCIA",
                                        row["Conta_ID"], # O centro de custo vira a conta de origem
                                        sel_cen, # A conta destino
                                        f"TRF-{row['Documento_ID']}",
                                        "CONCILIADO"
                                    ]
                                    ws_l.append_row(contrapartida, value_input_option="USER_ENTERED")
                                
                                st.cache_data.clear() # Limpa cache para refletir a alteração
                                st.success(f"Linha {linha_index} conciliada!")
                                st.rerun()
                        st.divider()

    # ---------------------------------------------------------
    # MENU: LANÇAMENTOS CONCILIADOS (CORREÇÃO)
    # ---------------------------------------------------------
    elif menu == "Lançamentos Conciliados":
        st.title("✅ Lançamentos Conciliados")
        st.info("Revise o que já foi confirmado. Se alterar aqui, o lançamento continuará nesta aba.")

        if not df_lancamentos.empty:
            if "Status" in df_lancamentos.columns:
                mask_conciliado = (df_lancamentos["Status"].astype(str).str.upper() == "CONCILIADO")
            else:
                mask_conciliado = (df_lancamentos["Categoria_ID"] != "") & (df_lancamentos["Centro_Custo_ID"] != "")
                
            df_conciliado = df_lancamentos[mask_conciliado].copy()

            if df_conciliado.empty:
                st.info("Nenhum lançamento conciliado encontrado.")
            else:
                l_cats = ["", "TRANSFERÊNCIA"] + df_categorias_analiticas["Nome_Categoria"].tolist() if not df_categorias_analiticas.empty else ["", "TRANSFERÊNCIA"]
                l_contas = df_contas["Nome_Conta"].tolist() if not df_contas.empty else []
                
                l_cens = [""] + l_cens_seletor

                for idx, row in df_conciliado.iterrows():
                    linha_index = idx + 2
                    with st.container():
                        c = st.columns([1, 2, 1, 1.5, 1.5, 0.8])
                        c[0].text(row["Data"])
                        c[1].text(row["Descricao"])
                        c[2].text(formatar_moeda_br(row["Valor"]))
                        
                        val_cat_atual = row["Categoria_ID"]
                        val_cen_atual = row["Centro_Custo_ID"]
                        
                        idx_cat = l_cats.index(val_cat_atual) if val_cat_atual in l_cats else 0
                        
                        sel_cat = c[3].selectbox(f"Categoria", l_cats, index=idx_cat, key=f"cat_c_{idx}")
                        
                        if sel_cat == "TRANSFERÊNCIA":
                            idx_cen = l_contas.index(val_cen_atual) if val_cen_atual in l_contas else 0
                            sel_cen = c[4].selectbox(f"Conta Destino", l_contas, index=idx_cen, key=f"cen_c_{idx}")
                        else:
                            idx_cen = l_cens.index(val_cen_atual) if val_cen_atual in l_cens else 0
                            sel_cen = c[4].selectbox(f"Centro Custo", l_cens, index=idx_cen, key=f"cen_c_{idx}")
                        
                        if c[5].button("💾 Salvar", key=f"btn_c_{idx}"):
                            gc = conectar_planilha()
                            ws_l = gc.open_by_key(ID_DA_PLANILHA).worksheet(NOME_ABA_LANCAMENTOS)
                            ws_l.update_cell(linha_index, 4, sel_cat)
                            ws_l.update_cell(linha_index, 5, sel_cen)
                            st.cache_data.clear()
                            st.success(f"Atualizado!")
                            st.rerun()
                        st.divider()

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

    # ---------------------------------------------------------
    # MENU: RELATÓRIO MENSAL (DRE HIERÁRQUICO MELHORADO)
    # ---------------------------------------------------------
    elif menu == "Relatório Mensal":
        st.title("📊 Realizado Mensal (Estrutura Hierárquica)")
        
        # Filtro de Centro de Custo na barra lateral
        centro_filtro = st.sidebar.selectbox("Filtrar por Centro de Custo:", ["Todos"] + l_cens_seletor)
        
        if not df_lancamentos.empty and not df_categorias.empty:
            
            # Filtros Base: Ignorar transferências
            df_dre_input = df_lancamentos[df_lancamentos["Categoria_ID"] != "TRANSFERÊNCIA"].copy()
            
            # Filtro adicional de Centro de Custo se selecionado
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
            
            # Ordena as categorias pelo código para processamento hierárquico
            df_cats_ord = df_categorias.sort_values(by="Codigo")
            
            # Garante que a coluna Nível existe e é numérica
            if "Nivel" in df_cats_ord.columns:
                df_cats_ord["Nivel"] = pd.to_numeric(df_cats_ord["Nivel"], errors='coerce').fillna(4).astype(int)
            else:
                st.error("A aba Categorias precisa ter a coluna 'Nivel' (1 a 4).")
                st.stop()
            
            # Processa cada categoria hierarquicamente
            for _, cat in df_cats_ord.iterrows():
                codigo_pai = str(cat["Codigo"])
                nome_cat = cat["Nome_Categoria"]
                nivel = cat["Nivel"]
                
                # Formatação da descrição com base no nível (indentação)
                prefixo = "  " * (nivel - 1)
                
                linha_dre = {"Código": codigo_pai, "Descrição": prefixo + nome_cat, "Nível": nivel}
                
                # Soma os valores para cada mês considerando a hierarquia (começa com o código pai)
                valores_linha = []
                for mes in colunas_meses:
                    # Filtra lançamentos cujo código começa com o código pai desta linha
                    mask = df_pivot_ana.index.astype(str).str.startswith(codigo_pai)
                    valor_total = df_pivot_ana[mask][mes].sum()
                    linha_dre[mes] = valor_total
                    valores_linha.append(valor_total)
                
                # Cálculos de Total e Média (solicitados)
                total_linha = sum(valores_linha)
                linha_dre["Total Acumulado"] = total_linha
                
                # Média mensal: ignora meses com valor zero para não distorcer a média
                valores_positivos = [v for v in valores_linha if v != 0]
                media_linha = sum(valores_positivos) / len(valores_positivos) if valores_positivos else 0
                linha_dre["Média Mensal"] = media_linha
                
                relatorio_final.append(linha_dre)
            
            # Cria o DataFrame final do DRE
            df_dre = pd.DataFrame(relatorio_final)
            
            # Lista de colunas numéricas para formatação
            colunas_formato = colunas_meses + ["Total Acumulado", "Média Mensal"]
            
            # LÓGICA DE ESTILIZAÇÃO POR NÍVEL (MELHORIA SOLICITADA)
            def aplicar_cores(row):
                nivel = row["Nível"]
                # Nível 1: Azul Marinho / Branco / Negrito
                if nivel == 1:
                    return ['background-color: #002060; color: white; font-weight: bold'] * len(row)
                # Nível 2: Azul Claro / Preto / Negrito
                if nivel == 2:
                    return ['background-color: #BDD7EE; color: black; font-weight: bold'] * len(row)
                # Nível 3: Cinza / Preto / Negrito
                if nivel == 3:
                    return ['background-color: #D9D9D9; color: black; font-weight: bold'] * len(row)
                # Nível 4: Branco / Preto / Normal
                return ['background-color: white; color: black'] * len(row)

            # Aplica os estilos e a formatação de moeda
            st.dataframe(
                df_dre.style.apply(aplicar_cores, axis=1).format({m: formatar_moeda_br for m in colunas_formato}), 
                use_container_width=True, 
                height=600
            )
            
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
                    gc = conectar_planilha()
                    sh = gc.open_by_key(ID_DA_PLANILHA)
                    ws_c = sh.worksheet(NOME_ABA_CONTAS)
                    # Adiciona nova linha com ID incremental
                    ws_c.append_row([len(df_contas)+1, f_n, f_b, f_s])
                    st.cache_data.clear() # Força recarregamento
                    st.success("Conta salva!")
                    st.rerun()
            st.dataframe(df_contas)

        with tab2:
            st.subheader("Estrutura de Categorias")
            st.write("Hierarquia por pontos: 3 (Nível 1) -> 3.01 (Nível 2) -> 3.01.01 (Nível 3) -> 3.01.01.001 (Analítico)")
            st.info("O campo Nível (1 a 4) é obrigatório para a formatação do relatório.")
            with st.form("form_add_cat"):
                f_c = st.text_input("Código (ex: 3.01.01.001)")
                f_n = st.text_input("Nome da Categoria")
                f_t = st.selectbox("Tipo", ["Receita", "Despesa"])
                permite = st.checkbox("Esta categoria aceita lançamentos diretos? (Analítica)", value=True)
                
                # Novo campo: Nível (solicitado)
                f_v = st.number_input("Nível (1 a 4)", min_value=1, max_value=4, value=4, step=1)
                
                if st.form_submit_button("Salvar Categoria"):
                    if not f_c or not f_n:
                        st.error("Código e Nome são obrigatórios.")
                    else:
                        txt_permite = "SIM" if permite else "NÃO"
                        gc = conectar_planilha()
                        sh = gc.open_by_key(ID_DA_PLANILHA)
                        ws_cat = sh.worksheet(NOME_ABA_CATEGORIAS)
                        # Salva incluindo o nível (solicitado)
                        ws_cat.append_row([str(f_c), f_n, f_t, txt_permite, f_v])
                        st.cache_data.clear() # Força recarregamento
                        st.success("Categoria salva!")
                        st.rerun()
            
            # Exibe tabela ordenada pelo código para facilitar a visualização hierárquica
            if not df_categorias.empty and "Codigo" in df_categorias.columns:
                df_categorias["Codigo"] = df_categorias["Codigo"].astype(str)
                st.dataframe(df_categorias.sort_values(by="Codigo"), use_container_width=True)

        with tab3:
            st.subheader("Novos Centros de Custo")
            with st.form("form_add_cen"):
                f_n = st.text_input("Nome")
                if st.form_submit_button("Salvar"):
                    if not f_n:
                        st.error("Nome é obrigatório.")
                    else:
                        gc = conectar_planilha()
                        sh = gc.open_by_key(ID_DA_PLANILHA)
                        ws_cen = sh.worksheet(NOME_ABA_CENTROS)
                        # Salva com ID incremental
                        ws_cen.append_row([len(df_centros)+1, f_n])
                        st.cache_data.clear() # Força recarregamento
                        st.success("Centro salvo!")
                        st.rerun()
            st.dataframe(df_centros)
