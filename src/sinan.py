"""
Acesso aos microdados do SINAN no FTP público do DATASUS.

Os arquivos são distribuídos em DBC (dBASE comprimido). O fluxo é:
    FTP -> DBC -> DBF (pyreaddbc) -> registros (dbfread)

Nenhum dado sensível é usado: os microdados do SINAN são públicos e
anonimizados na origem (sem nome, CPF ou endereço).
"""

from __future__ import annotations

import ftplib
import io
import os
from pathlib import Path

import dbfread
import pyreaddbc

FTP_HOST = "ftp.datasus.gov.br"
FTP_DIR = "/dissemin/publicos/SINAN/DADOS/FINAIS"
CACHE = Path(__file__).resolve().parents[1] / "dados" / "brutos"


def _conectar() -> ftplib.FTP:
    ftp = ftplib.FTP(FTP_HOST, timeout=120)
    ftp.login()
    ftp.voidcmd("TYPE I")
    return ftp


def baixar(agravo: str, ano: int, forcar: bool = False) -> Path:
    """Baixa <AGRAVO>BR<AA>.dbc do FTP do DATASUS e devolve o caminho local."""
    CACHE.mkdir(parents=True, exist_ok=True)
    nome = f"{agravo}BR{str(ano)[-2:]}.dbc"
    destino = CACHE / nome
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        return destino

    with _conectar() as ftp:
        ftp.cwd(FTP_DIR)
        with open(destino, "wb") as fh:
            ftp.retrbinary(f"RETR {nome}", fh.write)
    return destino


def ler_registros(dbc: Path | str, colunas: list[str] | None = None) -> list[dict]:
    """Converte DBC -> DBF (cache) e devolve os registros como lista de dicts."""
    dbc = Path(dbc)
    dbf = dbc.with_suffix(".dbf")
    if not dbf.exists() or dbf.stat().st_size < dbc.stat().st_size / 20:
        pyreaddbc.dbc2dbf(str(dbc), str(dbf))

    tabela = dbfread.DBF(str(dbf), encoding="latin1", load=False)
    campos = set(tabela.field_names)
    if colunas:
        faltando = [c for c in colunas if c not in campos]
        if faltando:
            raise KeyError(f"Campos ausentes em {dbc.name}: {faltando}")
        colunas = [c for c in colunas if c in campos]
    else:
        colunas = list(tabela.field_names)

    registros = []
    for linha in tabela:
        if linha.get("_deleted"):
            continue
        registros.append({c: linha.get(c) for c in colunas})
    return registros


def listar_arquivos(agravo: str) -> list[str]:
    """Lista os anos disponíveis no FTP para um agravo (ex.: ANTR)."""
    with _conectar() as ftp:
        ftp.cwd(FTP_DIR)
        nomes: list[str] = []
        ftp.retrlines("NLST", nomes.append)
    return sorted(n for n in nomes if n.startswith(agravo.upper()) and n.endswith(".dbc"))


if __name__ == "__main__":
    for agravo in ("ANTR", "ESPO", "LEIV"):
        print(agravo, listar_arquivos(agravo))
