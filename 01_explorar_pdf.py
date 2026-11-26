"""
PASSO 1 — EXPLORAÇÃO

Objetivo: olhar cru para 1 PDF de exemplo antes de escrever regra de extração.
Rode isso para CADA layout diferente que você encontrar entre as 13 unidades
(pode ser que nem todas usem o mesmo template).

Uso:
    python 01_explorar_pdf.py caminho/para/exemplo.pdf
"""
import sys
import pdfplumber


def explorar(caminho_pdf: str):
    with pdfplumber.open(caminho_pdf) as pdf:
        print(f"Total de páginas: {len(pdf.pages)}\n")

        pagina = pdf.pages[0]

        print("=" * 60)
        print("TEXTO BRUTO DA PÁGINA 1 (primeiros 1500 caracteres)")
        print("=" * 60)
        texto = pagina.extract_text() or ""
        print(texto[:1500])

        print("\n" + "=" * 60)
        print("TABELAS DETECTADAS NA PÁGINA 1")
        print("=" * 60)
        tabelas = pagina.extract_tables()
        print(f"Número de tabelas encontradas: {len(tabelas)}\n")

        for i, tabela in enumerate(tabelas):
            print(f"--- Tabela {i+1} (primeiras 5 linhas) ---")
            for linha in tabela[:5]:
                print(linha)
            print()

        # Se extract_tables() vier vazio ou bagunçado, teste estratégias
        # alternativas de detecção de linha/coluna:
        print("=" * 60)
        print("TESTE COM ESTRATÉGIA ALTERNATIVA (texto, sem linhas visíveis)")
        print("=" * 60)
        tabelas_alt = pagina.extract_tables(table_settings={
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
        })
        print(f"Tabelas encontradas com estratégia 'text': {len(tabelas_alt)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python 01_explorar_pdf.py caminho/para/arquivo.pdf")
        sys.exit(1)
    explorar(sys.argv[1])
