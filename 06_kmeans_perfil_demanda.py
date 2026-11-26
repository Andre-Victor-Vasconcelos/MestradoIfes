"""
PASSO 6 — K-MEANS: PERFIL DE DEMANDA

Segmenta os medicamentos em clusters a partir de duas dimensões:
  - nível de consumo (log do consumo médio por quinzena)
  - volatilidade da demanda (coeficiente de variação)

Por que log no consumo: os volumes variam em ordens de grandeza diferentes
(de 1 unidade a milhares de gramas/doses) — sem log, o K-Means (que usa
distância euclidiana) ignora os itens de baixo volume, por mais críticos
que sejam clinicamente.

Os clusters não vêm com rótulo de negócio automático — o script ordena os
clusters pelo consumo médio e nomeia como Baixo/Médio/Alto, mas a
INTERPRETAÇÃO clínica de cada cluster (ex: "grupo de alto custo e baixa
volatilidade" vs "grupo essencial de alta rotatividade") é analítica sua,
e é justamente o tipo de achado que entra na dissertação.

Requer: pip install scikit-learn

Uso:
    python 06_kmeans_perfil_demanda.py
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

N_CLUSTERS = 3


def rodar_kmeans():
    df = pd.read_csv("features_consumo.csv")

    # Só entram no clustering itens com pelo menos 1 intervalo de consumo válido
    # (sem isso, consumo_medio = 0 artificialmente, o que distorceria o cluster)
    df_valido = df[df["n_intervalos_consumo_valido"] > 0].copy()
    excluidos = len(df) - len(df_valido)

    df_valido["log_consumo"] = np.log1p(df_valido["consumo_medio_por_quinzena"])
    df_valido["coef_variacao_preenchido"] = df_valido["coeficiente_variacao"].fillna(0)

    X = df_valido[["log_consumo", "coef_variacao_preenchido"]].to_numpy()
    X_scaled = StandardScaler().fit_transform(X)

    modelo = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    df_valido["cluster_bruto"] = modelo.fit_predict(X_scaled)

    score = silhouette_score(X_scaled, df_valido["cluster_bruto"])

    # Renomeia clusters por nível médio de consumo (0 = menor, N-1 = maior)
    ordem = df_valido.groupby("cluster_bruto")["consumo_medio_por_quinzena"].mean().sort_values().index
    nomes = ["Baixo consumo", "Médio consumo", "Alto consumo"][:N_CLUSTERS]
    mapa_nomes = {cluster_id: nomes[i] for i, cluster_id in enumerate(ordem)}
    df_valido["perfil_demanda"] = df_valido["cluster_bruto"].map(mapa_nomes)

    colunas_saida = ["unidade_saude", "categoria_estoque", "medicamento",
                      "consumo_medio_por_quinzena", "coeficiente_variacao",
                      "dias_cobertura_estimados", "perfil_demanda"]
    df_valido[colunas_saida].to_csv("perfil_demanda_kmeans.csv", index=False)

    print(f"Itens no clustering: {len(df_valido)} (excluídos por falta de consumo válido: {excluidos})")
    print(f"Silhouette score: {score:.3f}  "
          f"(> 0.5 = clusters bem separados; 0.25-0.5 = razoável; < 0.25 = fraco, considere revisar)")
    print()
    print("Distribuição por perfil:")
    print(df_valido["perfil_demanda"].value_counts())
    print()
    print("Amostra por perfil:")
    for nome in nomes:
        print(f"\n--- {nome} ---")
        amostra = df_valido[df_valido["perfil_demanda"] == nome].nlargest(5, "consumo_medio_por_quinzena")
        print(amostra[["medicamento", "consumo_medio_por_quinzena", "coeficiente_variacao", "dias_cobertura_estimados"]].to_string(index=False))


if __name__ == "__main__":
    rodar_kmeans()