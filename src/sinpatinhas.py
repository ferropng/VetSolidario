"""
Acesso aos microdados do SinPatinhas (Base dos Dados).

O SinPatinhas é o Cadastro Nacional de Animais Domésticos (Lei 15.046/2024,
Decreto 12.439/2025), mantido pelo Ministério do Meio Ambiente. A Base dos
Dados publica a tabela tratada `basedosdados.br_mma_sinpatinhas.microdados`
e expõe um endpoint público de download em CSV comprimido — é por ele que o
projeto puxa os dados, sem precisar de conta Google/BigQuery.

Endpoint (parâmetros em base64: p=dataset, q=tabela, d=tratado, s=gratuito):
    https://basedosdados.org/api/tables/downloadTable?p=...&q=...&d=...&s=...

A tabela tem uma linha por animal cadastrado. Não há nome, CPF nem endereço do
tutor nos microdados publicados — apenas o município (código IBGE de 7 dígitos).
"""

from __future__ import annotations

import gzip
import shutil
import urllib.request
from pathlib import Path

import pandas as pd

URL_DOWNLOAD = (
    "https://basedosdados.org/api/tables/downloadTable"
    "?p=YnJfbW1hX3NpbnBhdGluaGFz&q=bWljcm9kYWRvcw==&d=dHJ1ZQ==&s=ZnJlZQ=="
)  # p=br_mma_sinpatinhas  q=microdados  d=true (tratado)  s=free

CACHE = Path(__file__).resolve().parents[1] / "dados" / "brutos"
ARQUIVO_GZ = CACHE / "sinpatinhas_microdados.csv.gz"
COLUNAS = ["data_cadastro", "id_animal", "id_municipio", "especie",
           "idade", "sexo", "cor_pelagem"]


def baixar(forcar: bool = False) -> Path:
    """Baixa o CSV comprimido do SinPatinhas e valida a integridade do gzip."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if ARQUIVO_GZ.exists() and not forcar:
        return ARQUIVO_GZ

    tmp = ARQUIVO_GZ.with_suffix(".part")
    with urllib.request.urlopen(
        urllib.request.Request(URL_DOWNLOAD, headers={"User-Agent": "Mozilla/5.0"}),
        timeout=900,
    ) as resposta, open(tmp, "wb") as destino:
        shutil.copyfileobj(resposta, destino, length=1 << 20)

    # valida antes de promover: um gzip truncado viraria "base vazia" adiante
    with gzip.open(tmp, "rt", encoding="utf-8") as fh:
        fh.readline()
        proxima = fh.readline()
    if not proxima:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("download do SinPatinhas veio vazio ou corrompido")

    tmp.replace(ARQUIVO_GZ)
    return ARQUIVO_GZ


def ler(baixar_se_faltar: bool = True) -> pd.DataFrame:
    """Lê o CSV do SinPatinhas com os tipos já corrigidos."""
    if not ARQUIVO_GZ.exists():
        if not baixar_se_faltar:
            raise FileNotFoundError(ARQUIVO_GZ)
        baixar()

    return pd.read_csv(
        ARQUIVO_GZ,
        dtype={"id_municipio": "string"},
        parse_dates=["data_cadastro"],
        usecols=COLUNAS,
    )


def cobertura() -> dict:
    """Resumo rápido do arquivo em cache (usado nos prints das etapas)."""
    df = ler(baixar_se_faltar=False)
    return {
        "registros": len(df),
        "municipios": int(df["id_municipio"].nunique()),
        "inicio": str(df["data_cadastro"].min().date()),
        "fim": str(df["data_cadastro"].max().date()),
    }


if __name__ == "__main__":
    caminho = baixar()
    print(f"arquivo: {caminho} ({caminho.stat().st_size / 1e6:.1f} MB)")
    print(cobertura())
