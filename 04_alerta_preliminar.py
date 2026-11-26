"""
PASSO 4 — LISTA PRELIMINAR DE RISCO (a partir de UMA ÚNICA QUINZENA)

IMPORTANTE — o que isso NÃO é: isto não é o K-Means de perfil de demanda
nem o critério de Wald/Savage do seu anteprojeto. Aquilo exige série
temporal (consumo ao longo do tempo). Isto aqui é um "chute inicial"
baseado só no estoque atual, útil para:
  (a) já gerar algo concreto para mostrar ao orientador,
  (b) começar a validação qualitativa com o gestor da farmácia
      (perguntar: "esses itens fazem sentido como preocupação?").

Lógica: dentro de cada UNIDADE DE MEDIDA (comprimido, frasco ampola, grama...)
calculamos o percentil de cada item. Itens no percentil mais baixo daquele
grupo entram na lista — isso evita comparar "1 frasco ampola" com
"1000 gramas" como se fossem a mesma escala.

Uso:
    python 04_alerta_preliminar.py
"""
import sqlite3
import pandas as pd

DB_PATH = "estoque.db"
PERCENTIL_CORTE = 0.10  # 10% menores estoques dentro de cada grupo de unidade de medida


def gerar_lista_preliminar():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM estoque_quinzenal", con)
    con.close()

    df["percentil_no_grupo"] = df.groupby("unidade_medida")["quantidade_estoque"] \
        .rank(pct=True)

    candidatos = df[df["percentil_no_grupo"] <= PERCENTIL_CORTE].copy()
    candidatos = candidatos.sort_values(["unidade_medida", "quantidade_estoque"])

    colunas = ["unidade_saude", "categoria_estoque", "medicamento",
               "unidade_medida", "quantidade_estoque", "data_referencia"]
    candidatos[colunas].to_csv("lista_preliminar_validacao.csv", index=False)

    print(f"Total de itens: {len(df)}")
    print(f"Candidatos (menores {int(PERCENTIL_CORTE*100)}% dentro do próprio grupo de unidade de medida): {len(candidatos)}")
    print("\nSalvo em lista_preliminar_validacao.csv — leve essa lista para a"
          " conversa com o responsável pelo estoque e pergunte se os itens"
          " fazem sentido como preocupação real.")
    print("\nAmostra:")
    print(candidatos[colunas].head(15).to_string(index=False))


if __name__ == "__main__":
    gerar_lista_preliminar()