"""
PASSO 5 — FEATURES DE CONSUMO A PARTIR DA SÉRIE TEMPORAL

Regra central: a diferença de estoque entre duas quinzenas consecutivas
NÃO é consumo puro.
  - Se o estoque CAIU (delta negativo)  -> assumimos consumo = -delta
    nesse intervalo (nenhuma reposição no meio).
  - Se o estoque SUBIU (delta positivo) -> houve reposição (execução de
    Ata) nesse intervalo. O consumo real nesse intervalo específico fica
    "censurado" (não sabemos quanto foi consumido antes da reposição
    chegar), então NÃO contamos esse intervalo como amostra de consumo.

Isso é uma limitação conhecida e deve ser citada como tal na sua
dissertação (seção de limitações do método) — o ideal seria ter o dado
de dispensação direta, se existir uma fonte separada disso. Na ausência
dela, este é o proxy possível a partir dos relatórios de posição de
estoque.

Saída: features_consumo.csv, uma linha por (unidade, categoria, medicamento):
  - n_quinzenas_observadas
  - n_intervalos_consumo_valido  (intervalos sem reposição no meio)
  - consumo_medio_por_quinzena
  - desvio_padrao_consumo
  - coeficiente_variacao   (desvio / média -> mede volatilidade da demanda)
  - estoque_atual
  - dias_cobertura_estimados  (estoque_atual / consumo_medio_diário)

Uso:
    python 05_features_consumo.py
"""
import sqlite3
import numpy as np
import pandas as pd

DB_PATH = "estoque.db"
DIAS_POR_QUINZENA = 15


def calcular_features(caminho_db: str = DB_PATH) -> pd.DataFrame:
    con = sqlite3.connect(caminho_db)
    df = pd.read_sql("SELECT * FROM estoque_quinzenal", con)
    con.close()

    df["data_referencia"] = pd.to_datetime(df["data_referencia"])
    df = df.sort_values(["unidade_saude", "categoria_estoque", "medicamento", "data_referencia"])

    grupo_cols = ["unidade_saude", "categoria_estoque", "medicamento"]
    linhas_features = []

    for chave, grupo in df.groupby(grupo_cols):
        grupo = grupo.drop_duplicates(subset="data_referencia").sort_values("data_referencia")
        estoques = grupo["quantidade_estoque"].to_numpy()
        n_quinzenas = len(estoques)

        if n_quinzenas < 2:
            continue  # sem par de datas não dá pra estimar consumo

        deltas = np.diff(estoques)
        consumos_validos = -deltas[deltas < 0]  # só intervalos onde o estoque caiu

        n_validos = len(consumos_validos)
        consumo_medio = float(np.mean(consumos_validos)) if n_validos > 0 else 0.0
        desvio = float(np.std(consumos_validos)) if n_validos > 1 else 0.0
        coef_var = (desvio / consumo_medio) if consumo_medio > 0 else np.nan

        estoque_atual = float(estoques[-1])
        consumo_diario = consumo_medio / DIAS_POR_QUINZENA if consumo_medio > 0 else np.nan
        dias_cobertura = (estoque_atual / consumo_diario) if consumo_diario and consumo_diario > 0 else np.nan

        unidade_saude, categoria_estoque, medicamento = chave
        linhas_features.append({
            "unidade_saude": unidade_saude,
            "categoria_estoque": categoria_estoque,
            "medicamento": medicamento,
            "n_quinzenas_observadas": n_quinzenas,
            "n_intervalos_consumo_valido": n_validos,
            "consumo_medio_por_quinzena": round(consumo_medio, 2),
            "desvio_padrao_consumo": round(desvio, 2),
            "coeficiente_variacao": round(coef_var, 3) if not np.isnan(coef_var) else None,
            "estoque_atual": estoque_atual,
            "dias_cobertura_estimados": round(dias_cobertura, 1) if not np.isnan(dias_cobertura) else None,
        })

    resultado = pd.DataFrame(linhas_features)
    resultado.to_csv("features_consumo.csv", index=False)
    return resultado


if __name__ == "__main__":
    resultado = calcular_features()
    print(f"Itens com série temporal suficiente (>=2 quinzenas): {len(resultado)}")

    sem_consumo_valido = (resultado["n_intervalos_consumo_valido"] == 0).sum()
    print(f"Itens sem NENHUM intervalo de consumo válido (só reposição/estável): {sem_consumo_valido}")
    print("  -> esses ficam sem dias_cobertura_estimados; revisar manualmente ou aguardar mais quinzenas.\n")

    print("Amostra ordenada por menor cobertura estimada (mais urgente primeiro):")
    amostra = resultado.dropna(subset=["dias_cobertura_estimados"]).nsmallest(15, "dias_cobertura_estimados")
    print(amostra[["unidade_saude", "medicamento", "estoque_atual",
                    "consumo_medio_por_quinzena", "dias_cobertura_estimados"]].to_string(index=False))