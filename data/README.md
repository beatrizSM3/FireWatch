# Dados

Este diretório guarda os dados brutos do FireWatch: focos de calor detectados por satélite (NASA FIRMS) e o limite geográfico do Cerrado.

```
data/
├── README.md
└── raw/
    ├── biome_border/     # shapefile com o limite do Cerrado
    ├── nasa/             # CSVs de focos de calor, um diretório por satélite/sensor
    │   ├── MODIS/
    │   ├── SUOMI_VIIRS_C2/
    │   ├── J1_VIIRS_C2/
    │   └── J2_VIIRS_C2/
    └── zip/nasa/         # zips originais baixados do FIRMS (mesmo conteúdo de nasa/)
```

## O que é o FIRMS

O [FIRMS](https://firms.modaps.eosdis.nasa.gov/) (Fire Information for Resource Management System) é o serviço da NASA que distribui **detecções de fogo ativo** feitas por satélite.

Os sensores medem a radiação infravermelha da superfície. Quando um pixel fica bem mais quente que os vizinhos, o algoritmo marca esse pixel como **foco de calor**. Cada linha dos CSVs é um foco desses, ou seja, um pixel com provável fogo naquele momento.

Pontos importantes:

- Um foco **não é um incêndio**. Um incêndio grande gera muitos focos, em pixels vizinhos e em várias passagens do satélite.
- O satélite só vê o que está acontecendo **na hora da passagem**. Fogo que começa e apaga entre duas passagens não aparece. Nuvem densa e fumaça também escondem focos.
- A posição é o **centro do pixel**, não o ponto exato do fogo.

## Sensores e satélites

Os dados vêm de dois tipos de sensor, embarcados em quatro satélites diferentes.

### MODIS (pasta `MODIS/`)

**MODIS** (Moderate Resolution Imaging Spectroradiometer) é o sensor mais antigo. Ele voa em dois satélites da NASA:

| Satélite | Lançamento | Passagem sobre o Brasil (hora local) |
|---|---|---|
| **Terra** | 1999 | ~10h30 e ~22h30 |
| **Aqua** | 2002 | ~13h30 e ~01h30 |

- Resolução de **~1 km** por pixel. Detecta fogos maiores, perde muitos fogos pequenos.
- A série histórica é longa (desde 2000), por isso é muito usada para comparar anos.
- Terra e Aqua estão no fim da vida útil e saindo da órbita original, então a hora de passagem está mudando aos poucos. A NASA vai descontinuar o MODIS e o VIIRS é o substituto.
- Os arquivos usam a **Coleção 6.1** (`M-C61` no nome).

### VIIRS (pastas `SUOMI_VIIRS_C2/`, `J1_VIIRS_C2/`, `J2_VIIRS_C2/`)

**VIIRS** (Visible Infrared Imaging Radiometer Suite) é o sensor mais novo, sucessor do MODIS.

- Resolução de **~375 m** por pixel. Detecta fogos bem menores que o MODIS e gera bem mais focos para o mesmo evento.
- Todos os satélites com VIIRS passam sobre o Brasil por volta de **13h30 e 01h30** (hora local), com algumas dezenas de minutos de diferença entre eles.
- Os arquivos usam a **Coleção 2** (`C2` no nome).

O mesmo sensor VIIRS voa em três satélites. Cada pasta corresponde a um deles:

| Pasta | Satélite | Outro nome | Lançamento | Valor na coluna `satellite` |
|---|---|---|---|---|
| `SUOMI_VIIRS_C2/` | **Suomi NPP** | S-NPP | 2011 | `SNPP` |
| `J1_VIIRS_C2/` | **NOAA-20** | JPSS-1 (J1) | 2017 | `N20` |
| `J2_VIIRS_C2/` | **NOAA-21** | JPSS-2 (J2) | 2022 | `N21` |

**JPSS** (Joint Polar Satellite System) é o programa de satélites meteorológicos polares da NOAA com a NASA. "J1" e "J2" são os nomes de projeto dos satélites, que depois de lançados passaram a se chamar NOAA-20 e NOAA-21. O Suomi NPP foi o satélite de teste que antecedeu o programa.

### Resumo do que temos

| Pasta | Sensor | Satélite(s) | Pixel | Anos disponíveis |
|---|---|---|---|---|
| `MODIS/` | MODIS | Terra + Aqua | ~1 km | 2019–2026 |
| `SUOMI_VIIRS_C2/` | VIIRS | Suomi NPP | ~375 m | 2019–2026 |
| `J1_VIIRS_C2/` | VIIRS | NOAA-20 | ~375 m | 2019–2026 |
| `J2_VIIRS_C2/` | VIIRS | NOAA-21 | ~375 m | 2024–2026 |

## Organização dos arquivos

Cada subpasta é um pedido de download de **um ano**:

```
DL_FIRE_<fonte>_<ano>_<id do pedido>/
├── fire_archive_<fonte>_<id>.csv
├── fire_nrt_<fonte>_<id>.csv     # só em 2026
└── Readme.txt                    # só aponta para o readme do FIRMS
```

`<fonte>` é `M-C61` (MODIS), `SV-C2` (Suomi NPP), `J1V-C2` (NOAA-20) ou `J2V-C2` (NOAA-21). O `<id do pedido>` é só o número do download no FIRMS e não tem significado para a análise.

### `fire_archive` × `fire_nrt`

- **`fire_archive_*.csv` (Standard / Archive):** dado definitivo, reprocessado pela NASA com dados auxiliares de melhor qualidade. Fica disponível alguns meses depois da observação. Tem a coluna `type`.
- **`fire_nrt_*.csv` (Near Real Time):** dado entregue até ~3 horas depois da passagem do satélite. É menos refinado e **não tem a coluna `type`**. A coluna `version` termina em `NRT` (`2.0NRT`, `6.1NRT`).

Só 2026 tem arquivo NRT, porque o archive ainda não cobre o ano inteiro. Os dois arquivos se complementam sem sobreposição de datas:

| Fonte | Archive 2026 | NRT 2026 |
|---|---|---|
| VIIRS (SNPP, N20, N21) | 01/01 a 31/07 | a partir de 01/08 |
| MODIS | 01/01 a 31/08 | a partir de 01/09 |

Quando a NASA publicar o archive dos meses restantes, os dados NRT desses meses devem ser substituídos.

## Colunas dos CSVs

| Coluna | Descrição |
|---|---|
| `latitude`, `longitude` | Centro do pixel com fogo, em graus (WGS84). |
| `brightness` | Temperatura de brilho do pixel, em Kelvin. Canal I4 no VIIRS e canal 21/22 no MODIS. |
| `scan`, `track` | Tamanho real do pixel em km (largura × comprimento). O pixel cresce na borda da faixa imageada. |
| `acq_date` | Data da passagem do satélite (`AAAA-MM-DD`), em **UTC**. |
| `acq_time` | Hora da passagem (`HHMM`), em **UTC**. Para Brasília, subtraia 3 horas. |
| `satellite` | Satélite: `Terra`, `Aqua`, `SNPP`, `N20` ou `N21`. |
| `instrument` | Sensor: `MODIS` ou `VIIRS`. Atenção: no Suomi NPP esse campo vem como `SNPP`. |
| `confidence` | Confiança na detecção. VIIRS: `l` (baixa), `n` (nominal), `h` (alta). MODIS: número de 0 a 100. |
| `version` | Versão do algoritmo de detecção. |
| `bright_t31` | Temperatura de brilho de fundo, em Kelvin. Canal I5 no VIIRS e canal 31 no MODIS. |
| `frp` | **Fire Radiative Power**, em MW. Mede a energia liberada pelo fogo. É a melhor medida de intensidade. |
| `daynight` | `D` para detecção diurna, `N` para noturna. |
| `type` | Só no archive. `0` = vegetação, `1` = vulcão, `2` = outra fonte terrestre estática (indústria, queima de gás), `3` = offshore. |

## Limite do Cerrado (`raw/biome_border/`)

Shapefile com o polígono do bioma Cerrado, em SIRGAS 2000. Os CSVs do FIRMS cobrem uma área maior que o Cerrado. Use esse polígono para manter só os focos que caem dentro do bioma.

## Cuidados ao usar os dados

1. **O mesmo fogo aparece várias vezes.** Quatro satélites passam sobre a mesma região e um incêndio ocupa vários pixels. Não some focos de fontes diferentes sem tratar. Use uma fonte só, ou agrupe os focos por distância e tempo.
2. **MODIS e VIIRS não são comparáveis diretamente.** O VIIRS tem pixel menor e detecta muito mais focos. Compare séries temporais sempre dentro da mesma fonte.
3. **NOAA-21 só tem dados desde 2024.** Uma série que inclua essa fonte vai mostrar aumento artificial a partir de 2024.
4. **Os formatos são diferentes entre fontes.** `confidence` é texto no VIIRS e número no MODIS. O NRT não tem `type`. Padronize antes de juntar os arquivos.
5. **A `version` do MODIS muda de grafia.** Aparece como `6.03` até 2022 e `61.03` a partir de 2023. É o mesmo algoritmo.
6. **Filtre `type == 0`** para ficar só com fogo em vegetação.
7. **Leia `acq_time` como texto**, senão `0336` vira `336`. Exemplo com pandas:

   ```python
   df = pd.read_csv(path, dtype={"acq_time": str})
   ```

8. **Data e hora estão em UTC.** Uma detecção às `0130` UTC aconteceu às 22h30 de Brasília **do dia anterior**. Isso afeta principalmente a passagem noturna do Terra.

## Referências

- FIRMS: https://firms.modaps.eosdis.nasa.gov/
- Descrição oficial dos atributos: https://www.earthdata.nasa.gov/data/tools/firms/faq
- Readme do download: https://firms.modaps.eosdis.nasa.gov/download/Readme.txt
