# ============================================================
# CLASSIFICADOR DE XML NF-e — INTERFACE STREAMLIT
# Tema: Thomson Reuters / Domínio Sistemas — Dark Mode
# ============================================================

import streamlit as st
import pandas as pd
import zipfile
import shutil
import xml.etree.ElementTree as ET
import io
from pathlib import Path
from datetime import datetime
from classificador import (
    classificar_xmls, analisar_duplicatas,
    cfop_para_categoria, CATEGORIAS, indexar_xmls
)

st.set_page_config(
    page_title="Classificador XML NF-e",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# MAPA DE CATEGORIAS CUSTOMIZADO
# ============================================================

def _expandir(cfops_raw: list) -> set:
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
    "TRANSFERENCIA_USO_CONSUMO": _expandir([1157, 2157]),
    "TRANSFERENCIA_OUTRAS": _expandir([
        1153,1154,1158,1159,
        2153,2154,2158,2159,
    ]),
    "SERVICOS": _expandir([1301, 2301]),
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

_CFOP_PARA_CAT: dict[int, str] = {}
for _cat, _cfops in CATEGORIAS_CUSTOM.items():
    for _c in _cfops:
        _CFOP_PARA_CAT[_c] = _cat


def cfop_para_categoria_custom(cfop_str: str) -> str:
    try:
        cfop_int = int(str(cfop_str).strip())
    except (ValueError, TypeError):
        return "OUTROS"
    return _CFOP_PARA_CAT.get(cfop_int, "OUTROS")


# ============================================================
# LER CHAVE E TIPO DENTRO DO XML
# ============================================================

_NS_NFE = "http://www.portalfiscal.inf.br/nfe"
_NS_CTE = "http://www.portalfiscal.inf.br/cte"

def extrair_chave_xml(xml_bytes: bytes) -> tuple[str | None, str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None, "desconhecido"

    tag = root.tag

    if "cte" in tag.lower() or "CTe" in tag:
        for elem in root.iter(f"{{{_NS_CTE}}}CTe"):
            ch = elem.get("Id", "").replace("CTe", "")
            if len(ch) == 44:
                return ch, "CTe"
        for elem in root.iter(f"{{{_NS_CTE}}}chCTe"):
            if elem.text and len(elem.text.strip()) == 44:
                return elem.text.strip(), "CTe"
        return None, "CTe"

    for elem in root.iter(f"{{{_NS_NFE}}}infNFe"):
        ch = elem.get("Id", "").replace("NFe", "")
        if len(ch) == 44:
            return ch, "NFe"
    for elem in root.iter(f"{{{_NS_NFE}}}chNFe"):
        if elem.text and len(elem.text.strip()) == 44:
            return elem.text.strip(), "NFe"

    for tag_name in ["infNFe", "infCTe"]:
        for elem in root.iter(tag_name):
            ch = elem.get("Id", "").replace("NFe", "").replace("CTe", "")
            if len(ch) == 44:
                tipo = "CTe" if "CTe" in tag_name else "NFe"
                return ch, tipo

    return None, "desconhecido"


def indexar_xmls_por_chave(pasta_xmls: Path) -> dict[str, Path]:
    indice: dict[str, Path] = {}
    for xml_file in pasta_xmls.rglob("*.xml"):
        try:
            chave, _ = extrair_chave_xml(xml_file.read_bytes())
            if chave:
                indice[chave] = xml_file
        except Exception:
            pass
    return indice


def is_cte_bytes(xml_bytes: bytes) -> bool:
    _, tipo = extrair_chave_xml(xml_bytes)
    return tipo == "CTe"


# ============================================================
# CSS — CORRIGIDO (sem seletores agressivos em div/td/th)
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body,
[data-testid="stAppViewContainer"],
[data-testid="block-container"],
.main, .block-container {
    background-color: #0D1117 !important;
    color: #E6EDF3 !important;
    font-family: 'Inter', sans-serif !important;
}

[data-testid="stSidebar"] {
    background-color: #161B22 !important;
}
[data-testid="stSidebar"] * {
    color: #E6EDF3 !important;
}

/* inputs */
input, textarea, select {
    background-color: #1C2128 !important;
    color: #E6EDF3 !important;
    border: 1px solid #30363D !important;
    caret-color: #E6EDF3 !important;
}

/* file uploader */
[data-testid="stFileUploader"],
[data-testid="stFileUploaderDropzone"] {
    background-color: #161B22 !important;
    border-color: #30363D !important;
}
[data-testid="stFileUploader"] *,
[data-testid="stFileUploaderDropzone"] * {
    color: #E6EDF3 !important;
}

/* radio / checkbox */
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
    color: #E6EDF3 !important;
}

/* progress */
[data-testid="stProgress"] > div {
    background-color: #30363D !important;
}
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg,#E8580A,#FF6B1A) !important;
    border-radius: 4px !important;
}

/* tabs */
[data-testid="stTabs"] button {
    color: #8B949E !important;
    background-color: transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #E8580A !important;
    border-bottom: 2px solid #E8580A !important;
    background-color: transparent !important;
}
[data-testid="stTabs"] button:hover {
    color: #E6EDF3 !important;
}

/* botões */
.stButton > button {
    background: linear-gradient(135deg,#E8580A,#C44A08) !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 12px 32px !important;
    width: 100% !important;
    transition: all .2s !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg,#FF6B1A,#E8580A) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(232,88,10,.4) !important;
}

/* download button */
[data-testid="stDownloadButton"] button {
    background-color: #1C2128 !important;
    color: #E6EDF3 !important;
    border: 1px solid #30363D !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    width: 100% !important;
    padding: 12px 16px !important;
    transition: all .2s !important;
}
[data-testid="stDownloadButton"] button:hover {
    border-color: #E8580A !important;
    color: #E8580A !important;
    background-color: rgba(232,88,10,.08) !important;
}

/* alerts / expander */
[data-testid="stAlert"] {
    background-color: #161B22 !important;
    border-color: #30363D !important;
}

/* scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #E8580A; }

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; }

/* componentes custom */
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
    color: white !important;
    font-size: 10px; font-weight: 700;
    padding: 3px 8px; border-radius: 4px; letter-spacing: 1px;
}

.metric-card {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 8px; padding: 16px 20px; text-align: center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: #E8580A; }
.metric-card .value { font-size:28px; font-weight:700; color:#E8580A; line-height:1; }
.metric-card .label { font-size:11px; color:#8B949E; margin-top:6px; text-transform:uppercase; }
.metric-card.green  .value { color:#3FB950; }
.metric-card.red    .value { color:#F85149; }
.metric-card.yellow .value { color:#D29922; }
.metric-card.blue   .value { color:#58A6FF; }
.metric-card.purple .value { color:#BC8CFF; }

.section-title {
    color: #E6EDF3; font-size:14px; font-weight:600;
    margin:24px 0 12px 0; padding-bottom:8px;
    border-bottom:1px solid #30363D;
}

.conflict-card {
    background: #161B22;
    border: 1px solid #E8580A;
    border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;
}
.conflict-card .chave { font-family:monospace; font-size:11px; color:#58A6FF; word-break:break-all; }
.conflict-card .titulo { color:#E8580A; font-weight:700; font-size:13px; margin-bottom:8px; }

.status-box {
    border-radius:8px; padding:12px 16px; margin:8px 0;
    font-size:13px; display:flex; align-items:center; gap:10px;
}
.status-success { background:rgba(63,185,80,.15);  border:1px solid rgba(63,185,80,.4);  color:#3FB950; }
.status-warning { background:rgba(210,153,34,.15); border:1px solid rgba(210,153,34,.4); color:#D29922; }
.status-error   { background:rgba(248,81,73,.15);  border:1px solid rgba(248,81,73,.4);  color:#F85149; }
.status-info    { background:rgba(88,166,255,.15); border:1px solid rgba(88,166,255,.4); color:#58A6FF; }
.status-purple  { background:rgba(188,140,255,.15);border:1px solid rgba(188,140,255,.4);color:#BC8CFF; }

.footer {
    text-align:center; color:#8B949E; font-size:11px;
    margin-top:40px; padding-top:16px; border-top:1px solid #21262D;
}

/* ── TABELA HTML CUSTOM (substitui st.dataframe) ── */
.df-custom-wrap {
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid #30363D;
}
.df-custom {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
}
.df-custom thead th {
    background: #1C2128;
    color: #E8580A;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 2px solid #30363D;
    font-weight: 600;
    white-space: nowrap;
    position: sticky;
    top: 0;
    z-index: 1;
}
.df-custom tbody td {
    background: #161B22;
    color: #E6EDF3;
    padding: 7px 14px;
    border-bottom: 1px solid #21262D;
    white-space: nowrap;
}
.df-custom tbody tr:hover td {
    background: #1C2128;
}
.df-custom tbody tr:last-child td {
    border-bottom: none;
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
# HELPER — TABELA HTML (substitui st.dataframe)
# ============================================================

def df_tab(df_, altura=400):
    if isinstance(df_, list):
        df_ = pd.DataFrame(df_)
    if df_ is None or df_.empty:
        st.markdown(
            '<div class="status-box status-info">ℹ️ Nenhum registro.</div>',
            unsafe_allow_html=True)
        return

    # Escapa HTML nas células
    df_esc = df_.copy()
    for col in df_esc.columns:
        df_esc[col] = df_esc[col].astype(str).str.replace("&", "&amp;") \
                                               .str.replace("<", "&lt;") \
                                               .str.replace(">", "&gt;")

    header = "".join(f"<th>{c}</th>" for c in df_esc.columns)
    rows   = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>"
        for row in df_esc.itertuples(index=False)
    )

    html = f"""
    <div class="df-custom-wrap" style="max-height:{altura}px; overflow-y:auto;">
      <table class="df-custom">
        <thead><tr>{header}</tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


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
        Classifique XMLs por categoria fiscal · Leitura de chave interna · CT-e separado · Exporte relatório
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
    if "CFOP" in df.columns:
        df = df.copy()
        df["CATEGORIA"] = df["CFOP"].apply(cfop_para_categoria_custom)
    return df


def override_listas(resultado: dict) -> dict:
    for lista_key in ["encontrados", "nao_encontrados"]:
        nova = []
        for item in resultado.get(lista_key, []):
            cfop = str(item.get("CFOP", "")).strip()
            nova.append({**item, "CATEGORIA": cfop_para_categoria_custom(cfop)})
        resultado[lista_key] = nova
    return resultado


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
                df_prev.columns      = ["CFOP", "CHAVE_NFE"]
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
                df_tab(df_prev.head(30), altura=320)
                st.session_state.df_preview = df_prev

            except Exception as e:
                st.markdown(f'<div class="status-box status-error">❌ {e}</div>',
                            unsafe_allow_html=True)

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

    if resultado is None:
        prog = st.progress(0)
        info = st.empty()

        try:
            tmp = Path("tmp_class")
            tmp.mkdir(exist_ok=True)
            pasta_xmls = tmp / "xmls"
            pasta_xmls.mkdir(exist_ok=True)
            pasta_out  = tmp / "output"
            pasta_out.mkdir(exist_ok=True)

            info.markdown('<div class="status-box status-info">⏳ Salvando arquivos...</div>',
                          unsafe_allow_html=True)
            prog.progress(10)

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

            info.markdown('<div class="status-box status-info">⏳ Indexando XMLs pela chave interna...</div>',
                          unsafe_allow_html=True)
            prog.progress(25)

            indice_xml = indexar_xmls_por_chave(pasta_xmls)

            info.markdown('<div class="status-box status-info">⏳ Cruzando planilha com XMLs...</div>',
                          unsafe_allow_html=True)
            prog.progress(40)

            df_plan = pd.read_excel(
                io.BytesIO(st.session_state.planilha_bytes),
                sheet_name="Planilha1", dtype=str)
            df_plan.columns      = ["CFOP", "CHAVE_NFE"]
            df_plan["CFOP"]      = df_plan["CFOP"].str.strip()
            df_plan["CHAVE_NFE"] = df_plan["CHAVE_NFE"].str.strip()
            df_plan["CATEGORIA"] = df_plan["CFOP"].apply(cfop_para_categoria_custom)

            df_com = df_plan[df_plan["CHAVE_NFE"].notna() &
                             (df_plan["CHAVE_NFE"] != "nan") &
                             (df_plan["CHAVE_NFE"] != "")].copy()
            df_sem = df_plan[~df_plan.index.isin(df_com.index)].copy()

            info.markdown('<div class="status-box status-info">⏳ Classificando e copiando XMLs...</div>',
                          unsafe_allow_html=True)
            prog.progress(55)

            encontrados      = []
            nao_encontrados  = []
            ctes_encontrados = []

            pastas_cat: dict[str, Path] = {}
            for cat in CATEGORIAS_CUSTOM:
                p = pasta_out / cat
                p.mkdir(exist_ok=True)
                pastas_cat[cat] = p
            pasta_cte = pasta_out / "CTE"
            pasta_cte.mkdir(exist_ok=True)

            decisoes = st.session_state.decisoes
            grupos   = df_com.groupby("CHAVE_NFE")

            for chave, grp in grupos:
                xml_path = indice_xml.get(chave)

                if xml_path is None:
                    for _, row in grp.iterrows():
                        nao_encontrados.append({
                            "CHAVE_NFE": chave,
                            "CFOP":      row["CFOP"],
                            "CATEGORIA": row["CATEGORIA"],
                            "ARQUIVO":   "NÃO ENCONTRADO",
                        })
                    continue

                xml_bytes_local = xml_path.read_bytes()
                _, tipo = extrair_chave_xml(xml_bytes_local)

                if tipo == "CTe":
                    destino = pasta_cte / xml_path.name
                    destino.write_bytes(xml_bytes_local)
                    ctes_encontrados.append({
                        "ARQUIVO":   xml_path.name,
                        "CHAVE":     chave,
                        "CATEGORIA": "CTE",
                    })
                    continue

                cats_grp = grp["CATEGORIA"].unique().tolist()
                cats_destino = decisoes.get(chave, cats_grp) if len(cats_grp) > 1 else cats_grp

                for cat in cats_destino:
                    destino = pastas_cat.get(cat, pasta_out / "OUTROS")
                    destino.mkdir(exist_ok=True)
                    (destino / xml_path.name).write_bytes(xml_bytes_local)

                for _, row in grp.iterrows():
                    encontrados.append({
                        "CHAVE_NFE": chave,
                        "CFOP":      row["CFOP"],
                        "CATEGORIA": row["CATEGORIA"],
                        "ARQUIVO":   xml_path.name,
                    })

            # CT-e avulsos no ZIP não listados na planilha
            for xml_file in pasta_xmls.rglob("*.xml"):
                xml_bytes_local = xml_file.read_bytes()
                chave_interna, tipo = extrair_chave_xml(xml_bytes_local)
                if tipo == "CTe" and chave_interna not in {c["CHAVE"] for c in ctes_encontrados}:
                    destino = pasta_cte / xml_file.name
                    destino.write_bytes(xml_bytes_local)
                    ctes_encontrados.append({
                        "ARQUIVO":   xml_file.name,
                        "CHAVE":     chave_interna or "desconhecida",
                        "CATEGORIA": "CTE",
                    })

            prog.progress(75)
            info.markdown('<div class="status-box status-info">⏳ Gerando ZIPs por categoria...</div>',
                          unsafe_allow_html=True)

            zip_master_buf = io.BytesIO()
            with zipfile.ZipFile(zip_master_buf, "w", zipfile.ZIP_DEFLATED) as zf_master:
                for cat, pasta_cat in pastas_cat.items():
                    xmls_cat = list(pasta_cat.glob("*.xml"))
                    if xmls_cat:
                        cat_buf = io.BytesIO()
                        with zipfile.ZipFile(cat_buf, "w", zipfile.ZIP_DEFLATED) as zf_cat:
                            for xf in xmls_cat:
                                zf_cat.write(xf, xf.name)
                        zf_master.writestr(f"{cat}.zip", cat_buf.getvalue())

                xmls_cte = list(pasta_cte.glob("*.xml"))
                if xmls_cte:
                    cte_buf = io.BytesIO()
                    with zipfile.ZipFile(cte_buf, "w", zipfile.ZIP_DEFLATED) as zf_cte:
                        for xf in xmls_cte:
                            zf_cte.write(xf, xf.name)
                    zf_master.writestr("CTE.zip", cte_buf.getvalue())

            zip_bytes = zip_master_buf.getvalue()

            prog.progress(88)
            info.markdown('<div class="status-box status-info">⏳ Gerando relatório...</div>',
                          unsafe_allow_html=True)

            rel_buf = io.BytesIO()
            with pd.ExcelWriter(rel_buf, engine="openpyxl") as writer:
                df_plan.to_excel(writer, sheet_name="Planilha Completa", index=False)
                df_com.to_excel(writer,  sheet_name="Com Chave",         index=False)
                df_sem.to_excel(writer,  sheet_name="Sem Chave",         index=False)
                if encontrados:
                    pd.DataFrame(encontrados).to_excel(writer, sheet_name="Encontrados",     index=False)
                if nao_encontrados:
                    pd.DataFrame(nao_encontrados).to_excel(writer, sheet_name="Não Encontrados", index=False)
                if ctes_encontrados:
                    pd.DataFrame(ctes_encontrados).to_excel(writer, sheet_name="CT-e",          index=False)
            rel_bytes = rel_buf.getvalue()

            resultado = {
                "df_planilha":      df_plan,
                "df_com_chave":     df_com,
                "df_sem_chave":     df_sem,
                "encontrados":      encontrados,
                "nao_encontrados":  nao_encontrados,
                "ctes_encontrados": ctes_encontrados,
                "zip_bytes":        zip_bytes,
                "rel_bytes":        rel_bytes,
                "indice_xml":       indice_xml,
            }

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

    tabs = st.tabs([
        "📊 Resumo por Categoria",
        "🚛 CT-e Separados",
        "✅ Encontrados",
        "❌ Não Encontrados",
        "🔍 Sem Chave",
        "🗂️ Índice XMLs",
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
                        '🚛 Nenhum CT-e encontrado.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box status-purple">'
                        f'🚛 <strong>{len(ctes)}</strong> CT-e(s) identificados e '
                        f'separados em <code>CTE.zip</code>.</div>',
                        unsafe_allow_html=True)
            df_tab(pd.DataFrame(ctes))

    with tabs[2]:
        if not enc:
            st.markdown('<div class="status-box status-warning">'
                        '⚠️ Nenhum XML encontrado.</div>', unsafe_allow_html=True)
        else:
            df_tab(pd.DataFrame(enc))

    with tabs[3]:
        if not nao:
            st.markdown('<div class="status-box status-success">'
                        '✅ Todos encontrados!</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box status-error">'
                        f'❌ {len(nao)} chave(s) sem XML correspondente.</div>',
                        unsafe_allow_html=True)
            df_tab(pd.DataFrame(nao))

    with tabs[4]:
        resumo_sem = (df_sem.groupby(["CFOP", "CATEGORIA"])
                      .size().reset_index(name="QUANTIDADE")
                      .sort_values("QUANTIDADE", ascending=False))
        st.markdown(f'<div class="status-box status-warning">'
                    f'🔍 {len(df_sem)} registros sem CHAVE_NFE na planilha.</div>',
                    unsafe_allow_html=True)
        df_tab(resumo_sem)

    with tabs[5]:
        indice = resultado.get("indice_xml", {})
        st.markdown(f'<div class="status-box status-info">'
                    f'🗂️ <strong>{len(indice)}</strong> XMLs indexados pela chave interna.</div>',
                    unsafe_allow_html=True)
        if indice:
            df_idx = pd.DataFrame([
                {"CHAVE": k, "ARQUIVO": v.name} for k, v in indice.items()
            ])
            df_tab(df_idx)

    # ── Downloads ───────────────────────────────────────────
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
            for k in ["etapa","planilha_bytes","xml_bytes","xml_tipo",
                      "xml_nomes","dict_conflito","decisoes","resultado","df_preview"]:
                if k == "etapa":
                    st.session_state[k] = 1
                elif k in ["dict_conflito","decisoes"]:
                    st.session_state[k] = {}
                elif k == "xml_nomes":
                    st.session_state[k] = []
                else:
                    st.session_state[k] = None
            st.rerun()

# ── Footer ──────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  Classificador XML NF-e / CT-e · Streamlit · Tema Thomson Reuters / Domínio Sistemas
</div>""", unsafe_allow_html=True)
