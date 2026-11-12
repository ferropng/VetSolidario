"""
Indicadores de contexto para o painel operacional.

O painel do operador não deve carregar 928 mil cadastros para mostrar cinco
números. Este script lê a base uma vez e grava dois arquivos leves:

    dados/processados/resumo_cadastros.csv      indicadores gerais (chave/valor)
    dados/processados/municipios_sem_cadastro.csv   municípios a mobilizar

Uso:
    python src/resumo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"
BRUTOS = RAIZ / "dados" / "brutos"
sys.path.insert(0, str(RAIZ / "src"))

import dim_municipios as dim  # noqa: E402


def main() -> None:
    cadastros = pd.read_parquet(
        PROCESSADOS / "cadastros.parquet",
        columns=["data_cadastro", "especie", "idade", "filhote",
                 "codigo_ibge", "populacao"],
    )
    municipios = pd.read_csv(PROCESSADOS / "municipios_cadastros.csv",
                             dtype={"codigo_ibge": str})

    populacao = cadastros.drop_duplicates("codigo_ibge")["populacao"].sum()
    total = len(cadastros)

    resumo = [
        ("animais_cadastrados", total),
        ("municipios_com_cadastro", cadastros["codigo_ibge"].nunique()),
        ("populacao_coberta", int(populacao)),
        ("cobertura_por_100k", round(100_000 * total / populacao, 1)),
        ("pct_gato", round(100 * cadastros["especie"].eq("Gato").mean(), 1)),
        ("pct_filhote", round(100 * cadastros["filhote"].fillna(False).mean(), 1)),
        ("idade_mediana", float(cadastros["idade"].median())),
        ("primeiro_cadastro", cadastros["data_cadastro"].min().date().isoformat()),
        ("ultimo_cadastro", cadastros["data_cadastro"].max().date().isoformat()),
        ("municipios_sem_cadastro", 5571 - cadastros["codigo_ibge"].nunique()),
    ]

    # ---- alcance sobre os domicílios que declararam ter cão ou gato (PNS) ----
    domicilios = PROCESSADOS / "domicilios_animais_uf.csv"
    if domicilios.exists():
        pnad = pd.read_csv(domicilios)
        pnad = pnad[pnad["ano"] == pnad["ano"].max()]
        alcance = (municipios.groupby("uf")
                   .agg(cadastros=("cadastros", "sum"),
                        cadastros_cao=("cadastros_cao", "sum"),
                        cadastros_gato=("cadastros_gato", "sum"))
                   .reset_index()
                   .merge(pnad[["uf", "domicilios_cao", "domicilios_gato",
                                "pct_domicilios_cao", "pct_domicilios_gato"]],
                          on="uf", how="left"))
        alcance["cao_por_100_domicilios"] = (
            100 * alcance["cadastros_cao"] / alcance["domicilios_cao"]).round(2)
        alcance["gato_por_100_domicilios"] = (
            100 * alcance["cadastros_gato"] / alcance["domicilios_gato"]).round(2)
        alcance.to_csv(PROCESSADOS / "alcance_uf.csv", index=False,
                       encoding="utf-8")

        resumo += [
            ("domicilios_com_cao", int(alcance["domicilios_cao"].sum())),
            ("domicilios_com_gato", int(alcance["domicilios_gato"].sum())),
            ("cao_por_100_domicilios",
             round(100 * alcance["cadastros_cao"].sum()
                   / alcance["domicilios_cao"].sum(), 2)),
            ("gato_por_100_domicilios",
             round(100 * alcance["cadastros_gato"].sum()
                   / alcance["domicilios_gato"].sum(), 2)),
            ("ano_pnad", int(pnad["ano"].max())),
        ]

    tabela = pd.DataFrame(resumo, columns=["indicador", "valor"])
    tabela.to_csv(PROCESSADOS / "resumo_cadastros.csv", index=False, encoding="utf-8")
    print(tabela.to_string(index=False))

    # municípios sem nenhum cadastro: alvo de campanha de mobilização
    com_cadastro = set(municipios["codigo_ibge"].str.zfill(6))
    populacao_ibge = pd.read_csv(BRUTOS / "populacao_ibge.csv",
                                 dtype={"codigo_ibge": str})
    populacao_ibge["codigo_ibge"] = populacao_ibge["codigo_ibge"].str.zfill(6)

    sem = populacao_ibge[~populacao_ibge["codigo_ibge"].isin(com_cadastro)].copy()
    sem["uf"] = sem["codigo_ibge"].str[:2].map(dim.UF_POR_CODIGO)
    sem["latitude"] = sem["codigo_ibge"].map(
        lambda c: dim.coordenadas(c)[0] if dim.coordenadas(c) else None)
    sem["longitude"] = sem["codigo_ibge"].map(
        lambda c: dim.coordenadas(c)[1] if dim.coordenadas(c) else None)
    sem = sem.rename(columns={"municipio": "municipio"})[
        ["codigo_ibge", "municipio", "uf", "populacao", "latitude", "longitude"]
    ].sort_values("populacao", ascending=False)

    sem.to_csv(PROCESSADOS / "municipios_sem_cadastro.csv", index=False,
               encoding="utf-8")
    print(f"\nmunicípios sem cadastro: {len(sem)}")
    print(sem.head(8)[["municipio", "uf", "populacao"]].to_string(index=False))


if __name__ == "__main__":
    main()
