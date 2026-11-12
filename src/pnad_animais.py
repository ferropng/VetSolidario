"""
Domicílios com cão e com gato — PNAD/PNS via SIDRA (IBGE).

Por que entra no projeto: o SinPatinhas informa quantos animais foram
cadastrados, mas não quantos existem. Estas duas tabelas do IBGE dão o
denominador que faltava — quantos domicílios brasileiros declaram ter cão ou
gato — e permitem medir o alcance real da política de cadastro.

Tabelas usadas:
    4930  Domicílios com algum cachorro      (variáveis 5176 milhares, 5180 %)
    4931  Domicílios com algum gato          (variáveis 5184 milhares, 5188 %)

Níveis: UF (todas as 27) e município apenas para as capitais — a PNAD não é
representativa em nível municipal fora das capitais (a API devolve "...").

Saídas:
    dados/processados/domicilios_animais_uf.csv
    dados/processados/domicilios_animais_capitais.csv

Uso:
    python src/pnad_animais.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

import dim_municipios as dim

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"

BASE = "https://apisidra.ibge.gov.br/values"
ANOS = "2013,2019"

CAPITAIS = {
    "1200401": "Rio Branco", "2704302": "Maceió", "1600303": "Macapá",
    "1302603": "Manaus", "2927408": "Salvador", "2304400": "Fortaleza",
    "3205309": "Vitória", "5208707": "Goiânia", "2111300": "São Luís",
    "5103403": "Cuiabá", "5002704": "Campo Grande", "3106200": "Belo Horizonte",
    "1501402": "Belém", "2507507": "João Pessoa", "4106902": "Curitiba",
    "2611606": "Recife", "2207702": "Teresina", "3304557": "Rio de Janeiro",
    "2408102": "Natal", "4314902": "Porto Alegre", "1100205": "Porto Velho",
    "1400100": "Boa Vista", "4205407": "Florianópolis", "3550308": "São Paulo",
    "2800308": "Aracaju", "1721000": "Palmas", "5300108": "Brasília",
}

TABELAS = {
    "cao": {"tabela": 4930, "volume": 5176, "percentual": 5180},
    "gato": {"tabela": 4931, "volume": 5184, "percentual": 5188},
}


def consultar(tabela: int, variaveis: str, periodo: str, nivel: int) -> pd.DataFrame:
    url = f"{BASE}/t/{tabela}/n{nivel}/all/v/{variaveis}/p/{periodo}"
    resposta = requests.get(url, timeout=120)
    resposta.raise_for_status()
    dados = resposta.json()
    if not dados:
        return pd.DataFrame()

    tabela_df = pd.DataFrame(dados[1:])
    tabela_df["valor"] = pd.to_numeric(tabela_df["V"], errors="coerce")
    return tabela_df.dropna(subset=["valor"])


def por_uf() -> pd.DataFrame:
    partes = []
    for especie, meta in TABELAS.items():
        bruto = consultar(meta["tabela"],
                          f"{meta['volume']},{meta['percentual']}",
                          ANOS, 3)
        for sufixo, codigo in (("domicilios", meta["volume"]),
                               ("percentual", meta["percentual"])):
            if bruto.empty:
                continue
            recorte = bruto[pd.to_numeric(bruto["D2C"], errors="coerce")
                            == codigo].copy()
            recorte["uf"] = recorte["D1C"].map(dim.UF_POR_CODIGO)
            recorte["ano"] = recorte["D3N"]
            coluna = f"{sufixo}_{especie}"
            recorte = recorte.rename(columns={"valor": coluna})[
                ["uf", "ano", coluna]]
            partes.append(recorte)

    if not partes:
        raise SystemExit("SIDRA não devolveu dados para as UFs.")
    tabela = partes[0]
    for parte in partes[1:]:
        tabela = tabela.merge(parte, on=["uf", "ano"], how="outer")

    # "Mil domicílios" -> domicílios
    for coluna in ("domicilios_cao", "domicilios_gato"):
        if coluna in tabela:
            tabela[coluna] = (tabela[coluna] * 1000).round(0)

    tabela["ano"] = tabela["ano"].astype(int)
    tabela = tabela.rename(columns={
        "percentual_cao": "pct_domicilios_cao",
        "percentual_gato": "pct_domicilios_gato",
    })
    return tabela.sort_values(["ano", "uf"]).reset_index(drop=True)


def por_capital() -> pd.DataFrame:
    localidades = ",".join(CAPITAIS)
    partes = []
    for especie, meta in TABELAS.items():
        bruto = consultar(meta["tabela"], str(meta["volume"]), "2019", 6)
        bruto = bruto[bruto["D1C"].isin(CAPITAIS)]
        bruto["codigo_ibge"] = bruto["D1C"]
        bruto["municipio"] = (bruto["D1N"]
                              .str.replace(r"\s*\([A-Z]{2}\)$", "", regex=True)
                              .str.replace(r"\s*-\s*[A-Z]{2}$", "", regex=True))
        bruto = bruto.rename(columns={"valor": f"domicilios_{especie}"})[
            ["codigo_ibge", "municipio", f"domicilios_{especie}"]]
        partes.append(bruto)

    # a consulta em n6 exige a lista de códigos na URL
    if all(parte.empty for parte in partes):
        return pd.DataFrame()

    tabela = partes[0]
    for parte in partes[1:]:
        tabela = tabela.merge(parte, on=["codigo_ibge", "municipio"], how="outer")

    for coluna in ("domicilios_cao", "domicilios_gato"):
        if coluna in tabela:
            tabela[coluna] = (tabela[coluna] * 1000).round(0)
    tabela["uf"] = tabela["codigo_ibge"].str[:2].map({
        "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
        "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
        "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
        "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
        "51": "MT", "52": "GO", "53": "DF",
    })
    return tabela.sort_values("municipio").reset_index(drop=True)


def main() -> None:
    PROCESSADOS.mkdir(parents=True, exist_ok=True)

    uf = por_uf()
    destino_uf = PROCESSADOS / "domicilios_animais_uf.csv"
    uf.to_csv(destino_uf, index=False, encoding="utf-8")
    print(f"UFs: {len(uf)} linhas -> {destino_uf}")

    capitais = por_capital()
    destino_capitais = PROCESSADOS / "domicilios_animais_capitais.csv"
    if not capitais.empty:
        capitais.to_csv(destino_capitais, index=False, encoding="utf-8")
        print(f"capitais: {len(capitais)} -> {destino_capitais}")

    recente = uf[uf["ano"] == 2019]
    print("\nBrasil 2019 (soma das UFs):")
    print(f"  domicílios com cão ... {recente['domicilios_cao'].sum():,.0f}"
          .replace(",", "."))
    print(f"  domicílios com gato .. {recente['domicilios_gato'].sum():,.0f}"
          .replace(",", "."))
    print("\nmaiores volumes de domicílios com cão:")
    print(recente.nlargest(6, "domicilios_cao")
          [["uf", "domicilios_cao", "pct_domicilios_cao"]].to_string(index=False))


if __name__ == "__main__":
    main()
