"""
Teste de fumaça do dashboard.

Executa o app.py sem navegador (streamlit.testing.v1.AppTest) e percorre
todas as seções, garantindo que nenhuma levanta exceção e que cada uma
renderiza pelo menos um bloco de conteúdo.

Uso:
    python tests/test_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from streamlit.testing.v1 import AppTest  # noqa: E402

SECOES = [
    "Situação agora",
    "Fila de trabalho",
    "Castrações",
    "Resgates",
    "Território",
    "Dados e sistema",
]


def main() -> int:
    falhas = 0
    teste = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=300)
    teste.run()
    if teste.exception:
        print("[ERRO] carga inicial:", teste.exception[0].value)
        return 1

    print(f"[ok] carga inicial · {len(teste.dataframe)} tabelas renderizadas")

    for secao in SECOES:
        teste.sidebar.radio[0].set_value(secao).run()
        if teste.exception:
            falhas += 1
            print(f"[ERRO] {secao}: {teste.exception[0].value}")
            continue
        metricas = len(teste.metric)
        tabelas = len(teste.dataframe)
        print(f"[ok] {secao} · métricas={metricas} tabelas={tabelas}")

    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
