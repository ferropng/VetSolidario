"""
Etapa 2 — Limpeza, normalização e enriquecimento.

Lê os Parquets brutos, aplica o tratamento (tipos, nulos, duplicados,
padronização de categorias, outliers de data), decodifica os campos do
SINAN e cruza com a dimensão de municípios (nome, UF, coordenadas e
população) para calcular taxas por 100 mil habitantes.

Uso:
    python src/processar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dicionarios as dic  # noqa: E402
import ibge  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos"
PROCESSADOS = RAIZ / "dados" / "processados"

FAIXAS_ETARIAS = [
    (0, 4, "0-4"),
    (5, 9, "5-9"),
    (10, 14, "10-14"),
    (15, 19, "15-19"),
    (20, 29, "20-29"),
    (30, 39, "30-39"),
    (40, 49, "40-49"),
    (50, 59, "50-59"),
    (60, 200, "60+"),
]


def ler_brutos(agravo: str) -> pd.DataFrame:
    arquivos = sorted(BRUTOS.glob(f"{agravo.lower()}_*.parquet"))
    if not arquivos:
        raise SystemExit(
            f"Nenhum arquivo de {agravo} em {BRUTOS}. Rode antes: "
            f"python src/extrair.py --agravos {agravo}"
        )
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def idade_em_anos(serie: pd.Series) -> pd.Series:
    """NU_IDADE_N é composto: 1º dígito = unidade (1 h, 2 d, 3 mês, 4 ano)."""
    numero = pd.to_numeric(serie, errors="coerce")
    unidade = (numero // 1000).astype("Float64")
    valor = (numero % 1000).astype("Float64")
    anos = valor.where(unidade == 4, np.nan)
    meses = valor.where(unidade == 3, np.nan)
    dias = valor.where(unidade == 2, np.nan)
    anos = anos.fillna(meses / 12).fillna(dias / 365).fillna(0)
    return anos.clip(lower=0, upper=110)


def faixa_etaria(idade: pd.Series) -> pd.Series:
    faixa = pd.Series("Ignorado", index=idade.index, dtype="object")
    for minimo, maximo, rotulo in FAIXAS_ETARIAS:
        faixa = faixa.mask(idade.between(minimo, maximo), rotulo)
    return faixa


def _bool_sim(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().eq("1")


def processar_antr() -> pd.DataFrame:
    df = ler_brutos("ANTR")
    linhas_brutas = len(df)

    # --- padronização de tipos e códigos --------------------------------
    df["codigo_ibge"] = (
        df["ID_MN_RESI"].astype(str).str.replace(r"\D", "", regex=True)
        .str.zfill(6).replace("", np.nan)
    )

    for coluna in ("DT_NOTIFIC", "DT_SIN_PRI", "DT_ENCERRA", "ANT_DT_EXP"):
        df[coluna] = pd.to_datetime(df[coluna], errors="coerce")

    # --- duplicados ------------------------------------------------------
    antes = len(df)
    df = df.drop_duplicates(
        subset=["DT_NOTIFIC", "codigo_ibge", "NU_IDADE_N", "CS_SEXO",
                "ANIMAL", "ANT_DT_EXP"],
        keep="first",
    )
    duplicados = antes - len(df)

    # --- outliers de data ------------------------------------------------
    df["tempo_ate_atendimento_dias"] = (
        df["DT_SIN_PRI"] - df["ANT_DT_EXP"]
    ).dt.days
    df.loc[~df["tempo_ate_atendimento_dias"].between(0, 180),
           "tempo_ate_atendimento_dias"] = np.nan

    # --- decodificação ---------------------------------------------------
    df["especie_agressora"] = df["ANIMAL"].map(
        lambda v: dic.decodificar(v, dic.ANIMAL)
    )
    df["condicao_animal"] = df["CONDIC_ANI"].map(
        lambda v: dic.decodificar(v, dic.CONDIC_ANI)
    )
    df["sexo"] = df["CS_SEXO"].map(lambda v: dic.decodificar(v, dic.SEXO))
    df["raca_cor"] = df["CS_RACA"].map(lambda v: dic.decodificar(v, dic.RACA))
    df["interrompeu_tratamento"] = df["TRA_INTERR"].map(
        {"1": True, "2": False}
    ).astype("boolean")
    df["motivo_interrupcao"] = df["TRA_MOTIVO"].map(
        lambda v: dic.decodificar(v, dic.TRA_MOTIVO, padrao="Não se aplica")
    )
    df["ferimento_profundo"] = _bool_sim(df["ANT_PROFUN"])
    df["mordedura"] = _bool_sim(df["ANT_MORDED"])
    df["busca_ativa"] = df["BUSCA_ATIV"].astype(str).str.strip().eq("1")

    df["idade_anos"] = idade_em_anos(df["NU_IDADE_N"])
    df["faixa_etaria"] = faixa_etaria(df["idade_anos"]).where(
        df["idade_anos"].notna(), "Ignorado"
    )
    df["ano"] = df["DT_NOTIFIC"].dt.year
    df["mes"] = df["DT_NOTIFIC"].dt.month
    df["ano_mes"] = df["DT_NOTIFIC"].dt.to_period("M").astype(str)

    # --- dimensão municipal ---------------------------------------------
    dimensao = ibge.dimensao_municipios()
    dim = pd.DataFrame(dimensao.values())
    dim["latitude"] = pd.to_numeric(dim["latitude"], errors="coerce")
    dim["longitude"] = pd.to_numeric(dim["longitude"], errors="coerce")

    df = df.merge(dim, on="codigo_ibge", how="left")
    sem_municipio = df["municipio"].isna().sum()
    df["municipio"] = df["municipio"].fillna("Não informado")
    df["uf"] = df["uf"].fillna(
        df["codigo_ibge"].astype(str).str[:2].map(
            {str(k): v for k, v in __import__("dim_municipios").UF_POR_CODIGO.items()}
        )
    )

    # --- normalização de escala (0-100) para o índice de pressão ---------
    por_municipio = df.groupby("codigo_ibge").size().rename("atendimentos")
    pressao = np.log1p(por_municipio)
    df["indice_pressao"] = df["codigo_ibge"].map(
        (100 * (pressao - pressao.min()) / (pressao.max() - pressao.min())).round(3)
    )

    print(
        f"[ANTR] {linhas_brutas:,} brutos -> {len(df):,} após limpeza "
        f"({duplicados:,} duplicados removidos, {sem_municipio:,} sem município)"
    )
    print(df["ano"].value_counts().sort_index().to_string())
    return df


def processar_espo() -> pd.DataFrame:
    df = ler_brutos("ESPO")
    df["codigo_ibge"] = (
        df["ID_MUNICIP"].astype(str).str.replace(r"\D", "", regex=True)
        .str.zfill(6).replace("", np.nan)
    )
    df["DT_NOTIFIC"] = pd.to_datetime(df["DT_NOTIFIC"], errors="coerce")
    df["especie"] = df["ESPECIE"].map(
        lambda v: dic.decodificar(v, dic.ESPO_ESPECIE)
    )
    df["zona"] = df["TP_ZN_OCO"].map(lambda v: dic.decodificar(v, dic.ZONA))
    df["ano"] = df["DT_NOTIFIC"].dt.year
    df["mes"] = df["DT_NOTIFIC"].dt.month

    dimensao = ibge.dimensao_municipios()
    dim = pd.DataFrame(dimensao.values())[["codigo_ibge", "municipio", "uf",
                                           "latitude", "longitude", "populacao"]]
    df = df.merge(dim, on="codigo_ibge", how="left")
    df["municipio"] = df["municipio"].fillna("Não informado")
    print(f"[ESPO] {len(df):,} registros processados")
    return df


def indicadores_municipais(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município, com indicadores prontos para o dashboard."""
    agrupado = df.groupby(
        ["codigo_ibge", "municipio", "uf", "regiao_intermediaria",
         "latitude", "longitude", "populacao"], dropna=False
    ).agg(
        atendimentos=("DT_NOTIFIC", "size"),
        atendimentos_cao=("especie_agressora", lambda s: (s == "Cão").sum()),
        atendimentos_gato=("especie_agressora", lambda s: (s == "Gato").sum()),
        pct_gato=("especie_agressora", lambda s: 100 * (s == "Gato").mean()),
        pct_animal_suspeito=("condicao_animal",
                             lambda s: 100 * (s == "Suspeito").mean()),
        pct_interrupcao=("interrompeu_tratamento",
                         lambda s: 100 * s.fillna(False).mean()),
        pct_ferimento_profundo=("ferimento_profundo", lambda s: 100 * s.mean()),
        tempo_medio_atendimento=("tempo_ate_atendimento_dias", "mean"),
        idade_media=("idade_anos", "mean"),
    ).reset_index()

    agrupado["taxa_por_100k"] = np.where(
        agrupado["populacao"] > 0,
        agrupado["atendimentos"] / agrupado["populacao"] * 100_000,
        np.nan,
    )
    agrupado = agrupado.round({
        "pct_gato": 2, "pct_animal_suspeito": 2, "pct_interrupcao": 2,
        "pct_ferimento_profundo": 2, "tempo_medio_atendimento": 2,
        "idade_media": 2, "taxa_por_100k": 2,
    })
    return agrupado.sort_values("atendimentos", ascending=False)


def main() -> None:
    PROCESSADOS.mkdir(parents=True, exist_ok=True)

    antr = processar_antr()
    antr.to_parquet(PROCESSADOS / "atendimentos_antirabicos.parquet", index=False)

    indicadores = indicadores_municipais(antr)
    indicadores.to_csv(PROCESSADOS / "municipios_indicadores.csv",
                       index=False, encoding="utf-8")

    serie_mensal = (
        antr.groupby(["ano_mes", "uf"]).size().rename("atendimentos")
        .reset_index()
    )
    serie_mensal.to_csv(PROCESSADOS / "serie_mensal.csv",
                        index=False, encoding="utf-8")

    perfis = (
        antr.groupby(["faixa_etaria", "especie_agressora", "sexo"])
        .agg(atendimentos=("DT_NOTIFIC", "size"),
             pct_interrupcao=("interrompeu_tratamento",
                              lambda s: 100 * s.fillna(False).mean()),
             pct_ferimento_profundo=("ferimento_profundo",
                                     lambda s: 100 * s.mean()))
        .reset_index()
    )
    perfis.to_csv(PROCESSADOS / "perfil_atendimentos.csv",
                  index=False, encoding="utf-8")

    try:
        espo = processar_espo()
        espo.to_parquet(PROCESSADOS / "esporotricose.parquet", index=False)
        (
            espo.groupby(["codigo_ibge", "municipio", "uf"])["especie"]
            .agg(total="size",
                 gatos=lambda s: (s == "Gato").sum())
            .reset_index()
            .to_csv(PROCESSADOS / "municipios_esporotricose.csv",
                    index=False, encoding="utf-8")
        )
    except SystemExit as erro:
        print(f"[aviso] esporotricose não processada: {erro}")

    print(f"\nArquivos gerados em {PROCESSADOS}:")
    for arquivo in sorted(PROCESSADOS.iterdir()):
        print(f"  {arquivo.name}: {arquivo.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
