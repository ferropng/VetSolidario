"""
Tabelas de decodificação dos campos do SINAN usados no projeto.

Fonte: dicionário de dados SINAN Net v5 — ficha "Atendimento Antirrábico
Humano" (agravo ANTR) e ficha de Epizootias/Esporotricose. As categorias
foram validadas contra a distribuição real dos microdados de 2024
(ex.: ANIMAL=1 responde por ~74% dos atendimentos, coerente com cão como
principal agressor).
"""

# --- Atendimento antirrábico humano (ANTR) -------------------------------

ANIMAL = {
    "1": "Cão",
    "2": "Gato",
    "3": "Herbívoro",
    "4": "Silvestre",
    "5": "Morcego",
    "6": "Outro",
    "7": "Ignorado",
    "9": "Ignorado",
}

CONDIC_ANI = {
    "1": "Sadio",
    "2": "Suspeito",
    "3": "Raivoso",
    "4": "Ignorado",
    "9": "Ignorado",
}

TRA_INTERR = {"1": "Sim", "2": "Não", "9": "Ignorado"}

TRA_MOTIVO = {
    "1": "Abandono do tratamento",
    "2": "Mudança de endereço / transferência",
    "3": "Óbito",
    "4": "Reação adversa",
    "9": "Outro / ignorado",
}

TIPO_EXPOSICAO = {
    "Mordedura": "ANT_MORDED",
    "Arranhadura": "ANT_ARRANH",
    "Lambedura": "ANT_LAMBED",
    "Contato indireto": "ANT_CONTAT",
    "Contato com mucosa": "ANT_MUCOSA",
}

LOCAL_FERIMENTO = {
    "Cabeça/pescoço": "ANT_CABECA",
    "Mãos": "ANT_MAOS",
    "Tronco": "ANT_TRONCO",
    "Membros inferiores": "ANT_MEMBRO",
}

SEXO = {"M": "Masculino", "F": "Feminino", "I": "Ignorado"}

RACA = {
    "1": "Branca",
    "2": "Preta",
    "3": "Amarela",
    "4": "Parda",
    "5": "Indígena",
    "9": "Ignorado",
}

# --- Esporotricose (ESPO) -------------------------------------------------

ESPO_ESPECIE = {
    "1": "Gato",
    "2": "Cão",
    "3": "Roedor",
    "4": "Outro",
    "9": "Ignorado",
}

ZONA = {"1": "Urbana", "2": "Rural", "9": "Ignorado"}


def decodificar(valor, tabela: dict[str, str], padrao: str = "Ignorado") -> str:
    """Converte o código SINAN no rótulo legível, tolerando nulos e sujeira."""
    if valor is None:
        return padrao
    chave = str(valor).strip()
    if chave in ("", "None", "nan"):
        return padrao
    return tabela.get(chave, padrao)
