"""
PASSO 8 — EXTRAÇÃO DAS ATAS DE REGISTRO DE PREÇO VIGENTES

Lê o PDF "MEDICAMENTOS COM ARP VIGENTE" (multi-página) e extrai uma linha
por item de Ata: número do processo, descrição do medicamento, embalagem,
fornecedor, data de publicação e data de vigência.

Layout observado (10 colunas, cabeçalho em 2 linhas mescladas):
  Item | Edição | Nº Processo | ID CidadES | Descrição Resumida |
  Embalagem | ARP+Proposta+Publicação | Fornecedor |
  Publicada em | Vigência da Ata

Uso:
    python 08_extrair_atas_vigentes.py "MEDICAMENTOS_COM_ARP_VIGENTE....pdf"
"""
import sys
import re
from datetime import datetime
import pdfplumber
import pandas as pd


def parse_data_br(texto):
    if not texto:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if not m:
        return None
    dia, mes, ano = m.groups()
    try:
        return datetime(int(ano), int(mes), int(dia)).date().isoformat()
    except ValueError:
        return None


def extrair(caminho_pdf: str) -> pd.DataFrame:
    registros = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                for linha in tabela:
                    if not linha or len(linha) < 10:
                        continue
                    item = linha[0]
                    if not item or not str(item).strip().isdigit():
                        continue  # pula linhas de cabeçalho/título
                    _, edicao, processo, id_cidades, descricao, embalagem, \
                        arp_num, fornecedor, publicada_em, vigencia = linha[:10]

                    registros.append({
                        "item": int(item),
                        "edicao_serp": edicao,
                        "numero_processo": processo,
                        "descricao_medicamento": re.sub(r"\s+", " ", (descricao or "").strip()),
                        "embalagem": re.sub(r"\s+", " ", (embalagem or "").strip()),
                        "numero_ata": (arp_num or "").strip(),
                        "fornecedor": re.sub(r"\s+", " ", (fornecedor or "").strip()),
                        "publicada_em": parse_data_br(publicada_em),
                        "vigencia_fim": parse_data_br(vigencia),
                    })

    return pd.DataFrame(registros)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python 08_extrair_atas_vigentes.py caminho_do_pdf.pdf")
        sys.exit(1)

    df = extrair(sys.argv[1])
    df.to_csv("atas_vigentes.csv", index=False)
    print(f"Extraídas {len(df)} atas/itens.")
    print(f"\nSem data de vigência reconhecida: {df['vigencia_fim'].isna().sum()}")
    print("\nAmostra:")
    print(df.head(10).to_string(index=False))