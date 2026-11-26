"""
PASSO 9 — EXTRAÇÃO DOS PROCESSOS EM ANDAMENTO

Lê o PDF "PLANILHA DE PROCESSOS EM ANDAMENTO" e extrai o estágio atual de
cada processo de compra que AINDA NÃO virou Ata (ou seja, medicamentos sem
ARP vigente podem já ter um processo em curso — informação importante para
não classificar como "Crítico sem ação em andamento" algo que já está
sendo endereçado).

Layout (7 colunas):
  MEDICAMENTO | EDIÇÃO SERP | Nº PROCESSO | ITEM | EDITAL | DATA PREGÃO |
  FASE ATUAL DO PROCESSO

Uso:
    python 09_extrair_processos_andamento.py "PLANILHA_ANDAMENTO....pdf"
"""
import sys
import re
import pdfplumber
import pandas as pd

# Ordem de maturidade do processo (quanto maior, mais perto de virar Ata)
ORDEM_FASE = {
    "ABERTURA DE PROCESSO": 0,
    "PESQUISA DE PREÇO": 1,
    "ELABORAÇÃO DE EDITAL": 2,
    "PREGÃO AGENDADO": 3,
    "HABILITAÇÃO": 4,
    "FRACASSADO": -1,   # precisa reabrir, não conta como avanço
    "HOMOLOGAÇÃO": 5,
    "ELABORAÇÃO DE ATA": 6,
    "PUBLICAÇÃO DE ATA": 7,
}


def extrair(caminho_pdf: str) -> pd.DataFrame:
    registros = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                for linha in tabela:
                    if not linha or len(linha) < 7:
                        continue
                    medicamento, edicao, processo, item, edital, data_pregao, fase = linha[:7]
                    if not medicamento or medicamento.strip().upper() == "MEDICAMENTO":
                        continue
                    if not fase:
                        continue
                    fase_limpa = re.sub(r"\s+", " ", fase.strip().upper())
                    registros.append({
                        "medicamento": re.sub(r"\s+", " ", medicamento.strip()),
                        "edicao_serp": edicao,
                        "numero_processo": processo,
                        "edital": edital,
                        "fase_atual": fase_limpa,
                        "ordem_maturidade": ORDEM_FASE.get(fase_limpa, None),
                    })
    return pd.DataFrame(registros)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python 09_extrair_processos_andamento.py caminho_do_pdf.pdf")
        sys.exit(1)

    df = extrair(sys.argv[1])
    df.to_csv("processos_andamento.csv", index=False)
    print(f"Extraídos {len(df)} processos.")
    print("\nDistribuição por fase:")
    print(df["fase_atual"].value_counts().to_string())