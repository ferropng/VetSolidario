# Fontes de dados — VetSolidário

Inventário das fontes usadas, com o caminho exato de acesso, o que foi verificado
e o que ficou de fora.

---

## 1. Quadro-resumo

| # | Fonte | Papel no projeto | Situação |
|---|---|---|---|
| 1 | **SinPatinhas — Cadastro Nacional de Animais Domésticos** | base principal | **em uso** (15/04–02/12/2025) |
| 2 | IBGE — estimativa populacional (API) | denominador da cobertura | **em uso** |
| 3 | IBGE — localidades e malhas (API) | nome, UF, região, geometria | **em uso** (dimensão municipal) |
| 3b | **PNAD/SIDRA 4930 e 4931** — domicílios com cão e com gato | denominador da política (alcance) | **em uso** (2019, por UF e capitais) |
| 4 | SINAN — Atendimento Antirrábico Humano | demanda por atendimento (camada secundária) | **em uso** (2022–2024) |
| 5 | SINAN — Esporotricose | zoonose felina | disponível, não usado |
| 6 | Camada operacional da plataforma | teleconsulta, castração, resgate | **sintética, rotulada** |

---

## 2. SinPatinhas — fonte principal

**O que é.** O Cadastro Nacional de Animais Domésticos, criado pela **Lei
15.046/2024** e regulamentado pelo **Decreto 12.439/2025**, mantido pelo
Ministério do Meio Ambiente. Foco em controle populacional: castração e
microchipagem de cães e gatos.

| Item | Valor |
|---|---|
| Publicação | Base dos Dados — `basedosdados.br_mma_sinpatinhas.microdados` |
| Acesso | endpoint público de download em CSV comprimido |
| URL | `https://basedosdados.org/api/tables/downloadTable?p=…&q=…&d=…&s=…` (parâmetros em base64: dataset, tabela, tratado, gratuito) |
| Página | https://basedosdados.org/dataset/b8e72d64-5416-4a6e-a796-b47a0a600ddc?table=cccdfe78-93c0-454f-a060-1dfc341b2575 |
| Tamanho | ~8 MB comprimido · 48,8 MB descomprimido |
| Registros | **930.442** (uma linha por animal cadastrado) |
| Colunas | 7 — `data_cadastro`, `id_animal`, `id_municipio`, `especie`, `idade`, `sexo`, `cor_pelagem` |
| Cobertura temporal | 15/04/2025 a 02/12/2025 |
| Cobertura espacial | Brasil — 5.397 municípios com registro |
| Sigilo | **sem dado pessoal**: a versão publicada não traz nome, CPF, endereço nem contato do tutor; apenas o município |

**Nível de observação:** animal. `id_animal` é o identificador único (gerado pela
Base dos Dados); não há repetição.

**Como o projeto acessa:** `src/sinpatinhas.py` baixa o CSV comprimido por esse
endpoint, valida a integridade do gzip e cacheia em
`dados/brutos/sinpatinhas_microdados.csv.gz`. Não é necessário conta no Google
Cloud nem BigQuery.

> Limite importante: a base é **fotografia de uma política nova** (nove meses).
> O volume por município mede adesão ao cadastro, não população animal real.

## 3. IBGE

### 3.1 Estimativa populacional (em uso)

```
https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/variaveis/9324?localidades=N6[all]
```
- agregado **6579**, variável **9324** — população residente estimada
- **5.571 municípios**, referência 2026, sem token, retorno em **gzip**
- cache: `dados/brutos/populacao_ibge.csv`
- uso: denominador de todas as taxas por 100 mil habitantes

### 3.2 Localidades (em uso)

```
https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}
```
- nome, microrregião, mesorregião, UF
- atenção: código IBGE tem 7 dígitos, o sistema de saúde usa 6 → `zfill(6)`

### 3.3 Malhas territoriais (mapeada, não usada)

```
https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}?formato=application/vnd.geo+json
```
- responde 200 com GeoJSON (24,7 KB para São Paulo)
- serviria para mapa coroplético; hoje o mapa usa círculo por coordenada da sede

### 3.4 PNAD — domicílios com cão e com gato (em uso)

As duas tabelas que dão o **denominador animal** do projeto. A PNAD investiga
quantos domicílios brasileiros têm cão e gato — é o único dado oficial que se
aproxima de "quantos animais existem", e permite medir o alcance real do cadastro.

| Item | Valor |
|---|---|
| Tabela | **4930** — Domicílios com algum cachorro · **4931** — Domicílios com algum gato |
| Página | https://sidra.ibge.gov.br/tabela/4930 · https://sidra.ibge.gov.br/tabela/4931 |
| API | `https://apisidra.ibge.gov.br/values/t/4930/n3/all/v/5176,5180/p/2019` |
| Variáveis | 5176/5184 = domicílios (mil) · 5180/5188 = percentual do total de domicílios · 5179/5187 = coeficiente de variação |
| Anos | **2013 e 2019** |
| Níveis | UF (27) e **município apenas para capitais** — fora das capitais a API devolve `...` |
| Brasil 2019 | **33.754.348** domicílios com cão · **14.143.568** com gato |

**Limite metodológico:** amostra da PNAD não é representativa em nível municipal
fora das capitais, e os valores por UF são estimativas com intervalo de confiança
de 95% publicado na própria tabela. Por isso o alcance do projeto é comparado por
UF, não por município.

**Indicador derivado** (`dados/processados/alcance_uf.csv`):

```
cães por 100 domicílios com cão  = 100 × cães cadastrados / domicílios com cão
```

Nacional: **1,74** cão e **2,41** gatos por 100 domicílios. DF lidera (3,65), MT
está na lanterna (0,85).

### 3.5 Dimensão municipal (em uso)

`src/dim_municipios.py` — 5.571 municípios com nome, UF, região intermediária e
latitude/longitude da sede (módulo herdado do projeto CareView, derivado das
malhas do IBGE).

---

## 4. SINAN — Atendimento Antirrábico Humano (camada secundária)

Usada para medir **demanda por atendimento** e cruzar com a cobertura do
cadastro. Toda pessoa agredida por animal potencialmente transmissor da raiva é
de notificação compulsória.

| Item | Valor |
|---|---|
| Acesso | FTP `ftp.datasus.gov.br` → `/dissemin/publicos/SINAN/DADOS/FINAIS` |
| Arquivos | `ANTRBR22.dbc` 27,8 MB · `ANTRBR23.dbc` 30,9 MB · `ANTRBR24.dbc` 31,8 MB |
| Registros | 688.125 (2022) · 755.150 (2023) · 779.311 (2024) = **2.222.586** brutos |
| Após limpeza | **2.184.619** (37.967 duplicados removidos) |
| Campos | 79 no arquivo, 20 usados |
| Granularidade | notificação individual → município de residência |

Campos usados: `ID_MN_RESI` (município), `ANIMAL` (espécie agressora),
`TRA_INTERR` (abandono do esquema), `DT_SIN_PRI`/`ANT_DT_EXP` (tempo até o
atendimento), `ANT_PROFUN` (gravidade).

Arquivo derivado: `dados/processados/municipios_indicadores.csv`.

## 5. SINAN — Esporotricose (ESPO)

Zoonose fúngica transmitida por gatos: `ESPOBR20/21/22.dbc`, **20.557**
registros (2020–2022). Baixada e processada, ainda não incorporada ao dashboard.

## 6. Camada operacional da plataforma — **sintética**

Teleconsulta, castração e resgate **não existem como dado público**. São gerados
localmente:

| Item | Valor |
|---|---|
| Script | `src/plataforma.py` |
| Volume | 12.000 solicitações |
| Semente | 42 (reprodutível) |
| Calibração | nº de solicitações do município ∝ atendimentos antirrábicos reais |
| Rótulo | aviso explícito no app, no README e no notebook |

---

## 7. Fontes mapeadas e descartadas

| Fonte | Status verificado | Motivo |
|---|---|---|
| `dados.gov.br` — API de conjuntos de dados | 401 sem token | exige cadastro e token |
| `dados.prefeitura.sp.gov.br` — CKAN | desafio F5/JS no `curl` | precisaria de navegador; sem padrão entre prefeituras |
| IBGE SIDRA (renda, saneamento) | API responde, combinação tabela/variável a validar | próximo passo para controlar confundidores |
| DATASUS CNES | disponível no FTP | cadastro de estabelecimentos de saúde não cobre clínica veterinária |
| Portais de BH, DF, Campinas, Rio | 403 / 404 / sem resposta | sem série histórica comparável |

---

## 8. Como reproduzir

```bash
python src/processar_antr.py        # opcional — demanda (FTP DATASUS, ~3 min)
python src/processar_cadastros.py   # baixa o SinPatinhas e gera os indicadores
python src/pnad_animais.py          # domicílios com cão/gato (SIDRA)
python src/resumo.py                # KPIs e alcance sobre domicílios
python src/plataforma.py --total 9000
streamlit run app.py
```

| Arquivo gerado | Tamanho | Conteúdo |
|---|---|---|
| `dados/processados/cadastros.parquet` | 10 MB | 928.665 cadastros limpos com município, UF e coordenadas |
| `dados/processados/municipios_cadastros.csv` | 1,0 MB | 5.397 municípios com cobertura e índice de prioridade |
| `dados/processados/serie_mensal_cadastros.csv` | — | série mensal de cadastros |
| `dados/processados/perfil_cadastros.csv` | — | faixa etária × espécie × sexo |
| `dados/processados/municipios_indicadores.csv` | 0,6 MB | indicadores do SINAN (demanda) |
| `dados/processados/domicilios_animais_uf.csv` | — | domicílios com cão/gato por UF (2013 e 2019) |
| `dados/processados/domicilios_animais_capitais.csv` | — | mesmo dado para 26 capitais |
| `dados/processados/alcance_uf.csv` | — | cães e gatos cadastrados por 100 domicílios |
| `dados/processados/atendimentos.csv` | 2,3 MB | 9.000 solicitações simuladas com ciclo completo |

---

## 9. Como citar na proposta executiva

> BRASIL. Ministério do Meio Ambiente. **SinPatinhas — Cadastro Nacional de
> Animais Domésticos** (Lei nº 15.046/2024; Decreto nº 12.439/2025). Microdados
> tratados. Base dos Dados, 2026. Disponível em:
> https://basedosdados.org/dataset/b8e72d64-5416-4a6e-a796-b47a0a600ddc.
>
> INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA. **Estimativas de população
> residente — agregado 6579**. Rio de Janeiro: IBGE, 2026. Disponível em:
> https://servicodados.ibge.gov.br/api/v3/agregados/6579.
>
> INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA. **PNAD — Domicílios com algum
> cachorro (tabela 4930) e Domicílios com algum gato (tabela 4931)**. Rio de
> Janeiro: IBGE, 2019. Disponível em: https://sidra.ibge.gov.br/tabela/4930.
>
> BRASIL. Ministério da Saúde. **SINAN — Atendimento Antirrábico Humano,
> 2022–2024**. Microdados. Brasília: DATASUS, 2026. Disponível em:
> ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS.
