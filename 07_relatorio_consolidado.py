"""
PASSO 7 — RELATÓRIO CONSOLIDADO (Excel)

Junta features_consumo.csv + perfil_demanda_kmeans.csv numa única planilha,
ordenada por urgência (menor dias_cobertura primeiro), com cor por faixa de
risco. Os limiares de dias de cobertura abaixo (30 / 90) são um PONTO DE
PARTIDA — ajuste depois de conversar com o gestor da farmácia sobre o que
é "crítico" na prática (ex: pode depender do prazo médio de licitação real).

Uso:
    pip install openpyxl
    python 07_relatorio_consolidado.py
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

LIMIAR_CRITICO_DIAS = 30
LIMIAR_ATENCAO_DIAS = 90

COR_CRITICO = "FFC7CE"   # vermelho claro
COR_ATENCAO = "FFEB9C"   # amarelo claro
COR_OK = "C6EFCE"        # verde claro
COR_SEM_DADO = "D9D9D9"  # cinza


def classificar_risco(dias):
    if pd.isna(dias):
        return "Amostra insuficiente"
    if dias < LIMIAR_CRITICO_DIAS:
        return "Crítico"
    if dias < LIMIAR_ATENCAO_DIAS:
        return "Atenção"
    return "Confortável"


def montar_relatorio():
    features = pd.read_csv("features_consumo.csv")
    perfil = pd.read_csv("perfil_demanda_kmeans.csv")

    chave = ["unidade_saude", "categoria_estoque", "medicamento"]
    df = features.merge(
        perfil[chave + ["perfil_demanda"]], on=chave, how="left"
    )
    df["perfil_demanda"] = df["perfil_demanda"].fillna("Sem consumo válido")
    df["classificacao_risco"] = df["dias_cobertura_estimados"].apply(classificar_risco)

    ordem_risco = {"Crítico": 0, "Atenção": 1, "Confortável": 2, "Amostra insuficiente": 3}
    df["_ordem"] = df["classificacao_risco"].map(ordem_risco)
    df = df.sort_values(["_ordem", "dias_cobertura_estimados"], na_position="last").drop(columns="_ordem")

    colunas_finais = [
        "classificacao_risco", "unidade_saude", "medicamento", "categoria_estoque",
        "estoque_atual", "consumo_medio_por_quinzena", "coeficiente_variacao",
        "dias_cobertura_estimados", "perfil_demanda", "n_quinzenas_observadas",
        "n_intervalos_consumo_valido",
    ]
    df = df[colunas_finais]

    wb = Workbook()
    ws = wb.active
    ws.title = "Painel de Risco"

    cabecalhos = [
        "Risco", "Unidade", "Medicamento", "Categoria de Estoque", "Estoque Atual",
        "Consumo Médio/Quinzena", "Coef. Variação", "Dias de Cobertura (est.)",
        "Perfil de Demanda (K-Means)", "Quinzenas Observadas", "Intervalos de Consumo Válidos",
    ]
    ws.append(cabecalhos)
    for col_idx in range(1, len(cabecalhos) + 1):
        celula = ws.cell(row=1, column=col_idx)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", start_color="404040")
        celula.alignment = Alignment(horizontal="center")

    cor_por_risco = {
        "Crítico": COR_CRITICO,
        "Atenção": COR_ATENCAO,
        "Confortável": COR_OK,
        "Amostra insuficiente": COR_SEM_DADO,
    }

    for _, linha in df.iterrows():
        ws.append(list(linha))
        cor = cor_por_risco.get(linha["classificacao_risco"], None)
        if cor:
            linha_idx = ws.max_row
            for col_idx in range(1, len(cabecalhos) + 1):
                ws.cell(row=linha_idx, column=col_idx).fill = PatternFill("solid", start_color=cor)

    larguras = [20, 14, 42, 22, 14, 20, 14, 20, 22, 18, 24]
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura

    ws.freeze_panes = "A2"

    # Aba resumo
    ws2 = wb.create_sheet("Resumo")
    contagem = df["classificacao_risco"].value_counts()
    ws2.append(["Classificação", "Nº de itens"])
    ws2.cell(row=1, column=1).font = Font(bold=True)
    ws2.cell(row=1, column=2).font = Font(bold=True)
    for nome, qtd in contagem.items():
        ws2.append([nome, int(qtd)])
    ws2.column_dimensions["A"].width = 24
    ws2.column_dimensions["B"].width = 14

    wb.save("painel_risco_estoque.xlsx")
    print("Gerado: painel_risco_estoque.xlsx")
    print("\nResumo:")
    print(contagem.to_string())


if __name__ == "__main__":
    montar_relatorio()