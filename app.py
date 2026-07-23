# ============================================================
# CLASSIFICADOR DE XML NF-e — INTERFACE STREAMLIT
# Tema: Thomson Reuters / Domínio Sistemas — Dark Mode
# ============================================================

import streamlit as st
import pandas as pd
import zipfile
import shutil
import os
import io
from pathlib import Path
from datetime import datetime
from classificador import (
    classificar_xmls, analisar_duplicatas,
    cfop_para_categoria, CATEGORIAS, indexar_xmls
)

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Classificador XML NF-e",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# MAPA DE CATEGORIAS CUSTOMIZADO (override total)
# ============================================================

def _expandir(cfops_raw: list) -> set:
    """Expande ranges e inteiros para um set de ints."""
    resultado = set()
    for item in cfops_raw:
        if isinstance(item, tuple):
            resultado.update(range(item[0], item[1] + 1))
        else:
            resultado.add(item)
    return resultado

CATEGORIAS_CUSTOM = {
    "COMPRAS_MP_INDUSTRIALIZACAO": _expandir([
        1101,1111,1116,1117,1118,1120,1122,1124,1125,1126,
        (1251,1258), 1401,
        2101,2111,2116,2117,2118,2120,2122,2124,2125,2126,
        (2251,2258), 2401,
    ]),
    "COMPRAS_REVENDA": _expandir([
        1102,1113,1121,1123,1403,
        2102,2113,2121,2123,2403,
    ]),
    "DEVOLUCOES_MP_INDUSTRIALIZACAO": _expandir([
        1201,1203,1208,(1302,1306),
        2201,2203,2208,(2302,2306),
    ]),
    "DEVOLUCOES_REVENDA": _expandir([
        1202,1204,1207,1209,
        2202,2204,2207,2209,
    ]),
    "TRANSFERENCIA_MP_INDUSTRIALIZACAO": _expandir([
        1151,1155,1408,
        2151,2155,2408,
    ]),
    "TRANSFERENCIA_REVENDA": _expandir([
        1152,1156,1409,
        2152,2156,2409,
    ]),
    "TRANSFERENCIA_USO_CONSUMO": _expandir([
        1157,
        2157,
    ]),
    "TRANSFERENCIA_OUTRAS": _expandir([
        1153,1154,1158,1159,
        2153,2154,2158,2159,
    ]),
    "SERVICOS": _expandir([
        1301,
        2301,
    ]),
    "CTE_FRETES_TRANSPORTE": _expandir([
        (1351,1356),(1360,1363),1932,
        (2351,2356),(2360,2363),2932,
    ]),
    "ATIVO_IMOBILIZADO": _expandir([
        1406,(1551,1555),
        2406,(2551,2555),
    ]),
    "USO_CONSUMO": _expandir([
        1407,1556,1557,
        2407,2556,2557,
    ]),
    "OUTROS": _expandir([
        (1601,1605),(1651,1656),(1900,1949),
        (2601,2605),(2651,2656),(2900,2949),
    ]),
}

# Índice reverso: cfop_int → categoria
_CFOP_PARA_CAT: dict[int, str] = {}
for _cat, _cfops in CATEGORIAS_CUSTOM.items():
    for _c in _cfops:
        _CFOP_PARA_CAT[_c] = _cat


def cfop_para_categoria_custom(cfop_str: str) -> str:
    """Retorna a categoria do CFOP usando o mapa customizado."""
    try:
        cfop_int = int(str(cfop_str).strip())
    except (ValueError, TypeError):
        return "OUTROS"
    return _CFOP_PARA_CAT.get(cfop_int, "OUTROS")


# ============================================================
# DETECTAR CT-e
# ============================================================

def is_cte(xml_bytes: bytes) -> bool:
    try:
        conteudo = xml_bytes.decode("utf-8", errors="ignore")
    except Exception:
        conteudo = ""
    return "<cteProc" in conteudo or "<CTe " in conteudo or "<CTe>" in conteudo


# ============================================================
# CSS TEMA ESCURO TR / DOMÍNIO
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background-color: #0D1117;
    font-family: 'Inter', sans-serif;
    color: #E6EDF3;
}
[data-testid="stSidebar"] {
    background-color: #161B22;
    border-right: 1px solid #30363D;
}
.main-header {
    background: linear-gradient(135deg,#161B22,#1C2128);
    border: 1px solid #30363D;
    border-left: 4px solid #E8580A;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 24px;
}
.tr-badge {
    background: linear-gradient(135deg,#E8580A,#C44A08);
    color: white; font-size:10px; font-weight:700;
    padding:3px 8px; border-radius:4px; letter-spacing:1px;
}
.metric-card {
    background:#161B22; border:1px solid #30363D;
    border-radius:8px; padding:16px 20px; text-align:center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color:#E8580A; }
.metric-card .value { font-size:28px; font-weight:700; color:#E8580A; line-height:1; }
.metric-card .label { font-size:11px; color:#8B949E; margin-top:6px; text-transform:uppercase; }
.metric-card.green  .value { color:#3FB950; }
.metric-card.red    .value { color:#F85149; }
.metric-card.yellow .value { color:#D29922; }
.metric-card.blue   .value { color:#58A6FF; }
.metric-card.orange .value { color:#E8580A; }
.metric-card.purple .value { color:#BC8CFF; }

.section-title {
    color:#E6EDF3; font-size:14px; font-weight:600;
    margin:24px 0 12px 0; padding-bottom:8px;
    border-bottom:1px solid #30363D;
}
.conflict-card {
    background:#161B22; border:1px solid #E8580A;
    border-radius:8px; padding:16px 20px; margin-bottom:16px;
}
.conflict-card .chave {
    font-family:monospace; font-size:11px;
    color:#58A6FF; word-break:break-all;
}
.conflict-card .titulo {
    color:#E8580A; font-weight:700; font-size:13px; margin-bottom:8px;
}
.status-box {
    border-radius:8px; padding:12px 16px; margin:8px 0;
    font-size:13px; display:flex; align-items:center; gap:10px;
}
.status-success { background:rgba(63,185,80,.1);  border:1px solid rgba(63,185,80,.3);  color:#3FB950; }
.status-warning { background:rgba(210,153,34,.1); border:1px solid rgba(210,153,34,.3); color:#D29922; }
.status-error   { background:rgba(248,81,73,.1);  border:1px solid rgba(248,81,73,.3);  color:#F85149; }
.status-info    { background:rgba(88,166,255,.1); border:1px solid rgba(88,166,255,.3); color:#58A6FF; }
.status-purple  { background:rgba(188,140,255,.1);border:1px solid rgba(188,140,255,.3);color:#BC8CFF; }

.stButton > button {
    background:linear-gradient(135deg,#E8580A,#C44A08) !important;
    color:white !important; border:none !important;
    border-radius:6px !important; font-weight:600 !important;
    font-size:14px !important; padding:12px 32px !important;
    width:100% !important; transition:all .2s !important;
}
.stButton > button:hover {
    background:linear-gradient(135deg,#FF6B1A,#E8580A) !important;
    transform:translateY(-1px) !important;
    box-shadow:0 4px 12px rgba(232,88,10,.4) !important;
}
.stCheckbox label { color:#E6EDF3 !important; font-size:13px !important; }
[data-testid="stTabs"] button { color:#8B949E !important; }
[data-testid="stTabs"] button[aria-selected="true"] {
    color:#E8580A !important; border-bottom:2px solid #E8580A !important;
}
.stProgress > div > div {
    background:linear-gradient(90deg,#E8580A,#FF6B1A) !important;
    border-radius:4px !important;
}
::-webkit-scrollbar { width:6px; height:6px; }
::-webkit-scrollbar-track { background:#0D1117; }
::-webkit-scrollbar-thumb { background:#30363D; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#E8580A; }
#MainMenu, footer, header { visibility:hidden; }
.block-container { padding-top:1.5rem !important; }
.footer {
    text-align:center; color:#30363D; font-size:11px;
    margin-top:40px; padding-top:16px; border-top:1px solid #21262D;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# SESSION STATE
# ============================================================

for key, default in {
    "etapa":          1,
    "planilha_bytes": None,
    "xml_bytes":      None,
    "xml_tipo":       None,
    "xml_nomes":      [],
    "dict_conflito":  {},
    "decisoes":       {},
    "resultado":      None,
    "df_preview":     None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="main-header">
  <div style="display:flex;align-items:center;gap:12px;">
    <div style="font-size:36px;">📂</div>
    <div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="font-size:22px;font-weight:700;color:#E6EDF3;">
          Classificador de XML NF-e / CT-e
        </span>
        <span class="tr-badge">FISCAL</span>
      </div>
      <p style="color:#8B949E;font-size:13px;margin:4px 0 0 0;">
        Classifique XMLs por categoria fiscal · CT-e separado · Gerencie duplicatas · Exporte relatório
      </p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# INDICADOR DE ETAPAS
# ============================================================

etapas = ["📋 Upload", "⚠️ Duplicatas", "✅ Resultado"]
cols_eta = st.columns(3)
for i, (col, nome) in enumerate(zip(cols_eta, etapas), 1):
    ativo = st.session_state.etapa == i
    cor   = "#E8580A" if ativo else "#30363D"
    txt   = "#E6EDF3" if ativo else "#8B949E"
    with col:
        st.markdown(f"""
        <div style="text-align:center;padding:10px;border-radius:8px;
                    border:2px solid {cor};background:#161B22;">
          <span style="color:{txt};font-weight:{'700' if ativo else '400'};font-size:13px;">
            {nome}
          </span>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================
# HELPERS
# ============================================================

def aplicar_categoria_custom(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica cfop_para_categoria_custom na coluna CATEGORIA do df."""
    if "CFOP" in df.columns:
        df = df.copy()
        df["CATEGORIA"] = df["CFOP"].apply(cfop_para_categoria_custom)
    return df


def override_listas(resultado: dict) -> dict:
    """Reaplica categorias customizadas nas listas encontrados/nao_encontrados."""
    for lista_key in ["encontrados", "nao_encontrados"]:
        nova = []
        for item in resultado.get(lista_key, []):
            cfop = str(item.get("CFOP", "")).strip()
            nova.append({**item, "CATEGORIA": cfop_para_categoria_custom(cfop)})
        resultado[lista_key] = nova
    return resultado


def df_tab(df_, altura=380):
    if isinstance(df_, list):
        df_ = pd.DataFrame(df_)
    if df_.empty:
        st.markdown('<div class="status-box status-info">Nenhum registro.</div>',
                    unsafe_allow_html=True)
    else:
        st.dataframe(df_, use_container_width=True, height=altura)


# ============================================================
# ETAPA 1 — UPLOAD
# ============================================================

if st.session_state.etapa == 1:

    col_l, col_r = st.columns([1, 2])

    with col_l:
        st.markdown('<div class="section-title">📋 Planilha Excel</div>',
                    unsafe_allow_html=True)
        planilha_up = st.file_uploader(
            "Classificação.xlsx", type=["xlsx", "xls"], key="up_plan")

        st.markdown('<div class="section-title">📁 Arquivos XML / CT-e</div>',
                    unsafe_allow_html=True)
        tipo_xml = st.radio("Formato", ["📦 ZIP", "📄 XMLs individuais"],
                            label_visibility="collapsed")

        if tipo_xml == "📦 ZIP":
            xml_up = st.file_uploader("ZIP com XMLs", type=["zip"], key="up_zip")
        else:
            xml_up = st.file_uploader("XMLs", type=["xml"],
                                      accept_multiple_files=True, key="up_xml")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_analisar = st.button("🔍  ANALISAR PLANILHA")

    with col_r:
        if planilha_up:
            st.markdown('<div class="section-title">👁️ Preview</div>',
                        unsafe_allow_html=True)
            try:
                planilha_up.seek(0)
                df_prev = pd.read_excel(planilha_up, sheet_name="Planilha1", dtype=str)
                df_prev.columns = ["CFOP", "CHAVE_NFE"]
                df_prev["CFOP"]      = df_prev["CFOP"].str.strip()
                df_prev["CHAVE_NFE"] = df_prev["CHAVE_NFE"].str.strip()
                df_prev["CATEGORIA"] = df_prev["CFOP"].apply(cfop_para_categoria_custom)

                total   = len(df_prev)
                com_ch  = df_prev["CHAVE_NFE"].notna().sum()
                sem_ch  = df_prev["CHAVE_NFE"].isna().sum()
                cfops_u = df_prev["CFOP"].nunique()

                c1, c2, c3, c4 = st.columns(4)
                for col_, val, lbl, cls in [
                    (c1, total,   "Registros",    ""),
                    (c2, com_ch,  "Com Chave",    "green"),
                    (c3, sem_ch,  "Sem Chave",    "yellow"),
                    (c4, cfops_u, "CFOPs Únicos", "blue"),
                ]:
                    with col_:
                        st.markdown(f"""
                        <div class="metric-card {cls}">
                          <div class="value">{val:,}</div>
                          <div class="label">{lbl}</div>
                        </div>""", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                planilha_up.seek(0)
                st.dataframe(df_prev.head(30), use_container_width=True, height=320)
                st.session_state.df_preview = df_prev

            except Exception as e:
                st.markdown(f'<div class="status-box status-error">❌ {e}</div>',
                            unsafe_allow_html=True)

    # ── Botão Analisar ──────────────────────────────────────
    if btn_analisar:
        if not planilha_up:
            st.markdown('<div class="status-box status-error">❌ Envie a planilha.</div>',
                        unsafe_allow_html=True)
        elif not xml_up:
            st.markdown('<div class="status-box status-error">❌ Envie os XMLs.</div>',
                        unsafe_allow_html=True)
        else:
            planilha_up.seek(0)
            st.session_state.planilha_bytes = planilha_up.read()
            st.session_state.xml_tipo       = "zip" if tipo_xml == "📦 ZIP" else "xml"

            if tipo_xml == "📦 ZIP":
                xml_up.seek(0)
                st.session_state.xml_bytes = xml_up.read()
                st.session_state.xml_nomes = []
            else:
                st.session_state.xml_bytes = {f.name: f.read() for f in xml_up}
                st.session_state.xml_nomes = list(st.session_state.xml_bytes.keys())

            df_tmp = pd.read_excel(
                io.BytesIO(st.session_state.planilha_bytes),
                sheet_name="Planilha1", dtype=str)
            df_tmp.columns      = ["CFOP", "CHAVE_NFE"]
            df_tmp["CFOP"]      = df_tmp["CFOP"].str.strip()
            df_tmp["CHAVE_NFE"] = df_tmp["CHAVE_NFE"].str.strip()
            df_tmp["CATEGORIA"] = df_tmp["CFOP"].apply(cfop_para_categoria_custom)
            df_com = df_tmp[df_tmp["CHAVE_NFE"].notna() &
                            (df_tmp["CHAVE_NFE"] != "nan")].copy()

            _, _, dict_conf = analisar_duplicatas(df_com)
            st.session_state.dict_conflito = dict_conf
            st.session_state.decisoes      = {}

            st.session_state.etapa = 2 if dict_conf else 3
            st.rerun()

# ============================================================
# ETAPA 2 — RESOLUÇÃO DE DUPLICATAS COM CONFLITO
# ============================================================

elif st.session_state.etapa == 2:

    dict_conf = st.session_state.dict_conflito
    n_conf    = len(dict_conf)

    st.markdown(f"""
    <div class="status-box status-warning">
      ⚠️ <strong>{n_conf} XML(s)</strong> aparecem em categorias diferentes na planilha.
      Selecione para qual(is) pasta(s) cada um deve ser copiado.
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-title">⚠️ XMLs com Conflito de Categoria</div>',
                unsafe_allow_html=True)

    decisoes_temp = {}

    for idx, (chave, opcoes) in enumerate(dict_conf.items(), 1):
        cats_disponiveis = list({o["categoria"] for o in opcoes})
        cfops_por_cat    = {}
        for o in opcoes:
            cfops_por_cat.setdefault(o["categoria"], []).append(o["cfop"])

        st.markdown(f"""
        <div class="conflict-card">
          <div class="titulo">XML {idx} de {n_conf}</div>
          <div class="chave">🔑 {chave}</div>
        </div>""", unsafe_allow_html=True)

        col_info, col_sel = st.columns([2, 3])

        with col_info:
            st.markdown("**CFOPs na planilha:**")
            for o in opcoes:
                st.markdown(
                    f"&nbsp;&nbsp;`{o['cfop']}` → `{o['categoria']}`",
                    unsafe_allow_html=True)

        with col_sel:
            st.markdown("**Selecione o destino:**")
            todas = st.checkbox(
                "📁 Copiar para TODAS as categorias",
                value=True,
                key=f"todas_{chave}"
            )
            selecionadas = []
            if todas:
                selecionadas = cats_disponiveis
                for cat in cats_disponiveis:
                    cfops_str = ", ".join(cfops_por_cat.get(cat, []))
                    st.markdown(
                        f"<span style='color:#3FB950;'>✅</span> "
                        f"`{cat}` <span style='color:#8B949E;font-size:11px;'>"
                        f"(CFOPs: {cfops_str})</span>",
                        unsafe_allow_html=True)
            else:
                for cat in cats_disponiveis:
                    cfops_str = ", ".join(cfops_por_cat.get(cat, []))
                    chk = st.checkbox(
                        f"{cat}  (CFOPs: {cfops_str})",
                        value=True,
                        key=f"chk_{chave}_{cat}"
                    )
                    if chk:
                        selecionadas.append(cat)

        decisoes_temp[chave] = selecionadas
        st.markdown("---")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("← Voltar"):
            st.session_state.etapa = 1
            st.rerun()
    with col_b2:
        if st.button("✅  CONFIRMAR E PROCESSAR"):
            st.session_state.decisoes = decisoes_temp
            st.session_state.etapa    = 3
            st.rerun()

# ============================================================
# ETAPA 3 — PROCESSAMENTO E RESULTADO
# ============================================================

elif st.session_state.etapa == 3:

    resultado = st.session_state.resultado

    # ── Processar se ainda não foi feito ───────────────────
    if resultado is None:
        prog = st.progress(0)
        info = st.empty()

        try:
            tmp = Path("tmp_class")
            tmp.mkdir(exist_ok=True)
            pasta_xmls = tmp / "xmls"
            pasta_xmls.mkdir(exist_ok=True)

            info.markdown('<div class="status-box status-info">⏳ Salvando arquivos...</div>',
                          unsafe_allow_html=True)
            prog.progress(15)

            plan_path = tmp / "Classificacao.xlsx"
            plan_path.write_bytes(st.session_state.planilha_bytes)

            if st.session_state.xml_tipo == "zip":
                zip_path = tmp / "xmls.zip"
                zip_path.write_bytes(st.session_state.xml_bytes)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(pasta_xmls)
            else:
                for nome, conteudo in st.session_state.xml_bytes.items():
                    (pasta_xmls / nome).write_bytes(conteudo)

            info.markdown('<div class="status-box status-info">⏳ Classificando XMLs...</div>',
                          unsafe_allow_html=True)
            prog.progress(40)

            pasta_out = tmp / "output"
            resultado = classificar_xmls(
                caminho_planilha    = str(plan_path),
                caminho_xmls_ou_zip = str(pasta_xmls),
                pasta_output        = str(pasta_out),
                decisoes_usuario    = st.session_state.decisoes
            )

            # ── Override categorias em todos os DataFrames ──
            for df_key in ["df_planilha", "df_com_chave", "df_sem_chave",
                           "df_auto", "df_conflito"]:
                if df_key in resultado and resultado[df_key] is not None:
                    resultado[df_key] = aplicar_categoria_custom(resultado[df_key])

            resultado = override_listas(resultado)

            # ── Separar CT-e ────────────────────────────────
            prog.progress(60)
            info.markdown('<div class="status-box status-info">⏳ Separando CT-e...</div>',
                          unsafe_allow_html=True)

            ctes_encontrados = []
            pasta_cte = pasta_out / "CTE"
            pasta_cte.mkdir(exist_ok=True)

            for xml_file in pasta_xmls.rglob("*.xml"):
                conteudo = xml_file.read_bytes()
                if is_cte(conteudo):
                    (pasta_cte / xml_file.name).write_bytes(conteudo)
                    ctes_encontrados.append({
                        "ARQUIVO":   xml_file.name,
                        "CATEGORIA": "CTE"
                    })

            resultado["ctes_encontrados"] = ctes_encontrados

            # ── ZIP MASTER: um ZIP por categoria + CTE ──────
            prog.progress(75)
            info.markdown('<div class="status-box status-info">⏳ Gerando ZIPs...</div>',
                          unsafe_allow_html=True)

            zip_master_buf = io.BytesIO()
            with zipfile.ZipFile(zip_master_buf, "w", zipfile.ZIP_DEFLATED) as zf_master:

                if "zips_por_categoria" in resultado:
                    for cat, zip_cat_path in resultado["zips_por_categoria"].items():
                        zf_master.write(zip_cat_path, f"{cat}.zip")
                else:
                    with open(resultado["zip"], "rb") as f_zip:
                        zf_master.writestr("Classificados.zip", f_zip.read())

                if ctes_encontrados:
                    cte_buf = io.BytesIO()
                    with zipfile.ZipFile(cte_buf, "w", zipfile.ZIP_DEFLATED) as zf_cte:
                        for xml_file in pasta_cte.glob("*.xml"):
                            zf_cte.write(xml_file, xml_file.name)
                    zf_master.writestr("CTE.zip", cte_buf.getvalue())

            resultado["zip_bytes"] = zip_master_buf.getvalue()

            # ── Relatório Excel ─────────────────────────────
            with open(resultado["relatorio"], "rb") as f:
                resultado["rel_bytes"] = f.read()

            prog.progress(100)
            info.markdown('<div class="status-box status-success">✅ Concluído!</div>',
                          unsafe_allow_html=True)

            st.session_state.resultado = resultado
            shutil.rmtree(tmp, ignore_errors=True)

        except Exception as e:
            prog.progress(0)
            st.markdown(f'<div class="status-box status-error">❌ Erro: {e}</div>',
                        unsafe_allow_html=True)
            st.exception(e)
            shutil.rmtree(tmp, ignore_errors=True)
            st.stop()

    # ── Exibir resultados ───────────────────────────────────
    resultado = st.session_state.resultado

    df_plan = resultado["df_planilha"]
    df_com  = resultado["df_com_chave"]
    df_sem  = resultado["df_sem_chave"]
    enc     = resultado["encontrados"]
    nao     = resultado["nao_encontrados"]
    ctes    = resultado.get("ctes_encontrados", [])

    st.markdown('<div class="section-title">📊 Resultados</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    for col_, val, lbl, cls in [
        (c1, len(df_plan), "Total Registros",  ""),
        (c2, len(df_com),  "Com Chave",        "blue"),
        (c3, len(enc),     "NF-e Encontradas", "green"),
        (c4, len(nao),     "Não Encontrados",  "red"),
        (c5, len(df_sem),  "Sem Chave (NaN)",  "yellow"),
        (c6, len(ctes),    "CT-e Separados",   "purple"),
    ]:
        with col_:
            st.markdown(f"""
            <div class="metric-card {cls}">
              <div class="value">{val:,}</div>
              <div class="label">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 Resumo por Categoria",
        "🚛 CT-e Separados",
        "⚠️ Duplicatas Auto",
        "🔀 Conflitos Resolvidos",
        "✅ Encontrados",
        "❌ Não Encontrados",
        "🔍 Sem Chave"
    ])

    with tabs[0]:
        rows = []
        for cat, cfops_set in CATEGORIAS_CUSTOM.items():
            rows.append({
                "Categoria":       cat,
                "Qtd CFOPs":       len(cfops_set),
                "Total Planilha":  int(df_plan["CFOP"].apply(
                                       lambda x: int(x) if str(x).isdigit() else 0
                                   ).isin(cfops_set).sum()),
                "Com Chave":       int((df_com["CATEGORIA"] == cat).sum()),
                "Encontrados":     sum(1 for r in enc if r["CATEGORIA"] == cat),
                "Não Encontrados": sum(1 for r in nao if r["CATEGORIA"] == cat),
                "Sem Chave":       int((df_sem["CATEGORIA"] == cat).sum()),
            })
        # Linha CTE
        rows.append({
            "Categoria":       "CTE",
            "Qtd CFOPs":       "—",
            "Total Planilha":  len(ctes),
            "Com Chave":       len(ctes),
            "Encontrados":     len(ctes),
            "Não Encontrados": 0,
            "Sem Chave":       0,
        })
        df_tab(pd.DataFrame(rows))

    with tabs[1]:
        if not ctes:
            st.markdown('<div class="status-box status-info">'
                        '🚛 Nenhum CT-e encontrado nos arquivos enviados.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box status-purple">'
                        f'🚛 <strong>{len(ctes)}</strong> CT-e(s) identificados e '
                        f'separados em <code>CTE.zip</code> dentro do arquivo final.</div>',
                        unsafe_allow_html=True)
            df_tab(pd.DataFrame(ctes))

    with tabs[2]:
        df_auto  = resultado["df_auto"]
        dup_auto = df_auto[df_auto.duplicated("CHAVE_NFE", keep=False)]
        if dup_auto.empty:
            st.markdown('<div class="status-box status-success">'
                        '✅ Nenhuma duplicata automática.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box status-warning">'
                        f'⚠️ {len(dup_auto["CHAVE_NFE"].unique())} chave(s) com '
                        f'duplicata no mesmo grupo (copiadas 1x automaticamente).</div>',
                        unsafe_allow_html=True)
            df_tab(dup_auto[["CHAVE_NFE", "CFOP", "CATEGORIA"]])

    with tabs[3]:
        if not st.session_state.decisoes:
            st.markdown('<div class="status-box status-success">'
                        '✅ Nenhum conflito encontrado.</div>',
                        unsafe_allow_html=True)
        else:
            rows_conf = []
            for chave, cats_ok in st.session_state.decisoes.items():
                df_c = resultado["df_conflito"]
                grp  = df_c[df_c["CHAVE_NFE"] == chave]
                for _, row in grp.drop_duplicates(["CHAVE_NFE", "CATEGORIA"]).iterrows():
                    rows_conf.append({
                        "CHAVE_NFE": chave,
                        "CFOP":      row["CFOP"],
                        "CATEGORIA": row["CATEGORIA"],
                        "DECISÃO":   "✅ COPIADO" if row["CATEGORIA"] in cats_ok
                                     else "❌ IGNORADO"
                    })
            df_tab(pd.DataFrame(rows_conf))

    with tabs[4]:
        if not enc:
            st.markdown('<div class="status-box status-warning">'
                        '⚠️ Nenhum XML encontrado.</div>', unsafe_allow_html=True)
        else:
            df_tab(pd.DataFrame(enc))

    with tabs[5]:
        if not nao:
            st.markdown('<div class="status-box status-success">'
                        '✅ Todos encontrados!</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box status-error">'
                        f'❌ {len(nao)} chave(s) sem XML correspondente.</div>',
                        unsafe_allow_html=True)
            df_tab(pd.DataFrame(nao))

    with tabs[6]:
        resumo_sem = (df_sem.groupby(["CFOP", "CATEGORIA"])
                      .size().reset_index(name="QUANTIDADE")
                      .sort_values("QUANTIDADE", ascending=False))
        st.markdown(f'<div class="status-box status-warning">'
                    f'🔍 {len(df_sem)} registros sem CHAVE_NFE.</div>',
                    unsafe_allow_html=True)
        df_tab(resumo_sem)

    # ── Download único ──────────────────────────────────────
    st.markdown('<div class="section-title">⬇️ Downloads</div>', unsafe_allow_html=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cd1, cd2, cd3 = st.columns(3)

    with cd1:
        st.download_button(
            "⬇️ Baixar XMLs Classificados (NF-e + CT-e)",
            data=resultado["zip_bytes"],
            file_name=f"Classificados_{ts}.zip",
            mime="application/zip",
            use_container_width=True
        )
    with cd2:
        st.download_button(
            "📊 Relatório Excel",
            data=resultado["rel_bytes"],
            file_name=f"Relatorio_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with cd3:
        if st.button("🔄 Nova Classificação", use_container_width=True):
            for k in ["etapa", "planilha_bytes", "xml_bytes", "xml_tipo",
                      "xml_nomes", "dict_conflito", "decisoes", "resultado", "df_preview"]:
                st.session_state[k] = None if k != "etapa" else 1
                if k in ["dict_conflito", "decisoes"]:
                    st.session_state[k] = {}
                if k == "xml_nomes":
                    st.session_state[k] = []
            st.rerun()

# ── Footer ──────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  Classificador XML NF-e / CT-e · Streamlit · Tema Thomson Reuters / Domínio Sistemas
</div>""", unsafe_allow_html=True)
