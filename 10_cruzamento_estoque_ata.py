"""
PASSO 10 — CRUZAMENTO ESTOQUE x ATA (lógica Confortável/Crítico/Operacional)

Junta:
  - features_consumo.csv       (script 5: dias de cobertura estimados)
  - atas_vigentes.csv          (script 8: vigência das Atas)
  - processos_andamento.csv    (script 9: novas licitações em curso,
                                 já traz "ordem_maturidade" 0-7, com -1 para
                                 processo FRACASSADO)

O nome do medicamento é escrito de forma diferente no relatório de estoque
("ATORVASTATINA 40MG CPR") e na tabela de Atas ("ATORVASTATINA 40MG
COMPRIMIDO"), então o cruzamento usa fuzzy matching (rapidfuzz), não match
exato. Isso significa que cada correspondência tem um SCORE — scores baixos
(< 80) devem ser revisados manualmente antes de confiar na classificação.

Classificação final (LIMIARES SÃO PONTO DE PARTIDA — ajustar com o gestor):
  - Amostra insuficiente:               não há histórico de consumo suficiente
  - Crítico - SEM AÇÃO EM ANDAMENTO:    estoque baixo, nenhuma Ata vigente E
                                         nenhum processo de compra encontrado
                                         -> maior prioridade, ninguém está
                                         cuidando disso ainda
  - Crítico - processo fracassado:      estoque baixo, sem Ata, e o único
                                         processo encontrado foi FRACASSADO
                                         (precisa reabrir) -> mesma urgência
                                         do item acima, mas com contexto
  - Crítico - processo em fase avançada:estoque baixo, sem Ata, mas já existe
                                         processo perto de virar Ata -> ainda
                                         crítico, porém já endereçado
  - Crítico - processo em fase inicial: estoque baixo, sem Ata, processo
                                         existe mas ainda no começo
  - Operacional (com Ata):              estoque baixo MAS há Ata vigente com
                                         saldo de tempo -> disparar compra
  - Ata vencendo em breve:              estoque ok, mas a Ata vigente expira
                                         antes do próximo ciclo esperado
  - Atenção - sem Ata vigente / Atenção - Ata vigente / Confortável

A distinção acima (SEM AÇÃO / fracassado / fase avançada / fase inicial) só
é feita dentro do bucket "Crítico e sem Ata", que é o de maior prioridade
prática — é aí que mora a pergunta "isso já está sendo resolvido ou não?".

Uso:
    python 10_cruzamento_estoque_ata.py
"""
from datetime import date
import pandas as pd
from rapidfuzz import process, fuzz
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

LIMIAR_CRITICO_DIAS = 30
LIMIAR_ATENCAO_DIAS = 90
LIMIAR_ATA_VENCENDO_DIAS = 60   # se a ata vence em menos que isso, sinaliza
SCORE_MINIMO_MATCH = 78

# A partir de qual "ordem_maturidade" (script 09) um processo em andamento já
# é considerado avançado o bastante para não ser mais um ponto cego total.
# Ponto de partida: 5 = HOMOLOGAÇÃO em diante (fornecedor já definido, falta
# formalizar). Ajustar depois de validar com o gestor da farmácia.
LIMIAR_ORDEM_AVANCADA = 3


def carregar_dados():
    features = pd.read_csv("features_consumo.csv")
    atas = pd.read_csv("atas_vigentes.csv", parse_dates=["publicada_em", "vigencia_fim"])
    processos = pd.read_csv("processos_andamento.csv")
    return features, atas, processos


import re


def extrair_doses(texto):
    """Extrai números com unidade (mg, mcg, ml, ui, g) do nome do medicamento.
    Usado para IMPEDIR que o fuzzy match aprove itens de mesma substância
    mas dosagem diferente (ex: RISPERIDONA 1MG vs RISPERIDONA 2MG)."""
    if not texto:
        return set()
    return set(re.findall(r"\d+[.,]?\d*\s?(?:MG|MCG|ML|UI|G)\b", texto.upper()))


def doses_compativeis(nome_a, nome_b):
    doses_a, doses_b = extrair_doses(nome_a), extrair_doses(nome_b)
    if not doses_a or not doses_b:
        return True  # não dá pra checar, deixa passar (mas score ainda protege)
    return len(doses_a & doses_b) > 0


def melhor_match_ata(nome_medicamento, atas_descricoes):
    candidatos = process.extract(nome_medicamento, atas_descricoes, scorer=fuzz.token_sort_ratio, limit=5)
    for candidato, score, _ in candidatos:
        if score >= SCORE_MINIMO_MATCH and doses_compativeis(nome_medicamento, candidato):
            return candidato, score
    return None, (candidatos[0][1] if candidatos else 0)


def melhor_match_processo(nome_medicamento, processos_nomes):
    if not processos_nomes:
        return None, 0
    match = process.extractOne(nome_medicamento, processos_nomes, scorer=fuzz.token_sort_ratio)
    if match and match[1] >= SCORE_MINIMO_MATCH:
        return match[0], match[1]
    return None, (match[1] if match else 0)


def classificar(dias_cobertura, tem_ata, dias_restantes_ata, tem_processo, ordem_maturidade_processo):
    if pd.isna(dias_cobertura):
        return "Amostra insuficiente"

    if not tem_ata:
        if dias_cobertura >= LIMIAR_CRITICO_DIAS:
            return "Atenção - sem Ata vigente"
        # Bucket crítico sem Ata: aqui é onde importa saber se já existe
        # alguma ação de compra em curso ou se é um ponto cego total.
        if not tem_processo:
            return "Crítico - SEM AÇÃO EM ANDAMENTO"
        if ordem_maturidade_processo is not None and ordem_maturidade_processo < 0:
            return "Crítico - processo fracassado (precisa reabrir)"
        if ordem_maturidade_processo is not None and ordem_maturidade_processo >= LIMIAR_ORDEM_AVANCADA:
            return "Crítico - processo em fase avançada"
        return "Crítico - processo em fase inicial"

    # tem ata vigente
    if dias_restantes_ata is not None and dias_restantes_ata < LIMIAR_ATA_VENCENDO_DIAS and dias_cobertura > dias_restantes_ata:
        return "Ata vencendo em breve"
    if dias_cobertura < LIMIAR_CRITICO_DIAS:
        return "Operacional - disparar compra (Ata vigente)"
    if dias_cobertura < LIMIAR_ATENCAO_DIAS:
        return "Atenção - Ata vigente"
    return "Confortável"


def cruzar():
    features, atas, processos = carregar_dados()
    hoje = pd.Timestamp(date.today())

    atas_descricoes = atas["descricao_medicamento"].tolist()
    processos_nomes = processos["medicamento"].tolist()

    resultados = []
    for _, linha in features.iterrows():
        nome = linha["medicamento"]
        desc_match, score_ata = melhor_match_ata(nome, atas_descricoes)

        tem_ata = desc_match is not None
        vigencia_fim = fornecedor = numero_ata = None
        dias_restantes_ata = None
        if tem_ata:
            ata_linha = atas[atas["descricao_medicamento"] == desc_match].iloc[0]
            vigencia_fim = ata_linha["vigencia_fim"]
            fornecedor = ata_linha["fornecedor"]
            numero_ata = ata_linha["numero_ata"]
            dias_restantes_ata = (vigencia_fim - hoje).days

        proc_match, score_proc = melhor_match_processo(nome, processos_nomes) if not tem_ata else (None, 0)
        fase_processo = None
        ordem_maturidade_processo = None
        numero_processo = None
        if proc_match:
            proc_linha = processos[processos["medicamento"] == proc_match].iloc[0]
            fase_processo = proc_linha["fase_atual"]
            ordem_maturidade_processo = proc_linha.get("ordem_maturidade")
            if pd.notna(ordem_maturidade_processo):
                ordem_maturidade_processo = int(ordem_maturidade_processo)
            else:
                ordem_maturidade_processo = None
            numero_processo = proc_linha.get("numero_processo")

        classificacao = classificar(
            linha["dias_cobertura_estimados"], tem_ata, dias_restantes_ata,
            tem_processo=proc_match is not None,
            ordem_maturidade_processo=ordem_maturidade_processo,
        )

        resultados.append({
            "unidade_saude": linha["unidade_saude"],
            "categoria_estoque": linha.get("categoria_estoque"),
            "medicamento": nome,
            "estoque_atual": linha.get("estoque_atual"),
            "consumo_medio_por_quinzena": linha.get("consumo_medio_por_quinzena"),
            "dias_cobertura_estimados": linha["dias_cobertura_estimados"],
            "classificacao": classificacao,
            "tem_ata_vigente": tem_ata,
            "score_match_ata": score_ata,
            "ata_descricao_correspondente": desc_match,
            "numero_ata": numero_ata,
            "fornecedor": fornecedor,
            "vigencia_fim_ata": vigencia_fim.date().isoformat() if pd.notna(vigencia_fim) else None,
            "dias_restantes_ata": dias_restantes_ata,
            "processo_em_andamento": fase_processo,
            "numero_processo": numero_processo,
            "ordem_maturidade_processo": ordem_maturidade_processo,
            "revisar_match_manualmente": (tem_ata and score_ata < 90) or (proc_match and score_proc < 90),
        })

    df = pd.DataFrame(resultados)
    ordem = {
        "Crítico - SEM AÇÃO EM ANDAMENTO": 0,
        "Crítico - processo fracassado (precisa reabrir)": 1,
        "Crítico - processo em fase inicial": 2,
        "Crítico - processo em fase avançada": 3,
        "Operacional - disparar compra (Ata vigente)": 4,
        "Ata vencendo em breve": 5,
        "Atenção - sem Ata vigente": 6,
        "Atenção - Ata vigente": 7,
        "Confortável": 8,
        "Amostra insuficiente": 9,
    }
    df["_ordem"] = df["classificacao"].map(ordem)
    df = df.sort_values(["_ordem", "dias_cobertura_estimados"]).drop(columns="_ordem")
    df.to_csv("cruzamento_estoque_ata.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# RELATÓRIO ESTRUTURADO (Excel) — substitui a inspeção via terminal.
# Segue o mesmo padrão visual do script 07 (cor por faixa de risco, aba de
# resumo) e acrescenta uma aba dedicada só para o ponto cego real: itens
# críticos sem Ata E sem nenhum processo de compra em andamento.
# ---------------------------------------------------------------------------

COR_SEM_ACAO = "FF0000"        # vermelho forte — ninguém está cuidando
COR_FRACASSADO = "FFA07A"      # laranja-salmão — processo caiu, precisa reabrir
COR_FASE_INICIAL = "FFC7CE"    # vermelho claro
COR_FASE_AVANCADA = "FFEB9C"   # amarelo — crítico mas já encaminhado
COR_OPERACIONAL = "FFEB9C"     # amarelo
COR_ATA_VENCENDO = "FFEB9C"    # amarelo
COR_ATENCAO = "FFF2CC"         # amarelo claro
COR_OK = "C6EFCE"              # verde
COR_SEM_DADO = "D9D9D9"        # cinza

CORES_POR_CLASSIFICACAO = {
    "Crítico - SEM AÇÃO EM ANDAMENTO": COR_SEM_ACAO,
    "Crítico - processo fracassado (precisa reabrir)": COR_FRACASSADO,
    "Crítico - processo em fase inicial": COR_FASE_INICIAL,
    "Crítico - processo em fase avançada": COR_FASE_AVANCADA,
    "Operacional - disparar compra (Ata vigente)": COR_OPERACIONAL,
    "Ata vencendo em breve": COR_ATA_VENCENDO,
    "Atenção - sem Ata vigente": COR_ATENCAO,
    "Atenção - Ata vigente": COR_ATENCAO,
    "Confortável": COR_OK,
    "Amostra insuficiente": COR_SEM_DADO,
}

COLUNAS_RELATORIO = [
    "classificacao", "unidade_saude", "medicamento", "categoria_estoque",
    "estoque_atual", "consumo_medio_por_quinzena", "dias_cobertura_estimados",
    "tem_ata_vigente", "numero_ata", "fornecedor", "vigencia_fim_ata",
    "dias_restantes_ata", "processo_em_andamento", "numero_processo",
    "score_match_ata", "revisar_match_manualmente",
]

CABECALHOS_RELATORIO = [
    "Classificação", "Unidade", "Medicamento", "Categoria de Estoque",
    "Estoque Atual", "Consumo Médio/Quinzena", "Dias de Cobertura (est.)",
    "Tem Ata Vigente?", "Nº Ata", "Fornecedor", "Vigência da Ata (fim)",
    "Dias Restantes da Ata", "Processo em Andamento (fase)", "Nº Processo",
    "Score Match Ata", "Revisar Match Manualmente?",
]

LARGURAS_RELATORIO = [30, 12, 42, 22, 14, 20, 20, 14, 14, 28, 18, 18, 26, 16, 14, 20]


def _escrever_aba(ws, df_aba):
    ws.append(CABECALHOS_RELATORIO)
    for col_idx in range(1, len(CABECALHOS_RELATORIO) + 1):
        celula = ws.cell(row=1, column=col_idx)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", start_color="404040")
        celula.alignment = Alignment(horizontal="center")

    for _, linha in df_aba.iterrows():
        ws.append([linha[c] for c in COLUNAS_RELATORIO])
        cor = CORES_POR_CLASSIFICACAO.get(linha["classificacao"])
        if cor:
            linha_idx = ws.max_row
            for col_idx in range(1, len(CABECALHOS_RELATORIO) + 1):
                ws.cell(row=linha_idx, column=col_idx).fill = PatternFill("solid", start_color=cor)

    for i, largura in enumerate(LARGURAS_RELATORIO, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.freeze_panes = "A2"


def gerar_relatorio_excel(df, caminho="cruzamento_estoque_ata.xlsx"):
    wb = Workbook()

    ws_principal = wb.active
    ws_principal.title = "Cruzamento Estoque x Ata"
    _escrever_aba(ws_principal, df)

    # Aba dedicada: o ponto cego real — crítico, sem Ata, sem processo algum.
    # É a lista que deve ser levada ao gestor com mais urgência: ninguém está
    # cuidando desses itens ainda.
    df_urgente = df[df["classificacao"] == "Crítico - SEM AÇÃO EM ANDAMENTO"]
    ws_urgente = wb.create_sheet("Ação Urgente")
    if len(df_urgente) > 0:
        _escrever_aba(ws_urgente, df_urgente)
    else:
        ws_urgente.append(["Nenhum item crítico sem Ata e sem processo em andamento no momento."])

    # Aba resumo
    ws_resumo = wb.create_sheet("Resumo")
    contagem = df["classificacao"].value_counts()
    ws_resumo.append(["Classificação", "Nº de itens"])
    ws_resumo.cell(row=1, column=1).font = Font(bold=True)
    ws_resumo.cell(row=1, column=2).font = Font(bold=True)
    for nome_class, qtd in contagem.items():
        ws_resumo.append([nome_class, int(qtd)])
    ws_resumo.column_dimensions["A"].width = 42
    ws_resumo.column_dimensions["B"].width = 14

    wb.save(caminho)
    return df_urgente


if __name__ == "__main__":
    df = cruzar()
    df_urgente = gerar_relatorio_excel(df)

    print("Gerado: cruzamento_estoque_ata.csv")
    print("Gerado: cruzamento_estoque_ata.xlsx (abas: Cruzamento Estoque x Ata / Ação Urgente / Resumo)")
    print(f"\nTotal de itens cruzados: {len(df)}")
    print(f"Sem Ata vigente encontrada (via fuzzy match): {(~df['tem_ata_vigente']).sum()}")
    print(f"Matches com score < 90 (revisar manualmente): {df['revisar_match_manualmente'].sum()}")
    print(f"\n>>> CRÍTICOS SEM AÇÃO EM ANDAMENTO (sem Ata e sem processo): {len(df_urgente)} <<<")
    print("\nDistribuição completa por classificação:")
    print(df["classificacao"].value_counts().to_string())