"""
PASSO 2 — EXTRAÇÃO EM LOTE (dado bruto, sem interpretação de negócio ainda)

Convenção assumida: os nomes de arquivo seguem um padrão contendo a UNIDADE
e a DATA, ex: "FC_CARIACICA_20260615.pdf". Ajuste `parse_nome_arquivo` para
o padrão real que a SESA usa nos seus arquivos.

Saída: um JSON por PDF em ./raw_json/, mais um log de erros.
Isso preserva o dado bruto — se você mudar a lógica de limpeza depois,
não precisa reprocessar os PDFs de novo.

Uso:
    python 02_extrair_pdf.py pasta_com_pdfs/
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime
import pdfplumber

PASTA_SAIDA = Path("raw_json")
LOG_ERROS = Path("log_extracao_erros.txt")


def parse_cabecalho(texto_pagina1: str):
    """
    Extrai unidade e data a partir do CABEÇALHO da própria página 1 do PDF,
    que é mais confiável que o nome do arquivo (nomes de arquivo variam mais
    entre downloads/renomeações do que o conteúdo do documento).

    Formato observado nos relatórios da SESA:
        "Posição de Estoque Atualizada em: 29/06/2026"
        "FCC - FARMACIA CIDADA DE CARIACICA"
    """
    data_ref = None
    m_data = re.search(r"Posi[cç][aã]o de Estoque Atualizada em:\s*(\d{2}/\d{2}/\d{4})", texto_pagina1)
    if m_data:
        data_ref = datetime.strptime(m_data.group(1), "%d/%m/%Y").date().isoformat()

    unidade = None
    m_unidade = re.search(r"FARMACIA CIDAD[AÃ]\s+(?:DE\s+|ESTADUAL\s+DE\s+)?([A-ZÀ-Ú ]+)", texto_pagina1.upper())
    if m_unidade:
        unidade = m_unidade.group(1).strip()

    return unidade, data_ref


def parse_nome_arquivo(nome_arquivo: str):
    """
    Fallback: tenta extrair unidade/data do nome do arquivo, caso o
    cabeçalho da página não seja reconhecido (ex.: PDF com layout diferente).
    """
    m = re.search(r"FC[_\s]?([A-ZÀ-Ú\s]+?)[_\s-].*?(\d{2})[_.](\d{2})[_.](\d{4})", nome_arquivo.upper())
    if not m:
        return None, None
    unidade = m.group(1).strip().replace("_", " ").rstrip("- ")
    dia, mes, ano = m.group(2), m.group(3), m.group(4)
    try:
        data = datetime(int(ano), int(mes), int(dia)).date().isoformat()
    except ValueError:
        data = None
    return unidade, data


def extrair_pdf(caminho_pdf: Path) -> dict:
    linhas_extraidas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_p1 = pdf.pages[0].extract_text() or ""
        unidade, data_ref = parse_cabecalho(texto_p1)
        if unidade is None or data_ref is None:
            unidade_fb, data_fb = parse_nome_arquivo(caminho_pdf.name)
            unidade = unidade or unidade_fb
            data_ref = data_ref or data_fb

        for num_pagina, pagina in enumerate(pdf.pages, start=1):
            tabelas = pagina.extract_tables()
            if not tabelas:
                # fallback: estratégia baseada em texto, para PDFs sem grade visível
                tabelas = pagina.extract_tables(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                })
            for tabela in tabelas:
                if not tabela or len(tabela) < 2:
                    continue
                cabecalho = tabela[0]
                for linha in tabela[1:]:
                    linhas_extraidas.append({
                        "pagina": num_pagina,
                        "cabecalho": cabecalho,
                        "linha": linha,
                    })

    return {
        "arquivo_origem": caminho_pdf.name,
        "unidade_bruta": unidade,
        "data_referencia": data_ref,
        "n_linhas": len(linhas_extraidas),
        "linhas": linhas_extraidas,
    }


def processar_pasta(pasta: Path):
    PASTA_SAIDA.mkdir(exist_ok=True)
    pdfs = sorted(pasta.glob("*.pdf"))
    print(f"Encontrados {len(pdfs)} PDFs em {pasta}")

    erros = []
    ok = 0
    for caminho_pdf in pdfs:
        try:
            resultado = extrair_pdf(caminho_pdf)
            if resultado["unidade_bruta"] is None:
                erros.append(f"{caminho_pdf.name}: não foi possível parsear unidade/data do nome do arquivo")
            saida = PASTA_SAIDA / (caminho_pdf.stem + ".json")
            saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2))
            ok += 1
        except Exception as e:
            erros.append(f"{caminho_pdf.name}: {type(e).__name__}: {e}")

    print(f"Processados com sucesso: {ok}/{len(pdfs)}")
    if erros:
        LOG_ERROS.write_text("\n".join(erros))
        print(f"{len(erros)} arquivo(s) com problema. Veja {LOG_ERROS}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python 02_extrair_pdf.py pasta_com_pdfs/")
        sys.exit(1)
    processar_pasta(Path(sys.argv[1]))
