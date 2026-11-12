"""
Etapa principal — SinPatinhas: limpeza, normalização e indicadores.

A tabela do SinPatinhas tem uma linha por animal cadastrado no Cadastro
Nacional de Animais Domésticos. Aqui ela é tratada e cruzada com:

  - dimensão municipal do IBGE (nome, UF, região, coordenadas, população);
  - indicadores do SINAN/Atendimento Antirrábico (demanda por atendimento),
    produzidos por `src/processar_antr.py`.

Saídas em dados/processados/:
  cadastros.parquet              base limpa, com município/UF/coordenadas
  municipios_cadastros.csv       uma linha por município, com cobertura e prioridade
  serie_mensal_cadastros.csv     série temporal de cadastros
  perfil_cadastros.csv           perfil cruzado (espécie × faixa etária × sexo)

Uso:
    python src/processar_cadastros.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ibge  # noqa: E402
import sinpatinhas  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"

FAIXAS = [
    (-1, 0, "Menos de 1 ano"),
    (1, 2, "1 a 2 anos"),
    (3, 5, "3 a 5 anos"),
    (6, 9, "6 a 9 anos"),
    (10, 200, "10 anos ou mais"),
]


def faixa_etaria(idade: pd.Series) -> pd.Series:
    faixa = pd.Series("Ignorado", index=idade.index, dtype="object")
    for minimo, maximo, rotulo in FAIXAS:
        faixa = faixa.mask(idade.between(minimo, maximo), rotulo)
    return faixa


def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    original = len(df)
    relatorio: dict[str, int] = {}

    # município: 7 dígitos do IBGE; nulos e códigos inválidos saem
    df["id_municipio"] = df["id_municipio"].astype("string").str.strip()
    invalidos = df["id_municipio"].isna() | ~df["id_municipio"].str.fullmatch(r"\d{7}")
    relatorio["sem_municipio_valido"] = int(invalidos.sum())
    df = df.loc[~invalidos].copy()

    # chave de 6 dígitos usada pelo sistema de saúde (SINAN/SIH)
    df["codigo_ibge"] = df["id_municipio"].str[:6]

    # duplicidade de animal
    antes = len(df)
    df = df.drop_duplicates(subset=["id_animal"], keep="first")
    relatorio["animais_duplicados"] = antes - len(df)

    # padronização de categorias
    df["especie"] = df["especie"].str.strip().str.title()
    df["sexo"] = df["sexo"].str.strip().str.title()
    df["cor_pelagem"] = df["cor_pelagem"].str.strip().str.title()

    # idade: 0 a 35 anos na base; fora de 0–30 é provável erro de digitação
    idade = pd.to_numeric(df["idade"], errors="coerce")
    relatorio["idade_invalida"] = int((idade.isna() | (idade > 30)).sum())
    df["idade"] = idade.where(idade.between(0, 30))
    df["faixa_etaria"] = faixa_etaria(df["idade"])
    df["filhote"] = (df["idade"] < 1).astype("boolean")

    df["ano"] = df["data_cadastro"].dt.year
    df["mes"] = df["data_cadastro"].dt.month
    df["ano_mes"] = df["data_cadastro"].dt.to_period("M").astype(str)
    df["dia_semana"] = df["data_cadastro"].dt.day_name()

    relatorio["removidos_total"] = original - len(df)
    return df.reset_index(drop=True), relatorio


def dimensao_municipal() -> pd.DataFrame:
    dimensao = pd.DataFrame(ibge.dimensao_municipios().values())
    dimensao["latitude"] = pd.to_numeric(dimensao["latitude"], errors="coerce")
    dimensao["longitude"] = pd.to_numeric(dimensao["longitude"], errors="coerce")
    return dimensao[["codigo_ibge", "municipio", "uf", "regiao_intermediaria",
                     "latitude", "longitude", "populacao"]]


def indicadores(df: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    por_municipio = df.groupby("codigo_ibge").agg(
        cadastros=("id_animal", "size"),
        cadastros_cao=("especie", lambda s: (s == "Cão").sum()),
        cadastros_gato=("especie", lambda s: (s == "Gato").sum()),
        pct_gato=("especie", lambda s: 100 * (s == "Gato").mean()),
        pct_femea=("sexo", lambda s: 100 * (s == "Fêmea").mean()),
        pct_filhote=("filhote", lambda s: 100 * s.fillna(False).mean()),
        idade_media=("idade", "mean"),
        idade_mediana=("idade", "median"),
        primeira_data=("data_cadastro", "min"),
        ultima_data=("data_cadastro", "max"),
    ).reset_index()

    tabela = por_municipio.merge(dim, on="codigo_ibge", how="left")
    tabela["municipio"] = tabela["municipio"].fillna("Não informado")
    tabela["populacao"] = tabela["populacao"].fillna(0)

    # cobertura: cadastros por 100 mil habitantes (normalização de escala)
    tabela["cobertura_por_100k"] = np.where(
        tabela["populacao"] > 0,
        tabela["cadastros"] / tabela["populacao"] * 100_000,
        np.nan,
    )

    # cruzamento com a demanda por atendimento antirrábico, quando existir
    antr_arquivo = PROCESSADOS / "municipios_indicadores.csv"
    if antr_arquivo.exists():
        antr = pd.read_csv(antr_arquivo, dtype={"codigo_ibge": str})[[
            "codigo_ibge", "atendimentos", "taxa_por_100k", "pct_interrupcao"
        ]].rename(columns={
            "atendimentos": "atendimentos_antirrabicos",
            "taxa_por_100k": "demanda_por_100k",
            "pct_interrupcao": "pct_abandono_tratamento",
        })
        tabela = tabela.merge(antr, on="codigo_ibge", how="left")
    else:
        tabela["atendimentos_antirrabicos"] = np.nan
        tabela["demanda_por_100k"] = np.nan
        tabela["pct_abandono_tratamento"] = np.nan

    # índice de prioridade: demanda alta + cobertura baixa
    z = lambda s: (s - s.mean()) / s.std(ddof=0)  # noqa: E731
    tabela["z_demanda"] = z(np.log1p(tabela["demanda_por_100k"].fillna(0)))
    tabela["z_cobertura"] = z(np.log1p(tabela["cobertura_por_100k"].fillna(0)))
    bruto = 0.5 * tabela["z_demanda"] - 0.5 * tabela["z_cobertura"]
    minimo, maximo = bruto.min(), bruto.max()
    tabela["indice_prioridade"] = (
        100 * (bruto - minimo) / (maximo - minimo)
    ).round(1)

    return tabela.sort_values("cadastros", ascending=False).round({
        "pct_gato": 2, "pct_femea": 2, "pct_filhote": 2,
        "idade_media": 2, "idade_mediana": 1, "cobertura_por_100k": 2,
        "demanda_por_100k": 2, "pct_abandono_tratamento": 2,
    })


def main() -> None:
    PROCESSADOS.mkdir(parents=True, exist_ok=True)

    bruto = sinpatinhas.ler()
    print(f"[SinPatinhas] {len(bruto):,} registros brutos".replace(",", "."))

    df, relatorio = limpar(bruto)
    print("[limpeza]", relatorio)
    print(f"[limpeza] {len(df):,} registros válidos".replace(",", "."))

    dim = dimensao_municipal()
    df = df.merge(dim, on="codigo_ibge", how="left")
    df.to_parquet(PROCESSADOS / "cadastros.parquet", index=False)

    tabela = indicadores(df, dim)
    tabela.to_csv(PROCESSADOS / "municipios_cadastros.csv", index=False,
                  encoding="utf-8")

    (df.groupby("ano_mes").size().rename("cadastros").reset_index()
     .to_csv(PROCESSADOS / "serie_mensal_cadastros.csv", index=False,
             encoding="utf-8"))

    (df.groupby(["faixa_etaria", "especie", "sexo"]).size()
     .rename("cadastros").reset_index()
     .to_csv(PROCESSADOS / "perfil_cadastros.csv", index=False, encoding="utf-8"))

    total = len(df)
    print(f"\nEspécie: " + " · ".join(
        f"{k} {v/total*100:.1f}%" for k, v in df["especie"].value_counts().items()
    ))
    print(f"Idade mediana: {df['idade'].median():.0f} anos | "
          f"filhotes: {df['filhote'].mean()*100:.1f}%")
    print(f"Municípios com cadastro: {tabela['codigo_ibge'].nunique():,}"
          .replace(",", "."))

    print("\nTop 10 por cobertura (população ≥ 100 mil):")
    print(tabela[tabela["populacao"] >= 100_000]
          .nlargest(10, "cobertura_por_100k")
          [["municipio", "uf", "populacao", "cadastros", "cobertura_por_100k"]]
          .to_string(index=False))

    print("\nTop 10 por índice de prioridade (demanda alta, cobertura baixa):")
    print(tabela[tabela["populacao"] >= 100_000]
          .nlargest(10, "indice_prioridade")
          [["municipio", "uf", "cobertura_por_100k", "demanda_por_100k",
            "indice_prioridade"]].to_string(index=False))

    print(f"\nArquivos em {PROCESSADOS}:")
    for arquivo in sorted(PROCESSADOS.iterdir()):
        print(f"  {arquivo.name}: {arquivo.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
