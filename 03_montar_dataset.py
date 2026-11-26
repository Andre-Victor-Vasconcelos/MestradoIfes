"""
PASSO 3 — CONSOLIDAÇÃO EM BASE ANALÍTICA

Lê os JSONs brutos de raw_json/, limpa, normaliza nomes de medicamento
(fuzzy match contra uma lista de referência REMEME) e grava:

  1. estoque.db (SQLite)      -> fonte da verdade, consultável, auditável
  2. dataset_kmeans.csv        -> uma linha por (unidade, medicamento, data),
                                   pronta para feature engineering / K-Means
  3. alertas_input.json        -> estrutura resumida por item, pronta para
                                   virar prompt de um LLM (texto do alerta)

Uso:
    python 03_montar_dataset.py
"""
import json
import re
import sqlite3
from pathlib import Path
import pandas as pd
from rapidfuzz import process, fuzz

PASTA_RAW = Path("raw_json")
DB_PATH = Path("estoque.db")

# Lista de referência REMEME — SUBSTITUA pela lista oficial completa da SESA.
# Se você não tiver essa lista ainda em mãos, pule a normalização por ora
# (o script funciona sem ela, só não vai corrigir grafias inconsistentes
# entre unidades/datas) e trate isso depois como um refinamento.
REMEME_REFERENCIA = []


def parse_quantidade(valor: str):
    """Converte string de quantidade em número, tolerando formatos com ponto/vírgula."""
    if valor is None:
        return None
    limpo = re.sub(r"[^\d,.\-]", "", str(valor)).replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def normalizar_nome_medicamento(nome_bruto: str, limiar: int = 85):
    """Faz fuzzy match do nome extraído contra a lista oficial REMEME."""
    if not nome_bruto:
        return None, 0
    nome_limpo = re.sub(r"\s+", " ", nome_bruto.upper().strip())
    if not REMEME_REFERENCIA:
        # Sem lista de referência ainda: mantém o nome limpo, sem score de match
        return nome_limpo, None
    match = process.extractOne(nome_limpo, REMEME_REFERENCIA, scorer=fuzz.WRatio)
    if match and match[1] >= limiar:
        return match[0], match[1]
    return nome_limpo, match[1] if match else 0  # mantém original + score baixo p/ QA


def carregar_raw() -> pd.DataFrame:
    registros = []
    for caminho_json in sorted(PASTA_RAW.glob("*.json")):
        dado = json.loads(caminho_json.read_text())
        unidade = dado.get("unidade_bruta")
        data_ref = dado.get("data_referencia")
        for item in dado.get("linhas", []):
            linha = item["linha"]
            # Layout observado nos relatórios SESA/FCC:
            # [DS_ESTOQUE, DS_PRODUTO, DS_UNIDADE (medida), QT_ATUAL]
            if len(linha) < 4:
                continue
            categoria_estoque, nome_med_bruto, unidade_medida, qtd_bruta = linha[:4]
            registros.append({
                "arquivo_origem": dado["arquivo_origem"],
                "unidade_saude": unidade,
                "data_referencia": data_ref,
                "categoria_estoque": categoria_estoque,
                "medicamento_bruto": nome_med_bruto,
                "unidade_medida": unidade_medida,
                "quantidade_estoque": parse_quantidade(qtd_bruta),
            })
    return pd.DataFrame(registros)


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    resultados = df["medicamento_bruto"].apply(normalizar_nome_medicamento)
    df["medicamento"] = resultados.apply(lambda t: t[0])
    df["score_match_nome"] = resultados.apply(lambda t: t[1])
    # Sinaliza para revisão manual os matches fracos (< 85) — parte do QA técnico
    df["revisar_manualmente"] = df["score_match_nome"].apply(lambda s: (s is not None) and s < 85)
    return df


def gravar_sqlite(df: pd.DataFrame):
    con = sqlite3.connect(DB_PATH)
    df.to_sql("estoque_quinzenal", con, if_exists="replace", index=False)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_unidade_med_data
        ON estoque_quinzenal (unidade_saude, medicamento, data_referencia)
    """)
    con.commit()
    con.close()
    print(f"Gravado em {DB_PATH} (tabela estoque_quinzenal, {len(df)} linhas)")


def exportar_para_kmeans(df: pd.DataFrame):
    """
    Uma linha por (unidade, medicamento, data) é o grão certo para depois
    agregar por medicamento e calcular features como:
    consumo médio, desvio padrão, tendência — que alimentam o K-Means.
    """
    df.to_csv("dataset_kmeans.csv", index=False, encoding="utf-8")
    print("Exportado dataset_kmeans.csv (grão: unidade x medicamento x quinzena)")


def exportar_para_alertas_llm(df: pd.DataFrame):
    """
    Estrutura resumida por medicamento+unidade: só o necessário para um LLM
    redigir o texto do alerta. Note que NÃO mandamos o dataset inteiro —
    mandamos o resultado já calculado (última leitura + score de QA).
    """
    # IMPORTANTE: um mesmo medicamento pode existir em mais de uma
    # categoria de estoque na mesma unidade (ex.: "FCC - PADRONIZADOS" e
    # "FCC - PADRONIZADO ESP 1A" com saldos DIFERENTES) — descoberto ao
    # testar contra um relatório real. Por isso a chave inclui categoria.
    resumo = (
        df.sort_values("data_referencia")
        .groupby(["unidade_saude", "categoria_estoque", "medicamento"])
        .tail(1)[["unidade_saude", "categoria_estoque", "medicamento", "data_referencia",
                   "quantidade_estoque", "revisar_manualmente"]]
    )
    registros = resumo.to_dict(orient="records")
    Path("alertas_input.json").write_text(json.dumps(registros, ensure_ascii=False, indent=2))
    print(f"Exportado alertas_input.json ({len(registros)} itens)")


if __name__ == "__main__":
    df = carregar_raw()
    if df.empty:
        print("Nenhum dado encontrado em raw_json/. Rode o passo 2 primeiro.")
        raise SystemExit(1)

    df = normalizar(df)
    gravar_sqlite(df)
    exportar_para_kmeans(df)
    exportar_para_alertas_llm(df)

    print("\nAmostra do dataset final:")
    print(df.head())
