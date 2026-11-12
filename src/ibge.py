"""
Dimensão populacional e geográfica dos municípios.

- População residente: IBGE, API de agregados 6579 / variável 9324
  (estimativas populacionais), cacheada em CSV para não depender da rede.
- Nome, UF, região intermediária e coordenadas: src/dim_municipios.py.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "dados" / "brutos" / "populacao_ibge.csv"
URL_IBGE = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/"
    "variaveis/9324?localidades=N6[all]"
)


def _baixar_populacao() -> dict[str, tuple[str, int]]:
    """{codigo_ibge: (nome_municipio, populacao)} direto da API do IBGE."""
    req = urllib.request.Request(
        URL_IBGE, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        bruto = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            bruto = gzip.decompress(bruto)
    dados = json.loads(bruto)
    series = dados[0]["resultados"][0]["series"]

    saida = {}
    for item in series:
        codigo = item["localidade"]["id"][:6]
        nome = item["localidade"]["nome"].rsplit(" - ", 1)[0]
        valor = next(iter(item["serie"].values()), "0")
        saida[codigo] = (nome, int(float(valor or 0)))
    return saida


def carregar_populacao(forcar: bool = False) -> dict[str, int]:
    """População por município, usando cache local quando existir."""
    if not CACHE.exists() or forcar:
        dados = _baixar_populacao()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE, "w", newline="", encoding="utf-8") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(["codigo_ibge", "municipio", "populacao"])
            for codigo, (nome, pop) in sorted(dados.items()):
                escritor.writerow([codigo, nome, pop])

    populacao = {}
    with open(CACHE, encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            populacao[linha["codigo_ibge"]] = int(linha["populacao"])
    return populacao


def dimensao_municipios() -> dict[str, dict]:
    """Junta população + nome/UF/região/coordenadas numa única dimensão."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dim_municipios import MUNICIPIOS  # noqa: PLC0415

    populacao = carregar_populacao()
    dimensao = {}
    for codigo, (nome, uf, regiao, coord) in MUNICIPIOS.items():
        dimensao[codigo] = {
            "codigo_ibge": codigo,
            "municipio": nome,
            "uf": uf,
            "regiao_intermediaria": regiao,
            "latitude": coord[0] if coord else None,
            "longitude": coord[1] if coord else None,
            "populacao": populacao.get(codigo, 0),
        }
    return dimensao


if __name__ == "__main__":
    pop = carregar_populacao(forcar=True)
    print(f"{len(pop)} municípios com população (cache: {CACHE})")
