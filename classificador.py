import os
import shutil
import zipfile
import pandas as pd
import io
from pathlib import Path
from datetime import datetime

# ============================================================
# MAPEAMENTO DE CFOP → CATEGORIA
# ============================================================

CATEGORIAS = {
    "Compras":              [1101,1102,1111,1113,1116,1117,1118,1120,1121,1122,1123,1124,1125,
                             1126,1128,1131,1201,1202,1203,1204,1207,1208,1209,1251,1252,1253,
                             1254,1255,1256,1257,1258,2101,2102,2111,2113,2116,2117,2118,2120,
                             2121,2122,2123,2124,2125,2126,2128,2131,2201,2202,2203,2204,2207,
                             2208,2209,2251,2252,2253,2254,2255,2256,2257,2258],
    "Devoluções":           [1201,1202,1203,1204,1207,1208,1209,1302,1303,1304,1305,1306,
                             2201,2202,2203,2204,2207,2208,2209,2302,2303,2304,2305,2306],
    "Transferências":       [1151,1152,1153,1154,1155,1156,1157,1158,1159,
                             2151,2152,2153,2154,2155,2156,2157,2158,2159],
    "Serviços":             [1301,1302,1303,1304,1305,1306,1351,1352,1353,1354,1355,1356,
                             2301,2302,2303,2304,2305,2306,2351,2352,2353,2354,2355,2356],
    "Ativo Imobilizado":    [1551,1552,1553,1554,1555,1556,1557,
                             2551,2552,2553,2554,2555,2556,2557],
    "Uso e Consumo":        [1401,1403,1406,1407,1408,1409,
                             2401,2403,2406,2407,2408,2409],
    "Outros":               [1601,1602,1603,1604,1605,
                             2601,2602,2603,2604,2605,
                             1900,1901,1902,1903,1904,1905,1906,1907,1908,1909,
                             1910,1911,1912,1913,1914,1915,1916,1917,1918,1919,
                             1920,1921,1922,1923,1924,1925,1926,1927,1928,1929,
                             1930,1931,1932,1933,1934,1935,1936,1937,1938,1939,
                             1940,1941,1942,1943,1944,1945,1946,1947,1948,1949,
                             2900,2901,2902,2903,2904,2905,2906,2907,2908,2909,
                             2910,2911,2912,2913,2914,2915,2916,2917,2918,2919,
                             2920,2921,2922,2923,2924,2925,2926,2927,2928,2929,
                             2930,2931,2932,2933,2934,2935,2936,2937,2938,2939,
                             2940,2941,2942,2943,2944,2945,2946,2947,2948,2949,
                             1651,1652,1653,1654,1655,1656,
                             2651,2652,2653,2654,2655,2656],
}

# Índice invertido: cfop → categoria
_CFOP_INDEX = {}
for cat, lista in CATEGORIAS.items():
    for c in lista:
        _CFOP_INDEX[c] = cat


def cfop_para_categoria(cfop_str: str) -> str:
    try:
        cfop = int(str(cfop_str).strip())
        return _CFOP_INDEX.get(cfop, "Outros")
    except Exception:
        return "Outros"


# ============================================================
# INDEXAR XMLs (chave → caminho do arquivo)
# ============================================================

def indexar_xmls(pasta_xmls: str) -> dict:
    """Percorre recursivamente e mapeia chave NF-e → caminho do XML."""
    import xml.etree.ElementTree as ET
    index = {}
    for root_dir, _, files in os.walk(pasta_xmls):
        for fname in files:
            if not fname.lower().endswith(".xml"):
                continue
            fpath = os.path.join(root_dir, fname)
            try:
                tree = ET.parse(fpath)
                root_el = tree.getroot()
                ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
                # Tenta pegar chave pelo atributo Id da infNFe
                inf = root_el.find(".//{http://www.portalfiscal.inf.br/nfe}infNFe")
                if inf is not None:
                    chave = inf.get("Id", "").replace("NFe", "")
                    if chave:
                        index[chave] = fpath
                        continue
                # Fallback: nome do arquivo sem extensão (44 dígitos)
                nome_sem_ext = os.path.splitext(fname)[0]
                if len(nome_sem_ext) == 44 and nome_sem_ext.isdigit():
                    index[nome_sem_ext] = fpath
            except Exception:
                nome_sem_ext = os.path.splitext(fname)[0]
                if len(nome_sem_ext) == 44 and nome_sem_ext.isdigit():
                    index[nome_sem_ext] = fpath
    return index


# ============================================================
# ANALISAR DUPLICATAS
# ============================================================

def analisar_duplicatas(df_com_chave: pd.DataFrame):
    """
    Retorna:
        df_auto     — chaves únicas por categoria (sem conflito)
        df_conflito — chaves que aparecem em categorias diferentes
        dict_conf   — {chave: [{cfop, categoria}, ...]}
    """
    grupos = df_com_chave.groupby("CHAVE_NFE")["CATEGORIA"].nunique()
    chaves_conf = set(grupos[grupos > 1].index)

    df_auto     = df_com_chave[~df_com_chave["CHAVE_NFE"].isin(chaves_conf)].copy()
    df_conflito = df_com_chave[ df_com_chave["CHAVE_NFE"].isin(chaves_conf)].copy()

    dict_conf = {}
    for chave, grp in df_conflito.groupby("CHAVE_NFE"):
        opcoes = []
        for _, row in grp.drop_duplicates(["CFOP","CATEGORIA"]).iterrows():
            opcoes.append({"cfop": row["CFOP"], "categoria": row["CATEGORIA"]})
        dict_conf[chave] = opcoes

    return df_auto, df_conflito, dict_conf


# ============================================================
# CLASSIFICAR XMLs — FUNÇÃO PRINCIPAL
# ============================================================

def classificar_xmls(
    caminho_planilha:    str,
    caminho_xmls_ou_zip: str,
    pasta_output:        str,
    decisoes_usuario:    dict = None,
) -> dict:
    """
    Classifica XMLs em pastas por categoria fiscal.

    Retorna dict com:
        df_planilha, df_com_chave, df_sem_chave,
        df_auto, df_conflito, dict_conflito,
        encontrados, nao_encontrados,
        zip (caminho), relatorio (caminho)
    """
    if decisoes_usuario is None:
        decisoes_usuario = {}

    # 1. Ler planilha
    df = pd.read_excel(caminho_planilha, sheet_name="Planilha1", dtype=str)
    df.columns = ["CFOP", "CHAVE_NFE"]
    df["CFOP"]      = df["CFOP"].str.strip()
    df["CHAVE_NFE"] = df["CHAVE_NFE"].str.strip()
    df["CATEGORIA"] = df["CFOP"].apply(cfop_para_categoria)

    df_com = df[df["CHAVE_NFE"].notna() & (df["CHAVE_NFE"] != "nan")].copy()
    df_sem = df[df["CHAVE_NFE"].isna()  | (df["CHAVE_NFE"] == "nan")].copy()

    # 2. Separar conflitos / automáticos
    df_auto, df_conflito, dict_conf = analisar_duplicatas(df_com)

    # 3. Indexar XMLs
    index_xml = indexar_xmls(caminho_xmls_ou_zip)

    # 4. Criar estrutura de pastas de saída
    pasta_out = Path(pasta_output)
    pasta_out.mkdir(parents=True, exist_ok=True)

    encontrados     = []
    nao_encontrados = []

    def copiar_xml(chave, categoria):
        dest_dir = pasta_out / categoria
        dest_dir.mkdir(parents=True, exist_ok=True)
        if chave in index_xml:
            src  = index_xml[chave]
            dest = dest_dir / os.path.basename(src)
            shutil.copy2(src, dest)
            encontrados.append({"CHAVE_NFE": chave, "CATEGORIA": categoria,
                                 "ARQUIVO": os.path.basename(src)})
        else:
            nao_encontrados.append({"CHAVE_NFE": chave, "CATEGORIA": categoria})

    # 5. Processar automáticos (sem conflito) — uma cópia por chave por categoria
    for chave, grp in df_auto.groupby("CHAVE_NFE"):
        for cat in grp["CATEGORIA"].unique():
            copiar_xml(chave, cat)

    # 6. Processar conflitos conforme decisão do usuário
    for chave, opcoes in dict_conf.items():
        cats_disponiveis = list({o["categoria"] for o in opcoes})
        cats_escolhidas  = decisoes_usuario.get(chave, cats_disponiveis)
        for cat in cats_escolhidas:
            copiar_xml(chave, cat)

    # 7. Gerar ZIP de saída
    zip_path = str(pasta_out.parent / "Classificados.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in pasta_out.rglob("*"):
            if fpath.is_file():
                zf.write(fpath, fpath.relative_to(pasta_out.parent))

    # 8. Gerar relatório Excel
    rel_path = str(pasta_out.parent / "Relatorio.xlsx")
    with pd.ExcelWriter(rel_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Planilha Completa", index=False)
        pd.DataFrame(encontrados).to_excel(writer, sheet_name="Encontrados", index=False)
        pd.DataFrame(nao_encontrados).to_excel(writer, sheet_name="Não Encontrados", index=False)
        df_sem.to_excel(writer, sheet_name="Sem Chave", index=False)

    return {
        "df_planilha":   df,
        "df_com_chave":  df_com,
        "df_sem_chave":  df_sem,
        "df_auto":       df_auto,
        "df_conflito":   df_conflito,
        "dict_conflito": dict_conf,
        "encontrados":   encontrados,
        "nao_encontrados": nao_encontrados,
        "zip":           zip_path,
        "relatorio":     rel_path,
    }
