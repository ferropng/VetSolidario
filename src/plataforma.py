"""
Camada operacional do VetSolidário — dados SINTÉTICOS com forma de operação.

Por que existe: nenhuma base pública registra teleconsulta veterinária,
castração agendada ou resgate de animal. Para que o painel do operador seja
demonstrável, esta etapa gera uma fila de solicitações com o ciclo de vida
completo (abertura, primeira resposta, conclusão), prazo de atendimento (SLA),
responsável e unidade.

O que é real aqui: o município, a coordenada e o volume relativo. O número de
solicitações de cada município é proporcional à demanda antirrábica real
(SINAN) e à lacuna de cobertura do cadastro (SinPatinhas); os municípios-piloto
saem do índice de prioridade calculado sobre dados reais.

O que é simulado: as solicitações em si, os prazos, os nomes dos profissionais
e os relatos. Nada disso é apresentado como dado oficial.

Uso:
    python src/plataforma.py --total 9000
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROCESSADOS = RAIZ / "dados" / "processados"

REFERENCIA_PADRAO = "2026-11-08 23:59"
JANELA_DIAS = 180

BAIRROS = [
    "Centro", "Zona Norte", "Zona Sul", "Zona Leste", "Zona Oeste",
    "Distrito Industrial", "Área Rural",
]

CANAIS = ["Aplicativo", "WhatsApp", "Telefone", "UBS / posto de saúde"]
PESOS_CANAL = [0.44, 0.32, 0.14, 0.10]

VETERINARIOS = [
    "Dra. Ana Beatriz Rocha", "Dr. Caio Menezes", "Dra. Fernanda Lima",
    "Dr. Guilherme Salles", "Dra. Helena Prado", "Dr. Ítalo Barreto",
    "Dra. Juliana Amaral", "Dr. Leandro Faria", "Dra. Mariana Duarte",
    "Dr. Nelson Aguiar", "Dra. Patrícia Vasques", "Dr. Rafael Toledo",
]
EQUIPES = [
    "Equipe de resgate municipal", "Equipe ONG Patinhas Livres",
    "Equipe voluntária Bairro Unido", "Mutirão de resgate regional",
    "Equipe de resgate — Defesa Animal",
]

# SLA por tipo e prioridade, em horas. É o relógio que o operador vê.
SLA = {
    ("Teleconsulta", "Crítica"): 1,
    ("Teleconsulta", "Alta"): 4,
    ("Teleconsulta", "Média"): 12,
    ("Teleconsulta", "Baixa"): 24,
    ("Resgate", "Crítica"): 2,
    ("Resgate", "Alta"): 6,
    ("Resgate", "Média"): 24,
    ("Castração", "Alta"): 72,
    ("Castração", "Média"): 168,
    ("Castração", "Baixa"): 336,
}

FATOR_RESPOSTA = 0.45
FATOR_SERVICO = {"Teleconsulta": (0.5, 2.0), "Castração": (48, 240), "Resgate": (4, 72)}

RELATOS = {
    "Teleconsulta": [
        "Cadela com ferida na pata há três dias",
        "Gato sem comer e apático desde ontem",
        "Filhote com diarreia e desidratação",
        "Cão com coceira intensa e queda de pelo",
        "Tutora idosa pede orientação sobre medicação",
    ],
    "Castração": [
        "Solicitação de castração de fêmea adulta",
        "Castração de macho de rua recolhido pela vizinhança",
        "Tutora de baixa renda pede castração de duas gatas",
        "Colônia de gatos do bairro — pedido de mutirão",
    ],
    "Resgate": [
        "Cão atropelado na via principal",
        "Animal abandonado em terreno baldio, sem água",
        "Gato preso em bueiro, moradores pedem ajuda",
        "Cadela com filhotes sob marquise de loja fechada",
        "Animal ferido com suspeita de maus-tratos",
    ],
}

PESO_TIPO = {"Teleconsulta": 0.45, "Castração": 0.37, "Resgate": 0.18}
PRIORIDADES = {
    "Teleconsulta": (["Baixa", "Média", "Alta"], [0.45, 0.40, 0.15]),
    "Castração": (["Baixa", "Média", "Alta"], [0.58, 0.34, 0.08]),
    "Resgate": (["Média", "Alta", "Crítica"], [0.15, 0.45, 0.40]),
}


def selecionar_municipios(quantidade: int = 22) -> pd.DataFrame:
    arquivo = PROCESSADOS / "municipios_cadastros.csv"
    if not arquivo.exists():
        raise SystemExit(
            "Rode antes: python src/processar_antr.py && "
            "python src/processar_cadastros.py"
        )
    municipios = pd.read_csv(arquivo, dtype={"codigo_ibge": str})
    municipios = municipios[municipios["latitude"].notna()]

    prioritarios = municipios.nlargest(9, "indice_prioridade")
    grandes = municipios.nlargest(9, "populacao")
    resto = municipios[~municipios["codigo_ibge"].isin(
        pd.concat([prioritarios, grandes])["codigo_ibge"])]
    medios = resto[resto["populacao"].between(100_000, 400_000)].nlargest(
        max(quantidade - 18, 0), "cadastros")

    pilotos = pd.concat([prioritarios, grandes, medios]).drop_duplicates("codigo_ibge")
    return pilotos.head(quantidade).reset_index(drop=True)


def gerar(total: int = 9_000, semente: int = 42,
          referencia: str = REFERENCIA_PADRAO) -> tuple[pd.DataFrame, pd.Timestamp]:
    rng = np.random.default_rng(semente)
    ref = pd.Timestamp(referencia)
    inicio = ref - timedelta(days=JANELA_DIAS)

    pilotos = selecionar_municipios()
    demanda = pilotos["demanda_por_100k"].fillna(pilotos["demanda_por_100k"].median())
    cobertura = pilotos["cobertura_por_100k"].fillna(
        pilotos["cobertura_por_100k"].median())
    # volume esperado = taxa real da demanda x população; multiplicado pela
    # lacuna de cobertura, porque onde o cadastro não chegou a plataforma
    # tende a ser mais procurada.
    volume = demanda / 100_000 * pilotos["populacao"].clip(lower=1)
    peso = (volume / volume.max()) * (1 + (1 - cobertura / cobertura.max()))
    peso = (peso / peso.sum()).to_numpy()

    municipio_idx = rng.choice(len(pilotos), size=total, p=peso)
    tipos = rng.choice(list(PESO_TIPO), size=total,
                       p=[PESO_TIPO[t] for t in PESO_TIPO])

    linhas = []
    for i in range(total):
        linha = pilotos.iloc[municipio_idx[i]]
        tipo = str(tipos[i])
        prioridades, probabilidades = PRIORIDADES[tipo]
        prioridade = str(rng.choice(prioridades, p=probabilidades))
        sla = SLA[(tipo, prioridade)]

        dias_atras = float(rng.exponential(9)) if rng.random() < 0.55 \
            else float(rng.uniform(30, JANELA_DIAS))
        aberta_em = ref - timedelta(days=dias_atras, hours=float(rng.uniform(0, 24)))
        aberta_em = max(aberta_em, inicio)

        mediana_resposta = max(0.25, sla * FATOR_RESPOSTA * float(rng.uniform(0.4, 1.9)))
        resposta_horas = float(rng.lognormal(np.log(mediana_resposta), 0.55))
        if rng.random() < 0.14:
            resposta_horas *= float(rng.uniform(1.6, 3.2))
        primeira_resposta = aberta_em + timedelta(hours=resposta_horas)

        baixo, alto = FATOR_SERVICO[tipo]
        conclusao = primeira_resposta + timedelta(hours=float(rng.uniform(baixo, alto)))

        if primeira_resposta > ref:
            status, resposta_em, concluida_em, responsavel = "Na fila", pd.NaT, pd.NaT, ""
        elif conclusao > ref:
            status, resposta_em, concluida_em = "Em andamento", primeira_resposta, pd.NaT
            responsavel = str(rng.choice(VETERINARIOS)) if tipo == "Teleconsulta" \
                else str(rng.choice(EQUIPES))
        elif rng.random() < 0.06:
            status, resposta_em, concluida_em, responsavel = "Cancelada", primeira_resposta, pd.NaT, ""
        else:
            status, resposta_em, concluida_em = "Concluída", primeira_resposta, conclusao
            responsavel = str(rng.choice(VETERINARIOS)) if tipo == "Teleconsulta" \
                else str(rng.choice(EQUIPES))

        if tipo == "Teleconsulta":
            unidade = "Teleconsulta — plataforma"
        elif tipo == "Castração":
            unidade = f"Clínica parceira — {linha['municipio']}"
        else:
            unidade = "Rede de resgate"

        linhas.append({
            "aberta_em": aberta_em,
            "tipo": tipo,
            "prioridade": prioridade,
            "status": status,
            "canal": str(rng.choice(CANAIS, p=PESOS_CANAL)),
            "relato": str(rng.choice(RELATOS[tipo])),
            "codigo_ibge": linha["codigo_ibge"],
            "municipio": linha["municipio"],
            "uf": linha["uf"],
            "bairro": str(rng.choice(BAIRROS)),
            "latitude": linha["latitude"] + rng.normal(0, 0.03),
            "longitude": linha["longitude"] + rng.normal(0, 0.03),
            "sla_horas": sla,
            "primeira_resposta_em": resposta_em,
            "concluida_em": concluida_em,
            "responsavel": responsavel,
            "unidade": unidade,
        })

    df = pd.DataFrame(linhas).sort_values("aberta_em").reset_index(drop=True)
    df.insert(0, "id_solicitacao", [f"VS-{200000 + i}" for i in range(len(df))])
    df["aberta_em"] = df["aberta_em"].dt.floor("min")
    return df, ref


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=9_000)
    parser.add_argument("--referencia", default=REFERENCIA_PADRAO)
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args()

    df, ref = gerar(args.total, args.semente, args.referencia)
    PROCESSADOS.mkdir(parents=True, exist_ok=True)

    destino = PROCESSADOS / "atendimentos.csv"
    df.to_csv(destino, index=False, encoding="utf-8")
    pd.DataFrame([{"referencia": ref, "semente": args.semente,
                   "total": len(df)}]).to_csv(
        PROCESSADOS / "atendimentos_meta.csv", index=False, encoding="utf-8")

    antigo = PROCESSADOS / "plataforma_solicitacoes.csv"
    if antigo.exists():
        antigo.unlink()

    abertas = df[df["status"].isin(["Na fila", "Em andamento"])]
    print(f"{len(df):,} solicitações simuladas -> {destino}".replace(",", "."))
    print(f"referência: {ref:%d/%m/%Y %H:%M}")
    print(df["status"].value_counts().to_string())
    print(f"fila aberta: {len(abertas):,}".replace(",", "."))
    print(df["tipo"].value_counts().to_string())


if __name__ == "__main__":
    main()
