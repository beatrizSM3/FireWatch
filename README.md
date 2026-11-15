# FireWatch — Partes A (Dados) e B (Harmonização e indicadores)

Este repositório tem as entregas das **Partes A e B do plano dividido**. A Parte A transformou os 28,4 milhões de focos do FIRMS e os shapefiles de UCs e TIs em arquivos limpos. A Parte B harmonizou os satélites numa série única (**CDeV**) e escreveu as **funções que calculam tudo que o app mostra**.

**Você não precisa rodar nada.** Os arquivos de `saida/` já estão no repositório: clonou, usou.

> **Pessoa C (app):** leia as seções 1, 2, 4 e 5. Tudo que o app precisa está em `firewatch/carregar.py` (busca os dados de uma área) e `firewatch/indicadores.py` (calcula). Você **não calcula nada no app**.

---

## 1. Como começar

```bash
git clone https://github.com/beatrizSM3/FireWatch.git
cd FireWatch
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Para conferir se recebeu tudo certo (≈ 5 s):

```bash
./rodar.sh -m pytest tests -q      # 31 testes: Parte A (15) + Parte B (16)
```

> O código usa a **API do DuckDB 2.x**. Com o DuckDB 1.x, algumas funções dão erro.

---

## 2. O que tem em `saida/`

| Arquivo | Parte | Uma linha é | Linhas | Usado por |
|---|---|---|---|---|
| `observacoes/ano=AAAA/parte-MM.parquet` | A | um foco (um arquivo por mês) | 25.623.084 | C (CSV dos focos), D |
| `disponibilidade.parquet` | A | um dia: status de cada satélite e a `referencia` | 2.875 | B, C |
| `fontes_fixas.parquet` | A | uma célula de fonte fixa (indústria/mar) | 28.118 | A |
| `celulas_base.parquet` | A | célula de 1 km × dia, por satélite (sem harmonizar) | 10.452.862 | B |
| `territorios.geojson` | A | um território (UC ou TI do Cerrado) | 811 | C |
| `celula_territorio.parquet` | A | célula × território (`dentro` / `entorno`) | 1.131.688 | B, C |
| **`celulas_dia.parquet`** | **B** | **célula × dia, harmonizada (CDeV). O arquivo que o app usa** | 10.452.862 | **C**, D |
| `fatores.parquet` | B | fator MODIS→VIIRS por mês × região de 1° | 9.792 | C (mapa), D |
| `fatores_agregados.csv` | B | fator do Brasil e do Cerrado por mês | 24 | D |
| `regioes.geojson` | B | uma região de 1° × 1° | 816 | C (opcional) |
| `deriva.csv` | B | ano × mês × área: erro do MODIS calibrado | 168 | C ("ver por sensor"), D |
| **`alerta_territorios.parquet`** | **B** | **um território com área ≥ 10 km²: o painel de alerta** | 363 | **C** |
| `mif_grupos.csv` | B | grupo de território × data de corte × ano: fração tardia | 105 | D |

Período: **01/01/2019 a 14/11/2026** (data local, UTC−3). Os CSVs e GeoJSONs são pequenos e vão para o Git; o `celulas_dia.parquet` tem 56 MB.

---

## 3. O que a Parte B fez

### 3.1 Harmonização em duas camadas (seção 6 do PLANO2)

1. **Mesma régua (Parte A):** célula-dia de 1 km. Sete pixels VIIRS ou um pixel MODIS no mesmo quadrado no mesmo dia contam **1**.
2. **Mesma escala (Parte B):** o MODIS ainda vê menos. O **fator** `f(mês, região)` = mediana, nos anos de calibração **2019–2022**, de `células-dia VIIRS ÷ células-dia MODIS`, só em dias em que os dois estavam `ok`. Região = quadrado de 1° × 1°. Se a região tem menos de 200 células-dia MODIS no período (ou menos de 2 anos), usa o fator do **Cerrado** ou o **nacional** do mesmo mês.

**Fatores medidos (VIIRS ÷ MODIS):**

| Mês | Brasil | Cerrado | | Mês | Brasil | Cerrado |
|---|---|---|---|---|---|---|
| jan | 2,61 | 1,70 | | jul | 2,30 | 2,13 |
| fev | 2,22 | 1,16 | | ago | 2,19 | 2,22 |
| mar | 2,01 | 1,08 | | set | 2,29 | 2,25 |
| abr | 1,99 | 1,36 | | out | 2,65 | 2,69 |
| mai | 2,14 | 1,91 | | nov | 3,11 | 3,23 |
| jun | 2,11 | 2,01 | | dez | 3,16 | 2,75 |

O MODIS vê cerca de **metade** das células-dia do VIIRS, e a proporção muda com a estação. Dos 9.792 estratos (816 regiões × 12 meses), só 1.497 tiveram dado suficiente para fator próprio; 2.235 usam o do Cerrado e 6.060 o nacional.

### 3.2 A série CDeV (`celulas_dia.parquet`)

Para cada célula-dia, conforme a `referencia` do dia em `disponibilidade.parquet`:

| Referência do dia | `cdev` | `fonte` |
|---|---|---|
| `snpp` (S-NPP ok) | 1 se `ativa_snpp`, senão 0 | `viirs` |
| `n20` (S-NPP fora, NOAA-20 ok) | 1 se `ativa_n20`, senão 0 | `viirs` |
| `modis` (os dois VIIRS fora) | `f` se `ativa_modis` (faixa `f_min`–`f_max`) | `modis_calibrado` |
| nenhum satélite ok | NULL (**NA, não zero**) | NULL |

**Nos dados reais nunca faltou VIIRS:** todos os 2.875 dias têm referência `snpp` (2.805) ou `n20` (70). Então `fonte` é sempre `viirs` e `cdev` é 0 ou 1. O caminho do MODIS calibrado existe no código, mas só seria usado se os dois VIIRS falhassem no mesmo dia.

### 3.3 Deriva do MODIS medida (`deriva.csv`)

Aplicando o fator de 2019–2022 nos outros anos, o MODIS calibrado se afasta do VIIRS:

| Ano | 2019 | 2020 | 2021 | 2022 | **2023** | **2024** | **2025** |
|---|---|---|---|---|---|---|---|
| Erro Brasil (%) | +1,0 | −2,9 | −3,6 | −1,6 | **+5,1** | **+8,1** | **+13,5** |
| Erro Cerrado (%) | +2,6 | +3,5 | −3,2 | +1,6 | **+6,4** | **+11,2** | **+9,2** |

Erro dentro de ±4% onde calibramos; cresce a partir de 2023. É a deriva orbital do Terra e do Aqua, medida. Para a Pessoa D: este é o achado de rigor do pitch.

### 3.4 Painel de alerta (`alerta_territorios.parquet`)

363 territórios com área ≥ 10 km² (259 UCs, 104 TIs). Para 2026 até 14/11 contra o mesmo intervalo de 2019–2025: **11 recordes, 47 acima da mediana, 233 abaixo da mediana, 72 abaixo do mínimo histórico**. 2026 foi um ano fraco de fogo no Cerrado (8º de 8 no bioma inteiro).

### 3.5 Modo MIF por grupo (`mif_grupos.csv`, para a Pessoa D)

Mediana 2019–2025 da fração do fogo **depois de 15/07**, por grupo (união das células, sem somar territórios):

| Grupo | Fração tardia |
|---|---|
| UC com plano de manejo | 81,2% |
| Proteção Integral | 82,4% |
| Uso Sustentável | 85,3% |
| UC sem plano de manejo | 86,2% |
| Terra Indígena | 86,7% |

As diferenças são pequenas (5 pontos). UCs com plano de manejo têm a menor fração tardia, mas com 7 anos isso é **indício, não prova**. Com corte em 30/06 ou 31/07 a ordem se mantém (ver o arquivo).

---

## 4. Para a Pessoa C: como usar

### 4.0 Antes de começar

- **Pule o passo C1 do plano (dados falsos).** Os dados reais já estão em `saida/`; comece direto com eles.
- **Onde fica o app:** crie `app/app.py`. Como o Streamlit não põe a raiz do projeto no `sys.path`, comece o arquivo com:
  ```python
  import sys, pathlib
  sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
  from firewatch import carregar, indicadores as ind, territorios as terr
  ```
  e rode da raiz: `.venv/bin/streamlit run app/app.py`.
- **Cache:** envolva as chamadas de `carregar` em `@st.cache_data`. Para funções que recebem geometria shapely (o Streamlit não sabe fazer hash dela), passe o GeoJSON (dict) ou o WKT (`geom.wkt`) como argumento, não o objeto shapely.
- **Vários usuários ao mesmo tempo:** `carregar` abre uma conexão DuckDB por thread; não precisa fazer nada.
- **Rótulo da unidade na tela:** `cdev` = "células de 1 km com fogo detectado" (≈ km² com fogo no dia). Evite a sigla CDeV para o usuário final.

### 4.1 Em 10 linhas

```python
from firewatch import carregar, indicadores as ind, territorios as terr

cel = carregar.celulas_do_territorio("UC-0000.17.1487")   # Parque Estadual do Cantão
ind.ano_em_curso(cel)                 # cartão "2026 até 14/11"
ind.termometro(cel, 2024, 9)          # "este mês está fora do normal?"
ind.calendario_mensal(cel)            # tabela para o mapa de calor
ind.janela_critica(cel)               # início, pico e fim da estação de fogo
ind.fracao_tardia(cel, 2024)          # Modo MIF
ind.contagem_honesta(cel)             # quanto a soma dos satélites inflaria
terr.dentro_entorno("UC-0000.17.1487", 2024)   # densidade dentro ÷ entorno
terr.resumo("UC-0000.17.1487")        # tudo acima numa chamada (para o boletim)
```

Todas as funções de `indicadores` devolvem **dicts** (com chaves em português e, quando faz sentido, uma tabela `por_ano`) ou **DataFrames**. Nenhuma desenha nada.

### 4.2 Buscar os dados de uma área (`firewatch/carregar.py`)

| Função | Devolve | Quando usar |
|---|---|---|
| `celulas_do_territorio(id, zona="dentro")` | linhas célula × dia do território (`zona="entorno"` = anel de 10 km) | Território escolhido na lista |
| `serie_do_territorio(id, zona)` | o mesmo, já somado por dia (mais leve) | Idem, para muitos territórios |
| `celulas_da_geometria(geom)` | células cujo centro cai dentro de `geom` (lat/lon: shapely, GeoJSON, GeoDataFrame) | Área desenhada ou círculo lat/lon + raio |
| `serie_da_geometria(geom)` | o mesmo, somado por dia | Áreas grandes (um estado) |
| `serie_do_cerrado()` / `serie_do_brasil()` | série diária do bioma / do país | Opção "Cerrado inteiro" |
| `territorios()` / `territorio(id)` | GeoDataFrame dos 811 / ficha (dict) de um | Lista, mapa e ficha |
| `alerta_territorios()` | o painel de alerta (DataFrame) | Aba "Painel de alerta" |
| `disponibilidade()`, `fatores()`, `deriva()` | as tabelas inteiras | Avisos de lacuna, mapa de fatores, curva de deriva |
| `area_entorno_km2(id)` | área do anel (nº de células `entorno`) | Densidade do entorno |
| `centros_lat_lon(celulas)` | as mesmas linhas com `lon` e `lat` do centro da célula | Desenhar as células de um dia no mapa |

**Mapa dos focos do mês:** duas opções. Células com fogo: `carregar.centros_lat_lon(cel[cel.data_local.between(ini, fim)])` (leve, 1 ponto por célula). Focos originais: `focos_da_area` (seção 4.5; pode ser pesado). **Mapa dos fatores:** `carregar.fatores()` com `regioes.geojson`, juntando por `regiao_id`.

Tudo é lido com DuckDB e filtrado **antes** de virar pandas. Um território sai em menos de 0,1 s; o Cerrado inteiro (série diária) em 0,1 s. Use `@st.cache_data` por cima.

**Área desenhada pelo usuário:** `celulas_da_geometria` aceita direto o GeoJSON que o `streamlit-folium` devolve (`st_data["last_active_drawing"]`). Para lat/lon + raio: `shapely.Point(lon, lat).buffer(raio_graus)` ou, melhor, construa o círculo em metros com geopandas e passe o GeoDataFrame.

**Alcance de cada forma de escolher a área:**

| Forma | Alcance | Motivo |
|---|---|---|
| Lista de territórios (UC / TI) e painel de alerta | **Só Cerrado** (811 territórios) | A Parte A selecionou só UCs e TIs que tocam o Cerrado |
| Desenhar no mapa / lat-lon + raio | **Brasil inteiro** | `celulas_dia.parquet` cobre o país todo |
| "Bioma inteiro" (`serie_do_cerrado`) | Só Cerrado | A única coluna de bioma é `no_cerrado` |

Fora do Cerrado tudo funciona (calendário, termômetro, 2026, janela, MIF, CSV), com dois avisos: a data de corte do Modo MIF (15/07) é uma convenção do Cerrado e deve ser ajustável; e as regiões com pouco MODIS usam o fator nacional (só afeta "ver por sensor" e deriva, não o `cdev`). Para ter UCs e TIs de outros biomas: tirar o filtro do Cerrado em `pipeline/a4_territorios.py` e rodar `./pipeline/rodar_pipeline.sh a4 a5 b4 b5`. Fora do Brasil não há dado.

### 4.3 As funções de `firewatch/indicadores.py`

Entrada comum: `celulas` = o que `carregar` devolveu (célula × dia **ou** série diária; as funções aceitam as duas formas).

| Função | Devolve | Chaves / colunas principais |
|---|---|---|
| `serie_diaria(celulas)` | DataFrame, uma linha por dia do calendário | `data_local, cdev, na, nrt, snpp, n20, modis_bruto, modis_calibrado, celulas_ativas` |
| `calendario_mensal(celulas)` | DataFrame ano × mês (formato longo) | `ano, mes, cdev, dias_na, cobertura_reduzida, parcial, dias_nrt`. Pivot: `cal.pivot(index="ano", columns="mes", values="cdev")` |
| `calendario_semanal(celulas)` | idem por semana (1–53) | `ano, semana, data_inicio, cdev, cobertura_reduzida, parcial` |
| `termometro(celulas, ano, mes)` | dict | `valor, mediana, minimo, maximo, posicao_texto ("2º de 8"), classificacao, parcial, ate_dia, nrt, anos_comparados, avisos, por_ano` |
| `ano_em_curso(celulas)` | dict (cartão "2026 até 14/11") | mesmas chaves do termômetro + `data_fim` |
| `ranking_anos(celulas)` | DataFrame | `ano, cdev, completo, posicao` (2026 vem `completo=False`) |
| `janela_critica(celulas)` | dict | `semana_inicio, semana_pico, semana_fim, mes_inicio, mes_pico, mes_fim, climatologia` |
| `ritmo_do_ano(celulas, ano)` | dict | `semana_atual, semana_tipica, semanas_adiantado, texto` |
| `fracao_tardia(celulas, ano, data_corte=None)` | dict (Modo MIF) | `precoce, tardio, fracao, em_curso, classificacao, posicao_texto, mediana, por_ano` |
| `contagem_honesta(celulas)` | dict | `soma_ingenua, unicas, razao, por_ano` |
| `por_sensor(celulas)` | DataFrame ("ver por sensor") | `ano, mes, viirs, modis_bruto, modis_calibrado, erro_pct` |
| `lacunas(disponibilidade)` | dict | `dias_sem_dado, dias_referencia_alternativa, meses_cobertura_reduzida, resumo` |
| `classificar(valor, historico)` | dict | a regra de classificação, se precisar aplicar a outro número |
| `densidade(valor, area_km2)` | float | CDeV por 1.000 km² |

**Classificação** (chave `classificacao`, sempre um destes textos):

| Texto | Significado |
|---|---|
| `recorde (acima do máximo histórico)` | maior que todos os outros anos |
| `acima da mediana` | maior que a mediana (empate com o máximo cai aqui) |
| `abaixo da mediana` | menor ou igual à mediana |
| `abaixo do mínimo histórico` | menor que todos os outros anos |
| `sem histórico comparável` | nenhum ano para comparar |

`posicao_texto` é "Nº de M" (1º = mais fogo). Use **mediana e posição**, nunca média nem percentil: só 7 anos de histórico. Toda função devolve `avisos`, uma lista de textos para mostrar na tela (sempre inclui "Histórico curto: 7 anos (2019–2025)").

**Regras que já estão dentro das funções** (não precisa refazer no app):
- Mês ou ano **incompleto** (nov/2026 até o dia 14) é comparado com o mesmo intervalo nos outros anos (`parcial=True`, `ate_dia=14`).
- Dias NA (sem satélite de referência) ficam fora; meses com > 20% de dias NA saem do histórico (`cobertura_reduzida`). Nos dados reais não há nenhum, mas o código trata.
- `nrt=True` quando parte do período veio do NRT (2026 após jul/ago): mostre "dado preliminar".

### 4.4 Territórios (`firewatch/territorios.py` e o painel)

- `terr.resumo(id)`: ficha + 2026 + termômetro + ranking + janela crítica + MIF + dentro × entorno + `avisos` (limite aproximado, território pequeno, sem célula). Use para montar o boletim.
- `terr.dentro_entorno(id, ano)`: `razao` > 1 = mais fogo dentro; < 1 = o entorno queima mais. O `texto` já termina com "(comparação, não causa)". **Mostre esse aviso.**
- `carregar.alerta_territorios()`: 363 linhas, já ordenadas (recordes primeiro). Colunas úteis para a tabela: `nome, tipo, categoria, uf, area_km2, cdev_2026, posicao_texto, classificacao, densidade_2026, densidade_mediana, fracao_tardia_2026, razao_dentro_entorno, limite_aproximado`. Para ordenar: `ordem_classificacao` (0 = recorde … 4 = sem histórico).
- **Territórios pequenos:** 448 dos 811 têm < 10 km² e ficam fora do painel. 184 (< 2 km²) não têm nenhuma célula `dentro`: `celulas_do_territorio` devolve vazio e `terr.resumo` avisa. Para eles mostre só os focos (`focos_da_area` com o polígono).
- **Limite aproximado:** `territorios.geojson` e o painel têm `limite_aproximado=True` em 155 UCs. Mostre "⚠ limite aproximado".

### 4.5 Baixar os focos de uma área (CSV)

```python
from firewatch.focos import focos_da_area, focos_csv

df = focos_da_area(geometria, "2024-09-01", "2024-09-30")   # geometria em lat/lon (EPSG:4326)
if df.attrs["truncado"]:
    st.warning(df.attrs["aviso"])
st.download_button("Baixar CSV", focos_csv(df), "focos.csv", "text/csv")
```

- A `geometria` pode ser um polígono shapely, um GeoJSON (dict) ou uma linha do `territorios.geojson`.
- Lê só os meses pedidos, filtra pelo polígono e para em **500 mil linhas** (avisa).
- Colunas: os nomes originais do FIRMS (`latitude`, `longitude`, `confidence`…), mais `satelite`, `sensor`, `produto`, `data_local` e `id_obs`. Inclui o N21; para filtrar: `satelites=["SNPP", "N20"]`.

### 4.6 Textos fixos que o app deve mostrar

| Onde | Texto |
|---|---|
| Sempre | Histórico curto: 7 anos (2019–2025) |
| Qualquer dado de 2026 após jul (VIIRS) / ago (MODIS) | Dado preliminar (NRT); pode mudar quando a NASA publicar o archive |
| Modo MIF | Precoce/tardio classifica a **época** do fogo, não a intenção |
| Dentro × entorno | Comparação, não causa |
| UC com `limite_aproximado` | Limite aproximado |
| Território < 10 km² | Estatísticas instáveis |
| Em todo lugar | "Atividade de fogo detectada por satélite". Nunca "área queimada" nem "previsão" |

---

## 5. Diferenças em relação ao plano (leia, Pessoa C)

**Parte A**

1. **`disponibilidade`: o MODIS pode ser `parcial`** (um dos dois satélites fora; 32 dias). Colunas extras: `n_snpp`, `n_n20`, `n_modis`, `n_terra`, `n_aqua`, `n_n21`, `status_terra`, `status_aqua`, `status_n21`.
2. **`celula_territorio` tem a grade completa** (todas as células do território e do anel, não só as com fogo). A área do entorno é a contagem de células `entorno`.
3. **Territórios selecionados sem buffer**, inteiros (não recortados pelo Cerrado): 811.
4. **`territorios.geojson` tem `uf` e `limite_aproximado`.**
5. **SNPP em 2026:** o NRT termina em 02/11; de 03 a 14/11 a referência é o N20.

**Parte B**

6. **`celulas_dia.parquet` tem colunas extras:** `regiao_id`, `no_cerrado` (centro da célula dentro do Cerrado), `cdev_modis`/`cdev_modis_min`/`cdev_modis_max` (MODIS calibrado da célula-dia, para o "ver por sensor" e a deriva). Com `no_cerrado` dá para filtrar o Cerrado inteiro sem geometria.
7. **Fallback dos fatores: Cerrado ou nacional** (o plano dizia "bioma"; só temos o polígono do Cerrado). Em `fatores.parquet`, `n_anos` e `n_celulas_dia` descrevem o estrato da **região**; `f` é o fator **aplicado** (que pode ser o do Cerrado/nacional, conforme `nivel`).
8. **Dias com MODIS `parcial` ficaram fora** da calibração e da deriva.
9. **`celulas_dia` só tem linhas com fogo.** Dias sem nenhuma linha numa área são zero de verdade; dias NA são os com `referencia` NULL em `disponibilidade`. `indicadores.serie_diaria` monta o calendário completo com zeros e NAs certos — por isso **sempre passe pelas funções de `indicadores`**, não some `cdev` direto.
10. **Semana** = `(dia do ano − 1) // 7 + 1`, de 1 a 53, igual em todos os anos (não é semana ISO).
11. **O `alerta_territorios` tem mais colunas** que o contrato (ficha, mês atual, mediana, entorno) para o app não precisar de JOIN.
12. **Arquivos a mais:** `fatores_agregados.csv`, `regioes.geojson`, `mif_grupos.csv`, `saida/_tmp/serie_territorios.parquet` (série diária de cada território × zona, fora do Git; cache do B4).

---

## 6. Memória: cuidado ao rodar scripts pesados

Uma máquina de 7,5 GB de RAM **travou por completo** com scripts sem limite de memória. Por isso, **rode os scripts com `./rodar.sh`**:

```bash
./rodar.sh pipeline/b2_celulas_dia.py
MEM=3G ./rodar.sh meu_script.py        # limite diferente (o padrão é 2 GB)
```

Se o script passar do limite, **só ele é encerrado** (código 137), e o computador continua normal. Isso só funciona no Linux com systemd. Em outros sistemas, o `rodar.sh` roda sem limite e mostra um aviso.

Para o app: `carregar` já filtra no DuckDB antes de trazer para o pandas. Evite `pd.read_parquet("saida/celulas_dia.parquet")` inteiro (10 M linhas).

---

## 7. Se precisar regenerar `saida/`

Normalmente não é preciso. Se algum parâmetro do `config.yaml` mudar:

```bash
./pipeline/rodar_pipeline.sh                # tudo (A e B), cerca de 5 min
./pipeline/rodar_pipeline.sh b1 b2 b3 b4 b5 # só a Parte B, cerca de 1 min
```

| Etapa | Script | Gera | Depende de |
|---|---|---|---|
| a0 | `a0_extrair_zips.py` | CSVs em `data/raw/nasa/` | — |
| a1 | `a1_observacoes.py` | `observacoes/`, `fontes_fixas.parquet` | a0 |
| a2 | `a2_disponibilidade.py` | `disponibilidade.parquet` | a1 |
| a3 | `a3_celulas_base.py` | `celulas_base.parquet` | a1 |
| a4 | `a4_territorios.py` | `territorios.geojson` | — |
| a5 | `a5_celula_territorio.py` | `celula_territorio.parquet` | a4 |
| **b1** | `b1_fatores.py` | `fatores.parquet`, `fatores_agregados.csv`, `regioes.geojson` | a2, a3 |
| **b2** | `b2_celulas_dia.py` | `celulas_dia.parquet` | b1 |
| **b3** | `b3_deriva.py` | `deriva.csv` | b2 |
| **b4** | `b4_alerta_territorios.py` | `alerta_territorios.parquet` | b2, a5 |
| **b5** | `b5_mif_grupos.py` | `mif_grupos.csv` | b2, a5 |

Parâmetros da Parte B no `config.yaml`: `calibracao_anos`, `estrato_minimo_celulas`, `cobertura_reduzida`, `mif_data_corte`, `territorio_area_min_km2`, `periodo_historico`, `ano_em_curso`, `data_fim_dados`. **Nunca escreva números direto no código.**

---

## 8. Estrutura

```
FireWatch/
├── README.md               ← este arquivo
├── config.yaml             ← TODOS os parâmetros
├── requirements.txt
├── rodar.sh                ← roda Python com limite de memória
├── firewatch/              ← biblioteca usada pelo app
│   ├── config.py           ← lê o config.yaml e os caminhos
│   ├── focos.py            ← focos_da_area() para o CSV (A11)
│   ├── carregar.py         ← B: busca os dados de uma área / território (leitura, sem cálculo)
│   ├── indicadores.py      ← B: funções puras — calendário, termômetro, 2026, MIF, janela, honesta
│   └── territorios.py      ← B: dentro × entorno e resumo() de um território
├── pipeline/               ← scripts que geram saida/ (a0..a5 Parte A, b1..b5 Parte B) + rodar_pipeline.sh
├── tests/                  ← test_parte_a.py, test_parte_b.py
├── saida/                  ← arquivos gerados (no Git, prontos para usar)
└── data/                   ← dados brutos (README próprio + auditoria)
```
