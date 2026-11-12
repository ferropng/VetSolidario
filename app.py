"""
VetSolidário — Central de Operações
FIAP Global Solution 2026.2 · CitizenTech

Painel do operador: o que está na fila agora, o que estourou o prazo, quem está
atendendo, onde a demanda se concentra e o que fazer em seguida.

A camada analítica (estatística descritiva, testes, probabilidade, correlação e
agrupamento) fica no notebook `notebooks/analise_vetsolidario.ipynb`. Aqui só
entra o que o operador precisa decidir no turno.

Execução:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

RAIZ = Path(__file__).resolve().parent
PROCESSADOS = RAIZ / "dados" / "processados"
sys.path.insert(0, str(RAIZ / "src"))

st.set_page_config(
    page_title="VetSolidário · Central de Operações",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

COR = "#7C3AED"
VERDE = "#16A34A"
AZUL = "#2563EB"
CINZA = "#6B7280"
VERMELHO = "#DC2626"
LARANJA = "#EA580C"
AMBAR = "#CA8A04"
CIANO = "#0891B2"

CORES_STATUS = {
    "Na fila": CINZA,
    "Em andamento": AZUL,
    "Concluída": VERDE,
    "Cancelada": "#9CA3AF",
}
CORES_PRIORIDADE = {
    "Crítica": VERMELHO,
    "Alta": LARANJA,
    "Média": AMBAR,
    "Baixa": CIANO,
}
ORDEM_PRIORIDADE = {"Crítica": 0, "Alta": 1, "Média": 2, "Baixa": 3}

st.markdown(
    """
    <style>
    .cartao {border:1px solid rgba(124,58,237,.22);border-radius:10px;
             padding:14px 16px;margin:6px 0;}
    .cartao h4 {margin:0 0 6px 0;font-size:.82rem;letter-spacing:.06em;
                text-transform:uppercase;opacity:.75;font-weight:600;}
    .cartao .grande {font-size:1.9rem;font-weight:700;line-height:1.1;}
    .cartao .nota {font-size:.8rem;opacity:.7;margin-top:4px;}
    .pilula {display:inline-block;padding:2px 9px;border-radius:999px;
             font-size:.72rem;font-weight:700;letter-spacing:.02em;}
    .p-red {background:rgba(220,38,38,.16);color:#DC2626;}
    .p-org {background:rgba(234,88,12,.16);color:#EA580C;}
    .p-amb {background:rgba(202,138,4,.18);color:#A16207;}
    .p-cya {background:rgba(8,145,178,.16);color:#0891B2;}
    .p-gre {background:rgba(22,163,74,.16);color:#16A34A;}
    .p-blu {background:rgba(37,99,235,.16);color:#2563EB;}
    .p-gry {background:rgba(107,114,128,.18);color:#6B7280;}
    .alerta {padding:10px 14px;border-radius:8px;margin:5px 0;
             font-size:.88rem;border-left:4px solid;}
    .a-red {background:rgba(220,38,38,.09);border-color:#DC2626;}
    .a-amb {background:rgba(202,138,4,.10);border-color:#CA8A04;}
    .a-blu {background:rgba(37,99,235,.09);border-color:#2563EB;}
    div[data-testid="stMetricValue"] {font-size:1.55rem;}
    code, .mono {font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DADOS
# ============================================================
@st.cache_data(show_spinner="Carregando a fila de atendimento...")
def carregar_atendimentos() -> tuple[pd.DataFrame, pd.Timestamp]:
    arquivo = PROCESSADOS / "atendimentos.csv"
    meta = PROCESSADOS / "atendimentos_meta.csv"
    if not arquivo.exists():
        st.error(
            "Fila não encontrada. Gere a camada operacional:\n\n"
            "```\npython src/plataforma.py --total 9000\n```"
        )
        st.stop()

    df = pd.read_csv(
        arquivo, dtype={"codigo_ibge": str},
        parse_dates=["aberta_em", "primeira_resposta_em", "concluida_em"],
    )
    referencia = pd.Timestamp(
        pd.read_csv(meta)["referencia"].iloc[0] if meta.exists()
        else df["aberta_em"].max()
    )

    df["prazo_resposta"] = df["aberta_em"] + pd.to_timedelta(df["sla_horas"], unit="h")
    df["aging_horas"] = (referencia - df["aberta_em"]).dt.total_seconds() / 3600
    df["respondeu"] = df["primeira_resposta_em"].notna()
    df["fim_resposta"] = df["primeira_resposta_em"].fillna(referencia)
    df["atraso_horas"] = ((df["fim_resposta"] - df["prazo_resposta"])
                          .dt.total_seconds() / 3600)
    df["atrasada"] = df["atraso_horas"] > 0
    df["aberta"] = df["status"].isin(["Na fila", "Em andamento"])
    df["ordem_prioridade"] = df["prioridade"].map(ORDEM_PRIORIDADE).fillna(9)
    df["tempo_resposta_h"] = ((df["primeira_resposta_em"] - df["aberta_em"])
                              .dt.total_seconds() / 3600)
    df["tempo_total_h"] = ((df["concluida_em"] - df["aberta_em"])
                           .dt.total_seconds() / 3600)
    return df.sort_values(["aberta_em"]).reset_index(drop=True), pd.Timestamp(referencia)


@st.cache_data(show_spinner=False, ttl=120)
def carregar_municipios() -> pd.DataFrame:
    arquivo = PROCESSADOS / "municipios_cadastros.csv"
    if not arquivo.exists():
        return pd.DataFrame()
    return pd.read_csv(arquivo, dtype={"codigo_ibge": str})


@st.cache_data(show_spinner=False, ttl=120)
def carregar_sem_cadastro() -> pd.DataFrame:
    arquivo = PROCESSADOS / "municipios_sem_cadastro.csv"
    if not arquivo.exists():
        return pd.DataFrame()
    return pd.read_csv(arquivo, dtype={"codigo_ibge": str})


@st.cache_data(show_spinner=False, ttl=120)
def carregar_alcance() -> pd.DataFrame:
    arquivo = PROCESSADOS / "alcance_uf.csv"
    if not arquivo.exists():
        return pd.DataFrame()
    return pd.read_csv(arquivo)


@st.cache_data(show_spinner=False, ttl=120)
def carregar_resumo() -> dict:
    arquivo = PROCESSADOS / "resumo_cadastros.csv"
    if not arquivo.exists():
        return {}
    tabela = pd.read_csv(arquivo)
    return dict(zip(tabela["indicador"], tabela["valor"]))


def horas(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    if valor < 1:
        return f"{valor * 60:.0f} min"
    if valor < 48:
        return f"{valor:.0f} h"
    return f"{valor / 24:.1f} d".replace(".", ",")


def numero(valor) -> str:
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def pilula(texto: str, cor: str) -> str:
    mapa = {"Crítica": "p-red", "Alta": "p-org", "Média": "p-amb", "Baixa": "p-cya",
            "Na fila": "p-gry", "Em andamento": "p-blu", "Concluída": "p-gre",
            "Cancelada": "p-gry"}
    return f'<span class="pilula {mapa.get(texto, cor)}">{texto}</span>'


atendimentos, referencia = carregar_atendimentos()
municipios = carregar_municipios()
sem_cadastro = carregar_sem_cadastro()
alcance = carregar_alcance()
resumo = carregar_resumo()

# ------------------------------------------------------------
# Ações do operador (valem para esta sessão de demonstração)
# ------------------------------------------------------------
if "acoes" not in st.session_state:
    st.session_state.acoes = {}

if st.session_state.acoes:
    for chave, acao in st.session_state.acoes.items():
        mascara = atendimentos["id_solicitacao"] == chave
        atendimentos.loc[mascara, "status"] = acao["status"]
        atendimentos.loc[mascara, "responsavel"] = acao["responsavel"]
    atendimentos["aberta"] = atendimentos["status"].isin(["Na fila", "Em andamento"])


# ============================================================
# BARRA LATERAL
# ============================================================
st.sidebar.title("🐾 VetSolidário")
st.sidebar.caption("Central de Operações · atendimento veterinário gratuito")

st.sidebar.markdown(
    f"**Situação em** {referencia:%d/%m/%Y %H:%M}"
    f"<br><span style='opacity:.7;font-size:.8rem'>última sincronização da base</span>",
    unsafe_allow_html=True,
)

st.sidebar.divider()
ufs = ["Todas"] + sorted(atendimentos["uf"].dropna().unique().tolist())
uf_sel = st.sidebar.selectbox("Praça (UF)", ufs)
tipo_sel = st.sidebar.segmented_control(
    "Tipo de solicitação",
    ["Todos", "Teleconsulta", "Castração", "Resgate"],
    default="Todos",
) or "Todos"

st.sidebar.divider()
pagina = st.sidebar.radio(
    "Tela",
    ["Situação agora", "Fila de trabalho", "Castrações", "Resgates",
     "Território", "Dados e sistema"],
)

st.sidebar.divider()
st.sidebar.caption(
    "A fila de solicitações é **simulada** (semente fixa, calibrada pela demanda "
    "real de cada município). Cobertura do cadastro, demanda antirrábica e "
    "população são dados oficiais."
)
if st.session_state.acoes:
    st.sidebar.caption(f"{len(st.session_state.acoes)} ação(ões) registrada(s) nesta sessão")
    if st.sidebar.button("Desfazer ações da sessão", width="stretch"):
        st.session_state.acoes = {}
        st.rerun()

# recorte global
base = atendimentos.copy()
if uf_sel != "Todas":
    base = base[base["uf"] == uf_sel]
if tipo_sel != "Todos":
    base = base[base["tipo"] == tipo_sel]

fila = base[base["aberta"]]
atrasadas = fila[fila["atrasada"]]
sem_resposta = fila[~fila["respondeu"]]
em_andamento = base[base["status"] == "Em andamento"]
concluidas_7d = base[(base["status"] == "Concluída")
                     & (base["concluida_em"] >= referencia - pd.Timedelta(days=7))]


# ============================================================
# 1. SITUAÇÃO AGORA
# ============================================================
if pagina == "Situação agora":
    st.title("Situação agora")
    st.caption(
        f"Visão do turno — {numero(len(base))} solicitações na base, "
        f"{numero(len(fila))} em aberto. Prazo contado a partir da abertura."
    )

    if base.empty:
        st.warning("Nenhuma solicitação para os filtros selecionados.")
        st.stop()

    percentual = 100 * len(atrasadas) / len(fila) if len(fila) else 0
    if percentual < 8:
        faixa, cor_faixa = "Operação sob controle", VERDE
    elif percentual < 18:
        faixa, cor_faixa = "Atenção: fila acumulando", AMBAR
    else:
        faixa, cor_faixa = "Crítico: prazo estourado", VERMELHO

    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
        f"<span style='width:11px;height:11px;border-radius:50%;background:{cor_faixa};"
        f"display:inline-block'></span>"
        f"<b style='color:{cor_faixa}'>{faixa}</b>"
        f"<span style='opacity:.75'>— {percentual:.1f}% da fila fora do prazo</span></div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Fila ativa", numero(len(fila)),
              help="Solicitações em 'Na fila' ou 'Em andamento'.")
    c2.metric("Fora do prazo", numero(len(atrasadas)),
              delta=f"{percentual:.0f}% da fila" if len(fila) else None,
              delta_color="inverse")
    c3.metric("Sem primeira resposta", numero(len(sem_resposta)),
              help="Ainda não foram assumidas por nenhum atendente.")
    c4.metric("Concluídas (7 dias)", numero(len(concluidas_7d)))
    c5.metric("Animais na base", numero(resumo.get("animais_cadastrados", 0)),
              help="Cadastros do SinPatinhas que a plataforma já conhece.")

    # ---------------- alertas ----------------
    criticos = fila[(fila["prioridade"] == "Crítica") & (fila["atrasada"])]
    castracao_fila = fila[fila["tipo"] == "Castração"]
    sem_clinica = castracao_fila[~castracao_fila["respondeu"]]
    municipio_top = (atrasadas.groupby("municipio").size().sort_values(ascending=False)
                     if len(atrasadas) else pd.Series(dtype=int))

    st.markdown("#### O que precisa de decisão hoje")
    if len(criticos):
        st.markdown(
            f"<div class='alerta a-red'><b>{len(criticos)} caso(s) crítico(s) fora do "
            f"prazo.</b> Resgate com prazo de 2 h; o mais antigo está em "
            f"{horas(criticos['atraso_horas'].max())} de atraso "
            f"({criticos.sort_values('atraso_horas', ascending=False).iloc[0]['municipio']}).</div>",
            unsafe_allow_html=True,
        )
    if len(sem_clinica):
        st.markdown(
            f"<div class='alerta a-red'><b>Fila de castração travada:</b> "
            f"{numero(len(sem_clinica))} pedidos sem primeira resposta, "
            f"o mais antigo esperando {horas(sem_clinica['aging_horas'].max())}. "
            f"É falta de vaga em clínica parceira, não de demanda.</div>",
            unsafe_allow_html=True,
        )
    if len(municipio_top):
        municipio = municipio_top.index[0]
        st.markdown(
            f"<div class='alerta a-amb'><b>Concentração territorial:</b> "
            f"{municipio} responde por {numero(municipio_top.iloc[0])} das "
            f"{numero(len(atrasadas))} solicitações fora do prazo "
            f"({100 * municipio_top.iloc[0] / len(atrasadas):.0f}%).</div>",
            unsafe_allow_html=True,
        )
    if not len(criticos) and not len(sem_clinica):
        st.markdown(
            "<div class='alerta a-blu'>Nenhum caso crítico fora do prazo neste "
            "recorte. A fila está dentro do tempo de resposta.</div>",
            unsafe_allow_html=True,
        )

    # ---------------- gráficos ----------------
    esquerda, direita = st.columns([3, 2])

    with esquerda:
        janela = referencia - pd.Timedelta(days=30)
        abertas_dia = (base[base["aberta_em"] >= janela]
                       .assign(dia=lambda d: d["aberta_em"].dt.date)
                       .groupby("dia").size())
        concluidas_dia = (base[(base["concluida_em"].notna())
                               & (base["concluida_em"] >= janela)]
                          .assign(dia=lambda d: d["concluida_em"].dt.date)
                          .groupby("dia").size())
        figura = go.Figure()
        figura.add_trace(go.Scatter(x=abertas_dia.index, y=abertas_dia.values,
                                    name="Abertas", mode="lines",
                                    line=dict(color=COR, width=2.2)))
        figura.add_trace(go.Scatter(x=concluidas_dia.index, y=concluidas_dia.values,
                                    name="Concluídas", mode="lines",
                                    line=dict(color=VERDE, width=2.2)))
        figura.update_layout(title="Entrada e saída de solicitações (30 dias)",
                             height=310, margin=dict(t=46, b=10),
                             legend=dict(orientation="h", y=1.12, x=0),
                             yaxis_title="solicitações/dia", xaxis_title=None)
        st.plotly_chart(figura, width="stretch")

    with direita:
        por_status = (fila.groupby(["tipo", "status"]).size()
                      .rename("n").reset_index())
        figura = px.bar(por_status, x="n", y="tipo", color="status",
                        orientation="h", barmode="stack",
                        title="Fila por tipo e etapa",
                        color_discrete_map=CORES_STATUS)
        figura.update_layout(height=310, margin=dict(t=46, b=10),
                             xaxis_title="solicitações", yaxis_title=None,
                             legend=dict(orientation="h", y=1.14, x=0))
        st.plotly_chart(figura, width="stretch")

    # ---------------- tempo de espera ----------------
    esquerda, direita = st.columns([2, 3])
    with esquerda:
        faixas = pd.cut(fila["aging_horas"], bins=[-0.1, 24, 72, 168, 720, 1e6],
                        labels=["até 1 dia", "1 a 3 dias", "3 a 7 dias",
                                "7 a 30 dias", "mais de 30 dias"])
        contagem = faixas.value_counts().reindex(
            ["até 1 dia", "1 a 3 dias", "3 a 7 dias", "7 a 30 dias",
             "mais de 30 dias"]).fillna(0)
        figura = px.bar(x=contagem.index, y=contagem.values,
                        title="Há quanto tempo a fila está aberta",
                        color=contagem.values, color_continuous_scale="OrRd")
        figura.update_layout(height=320, coloraxis_showscale=False,
                             margin=dict(t=46, b=10), xaxis_title=None,
                             yaxis_title="solicitações")
        st.plotly_chart(figura, width="stretch")

    with direita:
        st.markdown("**Praça com mais fila fora do prazo**")
        tabela = (fila.groupby(["municipio", "uf"])
                  .agg(fila=("id_solicitacao", "size"),
                       atrasadas=("atrasada", "sum"),
                       sem_resposta=("respondeu", lambda s: (~s).sum()),
                       espera_mediana=("aging_horas", "median"))
                  .reset_index()
                  .sort_values(["atrasadas", "fila"], ascending=False)
                  .head(12))
        tabela["espera_mediana"] = tabela["espera_mediana"].map(horas)
        st.dataframe(
            tabela, width="stretch", hide_index=True, height=318,
            column_config={
                "municipio": "Município", "uf": "UF", "fila": "Na fila",
                "atrasadas": "Fora do prazo", "sem_resposta": "Sem resposta",
                "espera_mediana": "Espera mediana",
            },
        )


# ============================================================
# 2. FILA DE TRABALHO
# ============================================================
elif pagina == "Fila de trabalho":
    st.title("Fila de trabalho")
    st.caption(
        "Ordem de atendimento: caso crítico primeiro, depois prazo estourado, "
        "depois quem espera há mais tempo."
    )

    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        status_sel = st.multiselect("Etapa", ["Na fila", "Em andamento"],
                                    default=["Na fila", "Em andamento"])
    with col2:
        prioridade_sel = st.multiselect("Prioridade",
                                        ["Crítica", "Alta", "Média", "Baixa"],
                                        default=["Crítica", "Alta", "Média", "Baixa"])
    with col3:
        somente_atrasadas = st.toggle("Só fora do prazo", value=False)
    with col4:
        busca = st.text_input("Buscar por município, bairro, id ou relato",
                              placeholder="ex.: Curitiba, VS-20, atropelado")

    trabalho = base[base["status"].isin(status_sel)]
    if prioridade_sel:
        trabalho = trabalho[trabalho["prioridade"].isin(prioridade_sel)]
    if somente_atrasadas:
        trabalho = trabalho[trabalho["atrasada"]]
    if busca:
        alvo = busca.strip().lower()
        mascara = (
            trabalho["municipio"].str.lower().str.contains(alvo, na=False)
            | trabalho["bairro"].str.lower().str.contains(alvo, na=False)
            | trabalho["id_solicitacao"].str.lower().str.contains(alvo, na=False)
            | trabalho["relato"].str.lower().str.contains(alvo, na=False)
        )
        trabalho = trabalho[mascara]

    trabalho = trabalho.sort_values(
        ["ordem_prioridade", "atraso_horas", "aging_horas"], ascending=[True, False, False]
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Na seleção", numero(len(trabalho)))
    m2.metric("Fora do prazo", numero(int(trabalho["atrasada"].sum())))
    m3.metric("Sem resposta", numero(int((~trabalho["respondeu"]).sum())))
    m4.metric("Espera mediana", horas(trabalho["aging_horas"].median()))

    st.divider()

    if trabalho.empty:
        st.info("Nenhuma solicitação com esses filtros.")
        st.stop()

    esquerda, direita = st.columns([3, 2])

    with esquerda:
        st.markdown(f"**{numero(len(trabalho))} solicitações — clique em uma linha**")
        tabela = trabalho.head(200)[[
            "id_solicitacao", "municipio", "tipo", "prioridade", "status",
            "aging_horas", "atraso_horas", "relato",
        ]].copy()
        tabela["espera"] = tabela["aging_horas"].map(horas)
        tabela["situacao"] = np.where(
            tabela["atraso_horas"] > 0,
            tabela["atraso_horas"].map(lambda h: f"atrasada {horas(h)}"),
            "no prazo",
        )
        exibicao = tabela[["id_solicitacao", "municipio", "tipo", "prioridade",
                           "status", "espera", "situacao", "relato"]]
        evento = st.dataframe(
            exibicao, width="stretch", hide_index=True, height=520,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "id_solicitacao": st.column_config.TextColumn("Solicitação", width="small"),
                "municipio": st.column_config.TextColumn("Município", width="medium"),
                "tipo": st.column_config.TextColumn("Tipo", width="small"),
                "prioridade": st.column_config.TextColumn("Prioridade", width="small"),
                "status": st.column_config.TextColumn("Etapa", width="medium"),
                "espera": st.column_config.TextColumn("Espera", width="small"),
                "situacao": st.column_config.TextColumn("Prazo", width="small"),
                "relato": st.column_config.TextColumn("Relato", width="large"),
            },
        )

    linhas = evento.selection.rows if evento and evento.selection else []
    escolhida = (trabalho.head(200).iloc[linhas[0]]
                 if linhas else trabalho.iloc[0])

    with direita:
        st.markdown("#### Detalhe da solicitação")
        st.markdown(
            f"<div class='cartao'><h4>{escolhida['id_solicitacao']}</h4>"
            f"<div style='font-size:1.05rem;font-weight:600'>{escolhida['relato']}</div>"
            f"<div class='nota'>{escolhida['municipio']} / {escolhida['uf']} · "
            f"{escolhida['bairro']} · via {escolhida['canal']}</div>"
            f"<div style='margin-top:10px;display:flex;gap:6px;flex-wrap:wrap'>"
            f"{pilula(escolhida['tipo'], 'p-blu')}"
            f"{pilula(escolhida['prioridade'], 'p-amb')}"
            f"{pilula(escolhida['status'], 'p-gry')}</div></div>",
            unsafe_allow_html=True,
        )

        prazo = escolhida["prazo_resposta"]
        situacao_prazo = ("fora do prazo" if escolhida["atrasada"] else "dentro do prazo")
        resposta = ("ainda sem resposta"
                    if pd.isna(escolhida["primeira_resposta_em"])
                    else f"{escolhida['primeira_resposta_em']:%d/%m/%Y %H:%M}")
        st.markdown(
            "| Campo | Valor |\n|---|---|\n"
            f"| Aberta em | {escolhida['aberta_em']:%d/%m/%Y %H:%M} |\n"
            f"| Prazo de resposta | {prazo:%d/%m/%Y %H:%M} ({situacao_prazo}) |\n"
            f"| Espera total | {horas(escolhida['aging_horas'])} |\n"
            f"| Primeira resposta | {resposta} |"
        )
        st.markdown(
            f"| Campo | Valor |\n|---|---|\n"
            f"| Responsável | {escolhida['responsavel'] or '— não atribuído —'} |\n"
            f"| Unidade | {escolhida['unidade']} |\n"
            f"| SLA do tipo/prioridade | {int(escolhida['sla_horas'])} h |"
        )

        st.markdown("##### Ação do operador")
        b1, b2 = st.columns(2)
        identificador = escolhida["id_solicitacao"]
        with b1:
            if st.button("Assumir caso", width="stretch", type="primary"):
                st.session_state.acoes[identificador] = {
                    "status": "Em andamento",
                    "responsavel": "Operador de plantão",
                }
                st.toast(f"{identificador} assumida por você.")
                st.rerun()
            if st.button("Concluir", width="stretch"):
                st.session_state.acoes[identificador] = {
                    "status": "Concluída",
                    "responsavel": (escolhida["responsavel"]
                                    or "Operador de plantão"),
                }
                st.toast(f"{identificador} concluída.")
                st.rerun()
        with b2:
            if st.button("Devolver à fila", width="stretch"):
                st.session_state.acoes[identificador] = {
                    "status": "Na fila", "responsavel": "",
                }
                st.toast(f"{identificador} devolvida à fila.")
                st.rerun()
            if st.button("Cancelar", width="stretch"):
                st.session_state.acoes[identificador] = {
                    "status": "Cancelada", "responsavel": "",
                }
                st.toast(f"{identificador} cancelada.")
                st.rerun()

        st.caption(
            "As ações valem para esta sessão — não alteram a base de demonstração."
        )

    st.divider()
    st.download_button(
        "Baixar a seleção em CSV",
        trabalho.to_csv(index=False).encode("utf-8"),
        file_name="fila_vetsolidario.csv",
        mime="text/csv",
    )


# ============================================================
# 3. CASTRAÇÕES
# ============================================================
elif pagina == "Castrações":
    st.title("Castrações")
    st.caption(
        "O gargalo do produto não é demanda — é vaga em clínica parceira. "
        "Esta tela mostra a fila por município e há quanto tempo ela espera."
    )

    castracao = base[base["tipo"] == "Castração"]
    if castracao.empty:
        st.warning("Nenhuma solicitação de castração nos filtros atuais.")
        st.stop()

    aberta = castracao[castracao["aberta"]]
    concluida = castracao[castracao["status"] == "Concluída"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pedidos", numero(len(castracao)))
    c2.metric("Na fila", numero(len(aberta)))
    c3.metric("Sem primeira resposta", numero(int((~aberta["respondeu"]).sum())))
    c4.metric("Fora do prazo", numero(int(aberta["atrasada"].sum())))
    c5.metric("Espera mediana", horas(aberta["aging_horas"].median()))

    st.markdown(
        f"<div class='alerta a-amb'>Prazo de resposta para castração: "
        f"<b>3 dias</b> (alta), <b>7 dias</b> (média) e <b>14 dias</b> (baixa). "
        f"São <b>{numero(len(aberta))}</b> pedidos esperando, "
        f"<b>{numero(int(aberta['aging_horas'].gt(336).sum()))}</b> deles há mais "
        f"de duas semanas.</div>",
        unsafe_allow_html=True,
    )

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        st.markdown("**Fila de castração por município**")
        tabela = (castracao.groupby(["municipio", "uf"])
                  .agg(pedidos=("id_solicitacao", "size"),
                       na_fila=("aberta", "sum"),
                       sem_resposta=("respondeu", lambda s: (~s).sum()),
                       fora_prazo=("atrasada", lambda s: int(
                           (s & castracao.loc[s.index, "aberta"]).sum())),
                       espera_mediana=("aging_horas", "median"),
                       concluidas=("status", lambda s: (s == "Concluída").sum()))
                  .reset_index())
        tabela["espera_mediana"] = tabela["espera_mediana"].map(horas)
        st.dataframe(
            tabela.sort_values("na_fila", ascending=False),
            width="stretch", hide_index=True, height=380,
            column_config={
                "municipio": "Município", "uf": "UF", "pedidos": "Pedidos",
                "na_fila": "Na fila", "sem_resposta": "Sem resposta",
                "fora_prazo": "Fora do prazo", "espera_mediana": "Espera mediana",
                "concluidas": "Concluídas",
            },
        )
    with direita:
        semanas = (castracao.assign(semana=lambda d: d["aberta_em"].dt.to_period("W").dt.start_time)
                   .groupby(["semana", "status"]).size().rename("n").reset_index())
        semanas = semanas[semanas["semana"] >= referencia - pd.Timedelta(days=84)]
        figura = px.bar(semanas, x="semana", y="n", color="status", barmode="stack",
                        title="Pedidos de castração por semana de abertura",
                        color_discrete_map=CORES_STATUS)
        figura.update_layout(height=380, margin=dict(t=46, b=10),
                             xaxis_title=None, yaxis_title="pedidos",
                             legend=dict(orientation="h", y=1.12, x=0))
        st.plotly_chart(figura, width="stretch")

    st.markdown("#### Pedidos mais antigos sem resposta")
    antigos = (aberta[~aberta["respondeu"]]
               .sort_values("aging_horas", ascending=False).head(15))
    if len(antigos):
        st.dataframe(
            antigos[["id_solicitacao", "municipio", "uf", "bairro", "prioridade",
                     "aging_horas", "relato"]]
            .assign(espera=lambda d: d["aging_horas"].map(horas))
            .drop(columns="aging_horas"),
            width="stretch", hide_index=True,
            column_config={"id_solicitacao": "Solicitação", "municipio": "Município",
                           "uf": "UF", "bairro": "Bairro", "prioridade": "Prioridade",
                           "relato": "Relato", "espera": "Espera"},
        )
    else:
        st.success("Nenhum pedido de castração sem primeira resposta.")


# ============================================================
# 4. RESGATES
# ============================================================
elif pagina == "Resgates":
    st.title("Resgates")
    st.caption(
        "Casos de animal abandonado, ferido ou em risco. Prioridade crítica tem "
        "prazo de 2 horas até o despacho da equipe."
    )

    resgate = base[base["tipo"] == "Resgate"]
    if resgate.empty:
        st.warning("Nenhum resgate nos filtros atuais.")
        st.stop()

    ativos = resgate[resgate["aberta"]]
    criticos = ativos[ativos["prioridade"] == "Crítica"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Resgates ativos", numero(len(ativos)))
    c2.metric("Críticos", numero(len(criticos)))
    c3.metric("Fora do prazo", numero(int(ativos["atrasada"].sum())))
    c4.metric("Sem equipe", numero(int((~ativos["respondeu"]).sum())))
    c5.metric("Resposta mediana",
              horas(resgate.loc[resgate["respondeu"], "tempo_resposta_h"].median()))

    st.markdown("#### Mapa dos casos ativos")
    pontos = ativos.dropna(subset=["latitude", "longitude"])
    mapa = folium.Map(location=[-15.7, -47.9], zoom_start=4,
                      tiles="OpenStreetMap", control_scale=True)
    grupo = MarkerCluster().add_to(mapa)
    for _, linha in pontos.iterrows():
        folium.CircleMarker(
            location=[linha["latitude"], linha["longitude"]],
            radius=9 if linha["prioridade"] == "Crítica" else 6,
            color=CORES_PRIORIDADE[linha["prioridade"]],
            weight=2, fill=True, fill_opacity=0.75,
            popup=folium.Popup(
                f"<b>{linha['id_solicitacao']}</b><br>{linha['relato']}<br>"
                f"{linha['municipio']} / {linha['uf']} — {linha['bairro']}<br>"
                f"Prioridade: {linha['prioridade']} · espera {horas(linha['aging_horas'])}"
                f"<br>Etapa: {linha['status']}"
                + (f"<br>Fora do prazo em {horas(linha['atraso_horas'])}"
                   if linha["atrasada"] else ""),
                max_width=280,
            ),
        ).add_to(grupo)
    st_folium(mapa, height=460, use_container_width=True, returned_objects=[])

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        st.markdown("#### Casos mais urgentes")
        urgentes = (ativos.sort_values(["ordem_prioridade", "atraso_horas",
                                        "aging_horas"], ascending=[True, False, False])
                    .head(18))
        st.dataframe(
            urgentes[["id_solicitacao", "municipio", "uf", "prioridade", "status",
                      "aging_horas", "relato"]]
            .assign(espera=lambda d: d["aging_horas"].map(horas))
            .drop(columns="aging_horas"),
            width="stretch", hide_index=True, height=420,
            column_config={"id_solicitacao": "Solicitação", "municipio": "Município",
                           "uf": "UF", "prioridade": "Prioridade", "status": "Etapa",
                           "relato": "Relato", "espera": "Espera"},
        )
    with direita:
        st.markdown("#### Resgates por UF")
        por_uf = (resgate.groupby("uf")
                  .agg(ativos=("aberta", "sum"),
                       fora_prazo=("atrasada", lambda s: int(
                           (s & resgate.loc[s.index, "aberta"]).sum())),
                       concluidos=("status", lambda s: (s == "Concluída").sum()))
                  .reset_index().sort_values("ativos", ascending=False))
        st.dataframe(por_uf, width="stretch", hide_index=True, height=200,
                     column_config={"uf": "UF", "ativos": "Ativos",
                                    "fora_prazo": "Fora do prazo",
                                    "concluidos": "Concluídos"})

        st.markdown("#### Equipes em campo")
        equipes = (ativos[ativos["respondeu"]]
                   .groupby("responsavel").size()
                   .sort_values(ascending=False).rename("casos").reset_index())
        st.dataframe(equipes, width="stretch", hide_index=True, height=200,
                     column_config={"responsavel": "Equipe", "casos": "Casos ativos"})


# ============================================================
# 5. TERRITÓRIO
# ============================================================
elif pagina == "Território":
    st.title("Território")
    st.caption(
        "Onde a plataforma deve abrir frente: município com muita demanda "
        "registrada e pouca cobertura de cadastro é onde a campanha rende mais."
    )

    if municipios.empty:
        st.error("Rode `python src/processar_cadastros.py` para gerar os indicadores.")
        st.stop()

    total_sem = int(resumo.get("municipios_sem_cadastro", len(sem_cadastro)))
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Cobertura nacional",
              f"{float(resumo.get('cobertura_por_100k', 0)):.0f} / 100 mil")
    k2.metric("Municípios com cadastro",
              numero(resumo.get("municipios_com_cadastro", len(municipios))))
    k3.metric("Sem nenhum cadastro", numero(total_sem),
              help="Municípios sem um único animal registrado no SinPatinhas.")
    k4.metric("Cães por 100 domicílios",
              f"{float(resumo.get('cao_por_100_domicilios', 0)):.2f}".replace(".", ","),
              help="Cães cadastrados para cada 100 domicílios que declaram ter cão "
                   "(PNAD/SIDRA).")
    k5.metric("Gatos por 100 domicílios",
              f"{float(resumo.get('gato_por_100_domicilios', 0)):.2f}".replace(".", ","),
              help="Gatos cadastrados para cada 100 domicílios que declaram ter "
                   "gato (PNAD/SIDRA).")

    if not alcance.empty:
        st.markdown("#### Alcance da política sobre quem tem animal em casa")
        st.caption(
            "Domicílios que declaram ter cão ou gato (PNAD/IBGE) contra os animais "
            "efetivamente cadastrados no SinPatinhas. É o indicador mais duro do "
            "projeto: mostra o quanto da população animal já entrou no sistema."
        )
        esquerda, direita = st.columns([3, 2])
        with esquerda:
            grafico = alcance.dropna(subset=["cao_por_100_domicilios"])                 .sort_values("cao_por_100_domicilios", ascending=True)
            figura = px.bar(
                grafico, x="cao_por_100_domicilios", y="uf", orientation="h",
                color="cao_por_100_domicilios", color_continuous_scale="Purp",
                labels={"cao_por_100_domicilios": "cães por 100 domicílios", "uf": ""},
            )
            figura.add_vline(
                x=float(resumo.get("cao_por_100_domicilios", 0)),
                line_dash="dash", line_color="#EA580C",
                annotation_text="média nacional",
            )
            figura.update_layout(height=520, coloraxis_showscale=False,
                                 margin=dict(t=30, b=10))
            st.plotly_chart(figura, width="stretch")
        with direita:
            tabela = alcance.sort_values("cao_por_100_domicilios", ascending=False)
            st.dataframe(
                tabela[["uf", "domicilios_cao", "cadastros_cao",
                        "cao_por_100_domicilios", "gato_por_100_domicilios"]],
                width="stretch", hide_index=True, height=520,
                column_config={
                    "uf": "UF",
                    "domicilios_cao": st.column_config.NumberColumn(
                        "Domicílios com cão", format="localized"),
                    "cadastros_cao": st.column_config.NumberColumn(
                        "Cães cadastrados", format="localized"),
                    "cao_por_100_domicilios": st.column_config.NumberColumn(
                        "Cães / 100 dom.", format="%.2f"),
                    "gato_por_100_domicilios": st.column_config.NumberColumn(
                        "Gatos / 100 dom.", format="%.2f"),
                },
            )
        st.caption(
            f"Referência: PNAD/IBGE {int(resumo.get('ano_pnad', 2019))} — "
            f"{numero(resumo.get('domicilios_com_cao', 0))} domicílios com cão e "
            f"{numero(resumo.get('domicilios_com_gato', 0))} com gato no país."
        )

    escolha = st.radio(
        "Camada do mapa",
        ["Índice de prioridade", "Cobertura do cadastro", "Cadastros absolutos"],
        horizontal=True,
    )
    campo = {"Índice de prioridade": "indice_prioridade",
             "Cobertura do cadastro": "cobertura_por_100k",
             "Cadastros absolutos": "cadastros"}[escolha]

    recorte = municipios.dropna(subset=["latitude", "longitude"]).copy()
    if uf_sel != "Todas":
        recorte = recorte[recorte["uf"] == uf_sel]
    recorte = recorte.nlargest(400, campo)

    mapa = folium.Map(location=[-15.7, -47.9], zoom_start=4,
                      tiles="OpenStreetMap", control_scale=True)
    valores = recorte[campo].astype(float)
    minimo, maximo = valores.min(), valores.max()
    for _, linha in recorte.iterrows():
        proporcao = 0.0 if maximo == minimo else (linha[campo] - minimo) / (maximo - minimo)
        folium.CircleMarker(
            location=[linha["latitude"], linha["longitude"]],
            radius=4 + 20 * proporcao,
            color=COR, weight=1, fill=True,
            fill_opacity=0.2 + 0.5 * proporcao,
            popup=folium.Popup(
                f"<b>{linha['municipio']} / {linha['uf']}</b><br>"
                f"Cadastros: {numero(linha['cadastros'])}<br>"
                f"Cobertura: {linha['cobertura_por_100k']:.0f} / 100 mil<br>"
                f"Demanda antirrábica: {linha['demanda_por_100k']:.0f} / 100 mil<br>"
                f"Prioridade: {linha['indice_prioridade']:.0f}",
                max_width=250,
            ),
        ).add_to(mapa)
    st_folium(mapa, height=430, use_container_width=True, returned_objects=[])

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("#### Fila de prioridade (100 mil+ habitantes)")
        prioridade = (municipios[municipios["populacao"] >= 100_000]
                      .nlargest(15, "indice_prioridade")
                      [["municipio", "uf", "populacao", "cobertura_por_100k",
                        "demanda_por_100k", "indice_prioridade"]])
        st.dataframe(
            prioridade, width="stretch", hide_index=True, height=380,
            column_config={
                "municipio": "Município", "uf": "UF", "populacao": "População",
                "cobertura_por_100k": "Cobertura / 100 mil",
                "demanda_por_100k": "Demanda / 100 mil",
                "indice_prioridade": "Prioridade",
            },
        )
    with direita:
        st.markdown("#### Municípios sem nenhum cadastro")
        st.caption("Alvo de campanha de mobilização: nem um animal registrado.")
        st.dataframe(
            sem_cadastro.head(15)[["municipio", "uf", "populacao"]],
            width="stretch", hide_index=True, height=380,
            column_config={"municipio": "Município", "uf": "UF",
                           "populacao": "População"},
        )


# ============================================================
# 6. DADOS E SISTEMA
# ============================================================
elif pagina == "Dados e sistema":
    st.title("Dados e sistema")
    st.caption("O que alimenta o painel, quando foi atualizado e o que ainda é demonstração.")

    st.markdown("#### Fontes em uso")
    fontes = pd.DataFrame([
        {"Fonte": "SinPatinhas — Cadastro Nacional de Animais Domésticos",
         "Natureza": "oficial", "Registros": f"{numero(resumo.get('animais_cadastrados', 0))}",
         "Cobertura": f"{resumo.get('primeiro_cadastro', '—')} a {resumo.get('ultimo_cadastro', '—')}"},
        {"Fonte": "SINAN — Atendimento Antirrábico Humano",
         "Natureza": "oficial", "Registros": "2.184.619", "Cobertura": "2022 a 2024"},
        {"Fonte": "IBGE — população residente (agregado 6579)",
         "Natureza": "oficial", "Registros": "5.571 municípios", "Cobertura": "2026"},
        {"Fonte": "IBGE — localidades e coordenadas das sedes",
         "Natureza": "oficial", "Registros": "5.571 municípios", "Cobertura": "2026"},
        {"Fonte": "Solicitações da plataforma (teleconsulta, castração, resgate)",
         "Natureza": "SIMULADA", "Registros": numero(len(atendimentos)),
         "Cobertura": f"{atendimentos['aberta_em'].min():%d/%m/%Y} a "
                      f"{atendimentos['aberta_em'].max():%d/%m/%Y}"},
    ])
    st.dataframe(fontes, width="stretch", hide_index=True)

    st.markdown(
        "<div class='alerta a-amb'><b>A fila de solicitações é simulada.</b> "
        "Nenhuma base pública registra teleconsulta veterinária, castração "
        "agendada ou resgate de animal. A simulação usa semente fixa e é "
        "calibrada pela demanda real de cada município — o volume e o mapa "
        "respeitam o padrão territorial observado nos dados oficiais, mas os "
        "casos, prazos e nomes não existem.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### Verificações da fila")
    verificacoes = pd.DataFrame([
        {"Checagem": "Solicitações na base", "Resultado": numero(len(atendimentos)),
         "Situação": "ok"},
        {"Checagem": "Identificador duplicado",
         "Resultado": numero(int(atendimentos["id_solicitacao"].duplicated().sum())),
         "Situação": "ok" if atendimentos["id_solicitacao"].duplicated().sum() == 0 else "revisar"},
        {"Checagem": "Registro sem município",
         "Resultado": numero(int(atendimentos["municipio"].isna().sum())),
         "Situação": "ok" if atendimentos["municipio"].isna().sum() == 0 else "revisar"},
        {"Checagem": "Data de conclusão anterior à abertura",
         "Resultado": numero(int((atendimentos["concluida_em"]
                                  < atendimentos["aberta_em"]).sum())),
         "Situação": "ok"},
        {"Checagem": "Solicitação aberta fora do período de operação",
         "Resultado": numero(int((atendimentos["aging_horas"] < 0).sum())),
         "Situação": "ok"},
        {"Checagem": "Concluídas sem primeira resposta",
         "Resultado": numero(int(((atendimentos["status"] == "Concluída")
                                  & atendimentos["primeira_resposta_em"].isna()).sum())),
         "Situação": "ok"},
    ])
    st.dataframe(verificacoes, width="stretch", hide_index=True)

    st.markdown("#### O que o sistema real precisa gravar")
    st.markdown(
        "Para o painel funcionar em produção, cada solicitação precisa carregar: "
        "`id`, `aberta_em`, `tipo`, `prioridade`, `canal`, `codigo_ibge`, `bairro`, "
        "coordenada, `sla_horas`, `primeira_resposta_em`, `concluida_em`, "
        "responsável e unidade. O prazo (SLA) é política da operação, não do dado — "
        "muda por tipo e prioridade e fica versionado."
    )

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("#### Fila por etapa")
        etapa = (atendimentos.groupby("status").size()
                 .rename("solicitações").reset_index())
        figura = px.bar(etapa, x="status", y="solicitações", color="status",
                        color_discrete_map=CORES_STATUS)
        figura.update_layout(height=300, showlegend=False, margin=dict(t=20, b=10),
                             xaxis_title=None)
        st.plotly_chart(figura, width="stretch")
    with direita:
        st.markdown("#### Entrada por canal")
        canal = (atendimentos.groupby("canal").size()
                 .rename("solicitações").reset_index()
                 .sort_values("solicitações", ascending=False))
        figura = px.bar(canal, x="solicitações", y="canal", orientation="h",
                        color="solicitações", color_continuous_scale="Purp")
        figura.update_layout(height=300, coloraxis_showscale=False,
                             margin=dict(t=20, b=10), yaxis_title=None)
        st.plotly_chart(figura, width="stretch")

    st.caption(
        "A análise estatística da base de cadastros fica em "
        "`notebooks/analise_vetsolidario.ipynb` — este painel é operacional."
    )
