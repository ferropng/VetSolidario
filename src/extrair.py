"""
Etapa 1 — Extração.

Baixa os microdados do SINAN (FTP DATASUS), converte DBC -> DBF e grava
um Parquet bruto por agravo/ano em dados/brutos/.

Uso:
    python src/extrair.py --agravos ANTR ESPO --anos 2022 2023 2024 2025
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sinan  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]

# Colunas efetivamente usadas na análise (reduz volume e tempo de leitura).
COLUNAS = {
    "ANTR": [
        "DT_NOTIFIC", "DT_SIN_PRI", "DT_ENCERRA", "ID_MN_RESI", "SG_UF",
        "NU_IDADE_N", "CS_SEXO", "CS_RACA", "ANIMAL", "CONDIC_ANI",
        "ANT_MORDED", "ANT_ARRANH", "ANT_LAMBED", "ANT_PROFUN",
        "ANT_DT_EXP", "DOSES", "TRA_INTERR", "TRA_MOTIVO",
        "BUSCA_ATIV", "FIM_ANIMAL",
    ],
    "ESPO": [
        "NU_ANO", "DT_NOTIFIC", "SG_UF_NOT", "ID_MUNICIP", "ESPECIE",
        "TP_ZN_OCO", "TP_AMB_OCO", "DT_INI_EPI",
    ],
    "LEIV": [
        "DT_NOTIFIC", "ID_MN_RESI", "SG_UF", "NU_IDADE_N", "CS_SEXO",
        "CLASSI_FIN", "CRITERIO", "EVOLUCAO", "DT_OBITO",
    ],
}


def extrair(agravo: str, anos: list[int]) -> None:
    colunas = COLUNAS.get(agravo)
    if not colunas:
        raise SystemExit(f"Agravo sem mapa de colunas: {agravo}")

    for ano in anos:
        destino = RAIZ / "dados" / "brutos" / f"{agravo.lower()}_{ano}.parquet"
        if destino.exists():
            print(f"[skip] {destino.name} já existe")
            continue

        try:
            dbc = sinan.baixar(agravo, ano)
        except Exception as erro:  # arquivo ainda não publicado no FTP
            print(f"[aviso] {agravo} {ano}: {erro}")
            continue

        registros = sinan.ler_registros(dbc, colunas=colunas)
        df = pd.DataFrame.from_records(registros)
        df["ano_arquivo"] = ano
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, index=False)
        print(f"[ok] {agravo} {ano}: {len(df):,} registros -> {destino.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extração dos microdados do SINAN")
    parser.add_argument("--agravos", nargs="+", default=["ANTR"],
                        choices=sorted(COLUNAS))
    parser.add_argument("--anos", nargs="+", type=int,
                        default=[2022, 2023, 2024, 2025])
    args = parser.parse_args()

    for agravo in args.agravos:
        extrair(agravo, args.anos)


if __name__ == "__main__":
    main()
