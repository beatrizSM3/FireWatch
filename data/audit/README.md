*# Auditoria dos dados FIRMS

Notas da auditoria de qualidade e da análise exploratória dos CSVs em `data/raw/nasa/`, feita em 2026-11-14. Para a descrição dos sensores e das colunas, veja [`../README.md`](../README.md).

Todos os números abaixo foram medidos nos arquivos. Quando algo é interpretação ou não pôde ser verificado, o texto diz isso.

## Escopo e método

- 31 CSVs, 28.389.853 linhas, carregados como cópia em DuckDB, com todas as colunas lidas como texto. Os originais não foram alterados.
- "Cerrado" = ponto dentro de `data/raw/biome_border/biome_border.shp`, testado em EPSG:5880 (metros).
- Salvo indicação contrária, as análises no Cerrado usam: `kind = archive`, `type = 0`, anos 2019–2025.
- Os pares entre satélites foram calculados com KD-tree sobre uma amostra aleatória de 2% dos pontos do Cerrado (seed 42, 166 mil pontos). Os vizinhos vêm de todos os pontos dentro do buffer de 15 km.

## Pronto para uso?

Os arquivos estão íntegros, mas os indicadores ainda não podem ser calculados direto. Faltam três tratamentos:

1. **Lacunas de satélite** dentro da estação de fogo.
2. **Deriva orbital do MODIS** (Terra e Aqua).
3. **Mudança da constelação** com a entrada do NOAA-21 em 2024.

## Achados

| ID | Gravidade | Achado | Ação recomendada |
|---|---|---|---|
| A1 | crítico | Dias com zero detecções enquanto outro satélite tem milhares de focos (lista abaixo). | Máscara de disponibilidade por satélite e dia. Dia sem dado = NA, não zero. |
| A2 | crítico | Deriva orbital do MODIS: mediana da passagem diurna do Terra 13,92 h → 12,32 h UTC e do Aqua 17,08 h → 18,08 h UTC (2019 → 2025). Fração noturna do Terra no Cerrado 0,294 → 0,524. | Não usar MODIS para tendência entre anos. |
| A3 | crítico | NOAA-21 só a partir de 2024-01-01. O ano de 2023 não foi baixado, embora o satélite opere desde 01/03/2023. | N21 fora do baseline. Baixar 2023 se for usar N21 na validação. |
| A4 | importante | Soma simples ÷ únicos (células-dia, sem N21): 1,33–1,46 em 1 km, 1,47–1,62 em 5 km, 1,52–1,67 em 10 km. | Sempre reportar a grade e a janela usadas. |
| A5 | importante | O Terra não tem nenhum par com outro satélite em janela de 1 h. | Deduplicar por passagem (VIIRS + Aqua da tarde) e tratar o Terra à parte. |
| A6 | importante | Confiança baixa no Cerrado: VIIRS `l` 11–12%, MODIS < 30 de 4,5–5,1%. As escalas não são comparáveis. | Usar VIIRS `n`+`h` e MODIS ≥ 30, com teste de sensibilidade. |
| A7 | importante | Passagem noturna do Terra cruza a meia-noite UTC: 36.542 detecções entre 21 e 24 h UTC e 484.168 entre 0 e 3 h. | Agregar por data local (UTC−3). |
| A8 | menor | `type ≠ 0` no Cerrado (2019–2025): N20 12.833, S-NPP 11.824, N21 4.289, Aqua 3.264, Terra 2.313. | Filtrar `type == 0`. |
| A9 | menor | `brightness = 0` em 15 linhas VIIRS, `bright_t31 = 0` em 1, `frp < 0` em 1 (MODIS, −1,3), `frp = 0` em 8.542. | Remover linhas com brilho 0 e FRP ≤ 0. |
| A10 | menor | `brightness = 367` (saturação do canal I4 do VIIRS) em 1,75 M linhas. `brightness < bright_t31` em 89.122 linhas VIIRS. | Usar FRP, não brilho, como medida contínua. |
| A11 | menor | 14 grupos com mesmo satélite, posição e minuto, mas atributos diferentes. | `drop_duplicates(["satellite","latitude","longitude","acq_date","acq_time"])`. |
| A12 | info | Não há NRT em 2019–2025. NRT só existe em 2026. | Nenhuma, já que 2026 fica fora. |

## 1. Inventário

- 27 arquivos archive com 15 colunas. Os 4 arquivos NRT de 2026 têm 14 colunas, sem `type`.
- Todos os campos convertem sem erro para o tipo esperado.
- `acq_time` é sempre texto `HHMM` válido, e data + hora formam datetime válido em 100% das linhas.
- Nenhuma linha duplicada exata, nem dentro de um arquivo nem entre arquivos. Os arquivos não se sobrepõem em 31/12 e 01/01.

| Satélite | Linhas 2019–2025 (archive) | Anos | `version` |
|---|---|---|---|
| S-NPP | 10.254.157 | 2019–2025 | `2` |
| NOAA-20 | 10.230.051 | 2019–2025 | `2` |
| NOAA-21 | 2.870.126 | 2024–2025 | `2` |
| MODIS (Aqua + Terra) | 2.666.263 | 2019–2025 | `6.03` até 2022, `61.03` depois |

Diferenças de esquema:

- `confidence` é número de 0 a 100 no MODIS e `l`/`n`/`h` no VIIRS.
- `instrument = SNPP` no S-NPP, em vez de `VIIRS`.
- O VIIRS também usa os nomes `brightness`/`bright_t31` (canais I4/I5). Não existem colunas `bright_ti4`/`bright_ti5`.
- `scan`: VIIRS de 0,32 a 0,80 km; MODIS de 1,0 a 4,82 km.

## 2. Cobertura temporal

Lacunas, ou seja, dias com zero detecções no Brasil inteiro:

| Satélite | Dias | Períodos |
|---|---|---|
| S-NPP | 37 | 28/06/2022; 27/07–10/08/2022; 26–27/07/2023; 30/05–03/06/2024; 10–15/07/2024; 25–28/07/2024; 26/09/2024; 03–05/11/2024 |
| Aqua | 18 | 28/08/2020; 24/09/2021; 01–16/04/2022 |
| Terra | 13 | 11–22/10/2022; 12/05/2024 |
| NOAA-20 | 6 | 19–22/07/2023; 30/09/2023; 04/02/2024 |
| NOAA-21 | 2 | 27–28/02/2024 |

Também há dias parciais, por exemplo S-NPP com 200 focos contra 3.796 do N20 em 16/07/2024.

- A razão diária S-NPP/N20 tem mediana 1,010 e p99 de 1,74. Fora das lacunas, os dois são intercambiáveis.
- 2025 teve menos focos que 2024 em todos os satélites, com razões entre sensores estáveis. **Interpretação:** sinal real entre anos, não falha de dados.
- Sazonalidade: entre fevereiro e abril, cerca de 9–45 mil focos por mês por VIIRS. Em setembro, 210–684 mil.

## 3. Qualidade dos campos

- **Coordenadas:** lat −33,8 a 5,4; lon −74,1 a −29,3. Nenhum ponto em caixas de teste dentro da Bolívia, do Paraguai, da Argentina ou do norte da Venezuela, o que indica download recortado pelo Brasil. Nenhuma lat/lon invertida. A precisão é de 5 casas no VIIRS e 4 no MODIS; menos casas são só zeros finais removidos.
- **UTC:** a passagem diurna mediana do VIIRS é ~17,0 h UTC, ou 14 h local. Isso é coerente com o cruzamento de ~13h30.
- **Confiança no Cerrado:**

  | Satélite | Baixa | Nominal | Alta |
  |---|---|---|---|
  | N20 | 394.143 (12,1%) | 2.638.517 | 217.145 |
  | S-NPP | 364.673 (11,1%) | 2.651.104 | 258.040 |
  | N21 | 115.679 (12,0%) | 764.908 | 84.241 |
  | Aqua (<30 / 30–79 / ≥80) | 21.386 (4,5%) | 280.767 | 172.187 |
  | Terra (<30 / 30–79 / ≥80) | 19.254 (5,1%) | 237.496 | 122.187 |

  O FRP mediano sobe com a confiança: VIIRS `h` ≈ 16–20 MW; MODIS ≥ 80 ≈ 41–60 MW.
- **`type = 3` (offshore) dentro do Cerrado:** 1.497 linhas no N20. **Interpretação provável:** grandes reservatórios. Não verificado; testar cruzando com uma máscara de água.

## 4. Pares entre satélites (deduplicação)

Percentual de detecções A com ≥ 1 par no satélite B, janela de 3 h:

| A → B | 0,5 km | 1 km | 2 km | 5 km |
|---|---|---|---|---|
| S-NPP → N20 | 61,9 | 71,1 | 75,0 | 78,3 |
| N21 → N20 | 62,2 | 72,0 | 76,0 | 79,4 |
| Aqua → N20 | 39,7 | 64,4 | 76,4 | 80,7 |
| N20 → Aqua | 11,4 | 25,2 | 33,8 | 39,7 |
| Terra → S-NPP | 15,5 | 24,0 | 27,5 | 29,3 |
| Terra → Aqua | 2,3 | 6,4 | 10,5 | 13,6 |

O percentual de N20/S-NPP → N21 parece baixo (~20–25%) porque o N21 só existe em 2 dos 7 anos.

Percentual de A com par em qualquer outro satélite:

| A | Raio | 1 h | 3 h | 6 h |
|---|---|---|---|---|
| S-NPP | 1 km | 76,3 | 77,5 | 78,2 |
| N20 | 1 km | 75,1 | 76,1 | 76,9 |
| Aqua | 1 km | 73,6 | 78,0 | 78,2 |
| Terra | 0,5 km | 0,0 | 27,4 | 51,0 |
| Terra | 1 km | 0,0 | 41,9 | 71,5 |
| Terra | 5 km | 0,0 | 50,1 | 82,4 |

Pares não ordenados no Cerrado, em milhões (estimativa = amostra × 50 ÷ 2):

| Raio | 1 h | 3 h | 6 h |
|---|---|---|---|
| 0,5 km | 7,1 | 8,1 | 8,5 |
| 1 km | 17,3 | 20,1 | 21,3 |
| 2 km | 33,0 | 39,1 | 41,9 |
| 5 km | 60,4 | 72,1 | 77,7 |

Interpretação:

- Entre VIIRS, o percentual com par se estabiliza entre 1 e 2 km.
- Entre MODIS e VIIRS, o percentual ainda cresce até 2 km, por causa do pixel do MODIS de 1–4,8 km.
- Com 5 km há ~9 pares por detecção. Contar pares não mede duplicação; o certo é medir a fração de detecções com par, ou clusterizar.
- O Terra passa ~3–4 h antes dos outros. Uma janela longa o bastante para pegar o Terra também junta estágios diferentes de um mesmo fogo.

Superestimativa da soma simples por células-dia (Aqua + Terra + S-NPP + N20, dia local UTC−3):

| Ano | 1 km | 5 km | 10 km |
|---|---|---|---|
| 2019 | 1,39 | 1,54 | 1,59 |
| 2020 | 1,40 | 1,54 | 1,59 |
| 2021 | 1,38 | 1,52 | 1,57 |
| 2022 | 1,35 | 1,50 | 1,55 |
| 2023 | 1,33 | 1,47 | 1,52 |
| 2024 | 1,46 | 1,62 | 1,67 |
| 2025 | 1,42 | 1,58 | 1,63 |

Incluir o N21 em 2024 aumenta as células-dia únicas de 1 km em 18% (506.326 → 598.127).

## 5. Diferenças entre sensores (Cerrado, 84 meses)

| Razão mensal | Mediana | p25–p75 | Mín.–máx. |
|---|---|---|---|
| S-NPP/N20 (contagem) | 1,018 | 0,98–1,04 | 0,61 (jul/2024, lacuna)–1,16 |
| N21/N20 (contagem, 24 meses) | 0,970 | 0,94–0,99 | 0,83–1,07 |
| MODIS/N20 (contagem) | 0,332 | 0,25–0,39 | 0,16–1,41 |
| MODIS/N20 (FRP) | 1,178 | 1,07–1,35 | 0,61–3,68 |
| Terra/Aqua (contagem) | 0,834 | 0,75–0,96 | 0,39 (out/2022)–2,51 (abr/2022) |

- Área média do pixel: MODIS ~2,2–2,3 km², VIIRS ~0,23 km². Entre 75% e 79% dos pixels MODIS têm `scan` > 1 km.
- Fração noturna: VIIRS 0,27–0,34; Aqua 0,10–0,13; Terra 0,29 → 0,52 (2019 → 2025).
- O MODIS registra ~1/3 dos focos do VIIRS, mas um FRP total parecido. O FRP não soma entre sensores e depende do horário de passagem.
- A razão MODIS/N20 sobe na estação chuvosa (até 1,41 em março), quando há poucos focos.
- **Ressalva sobre a deriva (A2):** a hora UTC também depende da longitude dos focos. O VIIRS variou só ~0,3 h no mesmo período, enquanto Terra e Aqua mudaram 1–1,6 h em direções opostas. A deriva orbital é a explicação provável, mas não foi isolada. Para testar, compare a hora solar local (UTC + lon/15).

Contagens anuais no Cerrado:

| Ano | Soma de todos | Soma sem N21 | Só N20 | Só S-NPP | Só MODIS |
|---|---|---|---|---|---|
| 2019 | 1.136.069 | 1.136.069 | 499.014 | 508.596 | 128.459 |
| 2020 | 1.124.472 | 1.124.472 | 492.864 | 505.755 | 125.853 |
| 2021 | 1.020.873 | 1.020.873 | 445.658 | 459.199 | 116.016 |
| 2022 | 989.614 | 989.614 | 448.193 | 429.534 | 111.887 |
| 2023 | 864.340 | 864.340 | 369.828 | 387.663 | 106.849 |
| 2024 | 1.806.515 | 1.261.397 | 561.830 | 545.278 | 154.289 |
| 2025 | 1.399.844 | 980.134 | 432.418 | 437.792 | 109.924 |

## 6. Recorte do Cerrado

- `biome_border.shp`: 1 polígono, válido, em EPSG:4674 (SIRGAS 2000). Bounds: lon −60,47 a −41,28; lat −24,68 a −2,33.
- Área em EPSG:5880: 1.996.856 km². É aproximada, porque a EPSG:5880 não é uma projeção de área igual.
- Contagem de pontos (todos os anos e types): 9.150.132 dentro do polígono, 10.057.752 no buffer de 10 km e 10.379.235 no buffer de 15 km.
- **Não verificável:** se o recorte da equipe foi feito em metros. Não havia código de recorte nem saída recortada no repositório.
- Nas latitudes do Cerrado, um buffer em graus erraria até ~9% no eixo leste-oeste, porque cos(24,7°) = 0,91.

## 7. Atenção estatística para os indicadores

- **Constelação:** o N21 a partir de 2024 soma +43% de detecções e +18% de células-dia de 1 km. A lacuna do S-NPP em julho de 2024 compensa parte disso e mascara o efeito.
- **Baseline curto:** há 7 valores por mês (2019–2025). Se 2024–2025 forem reservados para validação, sobram 5. Com 5 valores, o p90 é praticamente o máximo, e a MAD fica instável.
- **Risco discreto:** com 5 anos, a probabilidade só pode ser 0; 0,2; 0,4; 0,6; 0,8 ou 1. Suavizar com Beta-binomial ou janela de ±15 dias, ou agregar em células maiores.
- **Ano extremo:** N20 no Cerrado em 2024 teve 561.830 detecções; a média de 2019–2023 é 451 mil. Setembro de 2024 domina qualquer média. Usar mediana/MAD.
- **Outros vieses:** deriva do MODIS (A2), data UTC × data local (A7) e lacunas tratadas como zero (A1). A cobertura de nuvens não é verificável com estes dados.

## Decisões em aberto

1. **Fonte do baseline:** S-NPP + N20 deduplicados (recomendado) ou incluir MODIS mesmo com a deriva.
2. **Filtro de confiança:** VIIRS `n`+`h` e MODIS ≥ 30, ou manter tudo e reportar a sensibilidade.
3. **Raio de deduplicação:** sugestão de 1 km para VIIRS–VIIRS e 2 km para MODIS–VIIRS.
4. **Janela de deduplicação:** mesma passagem (≈ 1 h) ou mesmo dia local.
5. **Unidade dos indicadores:** detecção ou célula-dia (1, 5 ou 10 km).
6. **Período do baseline:** 2019–2023 ou 2019–2025 com validação leave-one-year-out.
7. **Dias com lacuna:** excluir, imputar pelo outro VIIRS, ou marcar como NA.
8. **NOAA-21:** baixar 2023 (a partir de 01/03) ou validar só com 2024–2025.

## Próximos passos

1. Construir a máscara de disponibilidade por satélite e dia.
2. Padronizar os filtros: `type == 0`, confiança, FRP > 0, brilho > 0, data local UTC−3.
3. Baseline S-NPP + N20, deduplicado por passagem com raio de 1 km. Medir a superestimativa da soma simples contra esse resultado.
4. Rodar a sensibilidade de raio e janela no conjunto completo, não só na amostra de 2%.
5. Testar a deriva do MODIS em hora solar local.
6. Baixar NOAA-21 de 2023, se for necessário.
7. Versionar o código do recorte do Cerrado em EPSG:5880.

## Como reproduzir (trechos principais)

Carga com `acq_time` como texto:

```python
import duckdb
con = duckdb.connect("firms.duckdb")
con.execute(f"""INSERT INTO fires BY NAME
  SELECT *, '{sensor}' sensor, '{kind}' kind, '{arquivo}' file
  FROM read_csv('{caminho}', header=true, all_varchar=true)""")
# datetime: strptime(acq_date || ' ' || acq_time, '%Y-%m-%d %H%M')
```

Recorte do Cerrado em metros:

```python
import geopandas as gpd, shapely
from pyproj import Transformer
poly = gpd.read_file("data/raw/biome_border/biome_border.shp").to_crs(5880).geometry.iloc[0]
buf15 = poly.buffer(15_000)
x, y = Transformer.from_crs(4326, 5880, always_xy=True).transform(lon, lat)
in_cerrado = shapely.contains_xy(poly, x, y)
```

Lacunas (dias com zero detecções e razão entre VIIRS):

```python
w = diario.pivot(index="d", columns="satellite", values="n")   # calendário completo, 0 onde não há dado
lacunas = w[(w.SNPP == 0) & (w.N20 > 1000)]
```

Pares entre satélites (KD-tree por dia, amostra A):

```python
from scipy.spatial import cKDTree
tree = cKDTree(np.c_[X[b], Y[b]])                 # B: pontos de [dia-6h, dia+1+6h]
viz = tree.query_ball_point(np.c_[X[a], Y[a]], 5000)
# filtrar satélite diferente, |dt| <= janela e distância <= raio
```

Superestimativa por células-dia:

```sql
SELECT count(DISTINCT (sat, gx, gy, dia_local)) / count(DISTINCT (gx, gy, dia_local))
FROM c WHERE sat <> 'N21';   -- gx = floor(x/1000), dia_local = (ts - INTERVAL 3 HOUR)::DATE
```
