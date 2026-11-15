# FireWatch — Parte A (Dados)

Esta é a entrega da **Parte A do plano dividido** (Pessoa A). Ela transforma os 28,4 milhões de focos do FIRMS (31 CSVs) e os shapefiles de UCs e TIs nos arquivos de `saida/`, que as Pessoas B, C e D usam.

**Você não precisa rodar nada.** Os arquivos de `saida/` já estão no repositório: clonou, usou.

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
./rodar.sh -m pytest tests -q      # 15 testes: colunas do contrato + "Pronto quando" de cada passo
```

> O código usa a **API do DuckDB 2.x**. Com o DuckDB 1.x, algumas funções dão erro.

---

## 2. O que tem em `saida/`

| Arquivo | Uma linha é | Linhas | Usado por |
|---|---|---|---|
| `observacoes/ano=AAAA/parte-MM.parquet` | um foco (um arquivo por mês) | 25.623.084 | B, C, D |
| `disponibilidade.parquet` | um dia | 2.875 | B, C |
| `fontes_fixas.parquet` | uma célula de fonte fixa (indústria/mar) | 28.118 | A |
| `celulas_base.parquet` | célula de 1 km × dia com fogo | 10.452.862 | B |
| `territorios.geojson` | um território (UC ou TI do Cerrado) | 811 | B, C |
| `celula_territorio.parquet` | célula × território | 1.131.688 | B |

Período: **01/01/2019 a 14/11/2026** (data local, UTC−3). As colunas seguem o contrato de dados (seção 0.6 do plano), com algumas colunas extras descritas abaixo.

Para ler tudo de uma vez com DuckDB: `SELECT * FROM 'saida/observacoes/*/*.parquet'`.

---

## 3. O que foi feito, passo a passo

| Passo | O que o plano pedia | O que foi feito | Conferido |
|---|---|---|---|
| **A2** | Ler os 31 CSVs como texto | `pipeline/a1_observacoes.py` | 28.389.853 linhas, 0 sem coordenada |
| **A3** | Filtros (`type=0`, confiança, FRP>0) e `data_local` | Igual ao plano. Também remove duplicatas (achado A11 da auditoria) | 90,3% mantidas |
| **A4** | Projetar em EPSG:5880 e criar `gx`, `gy` | Igual ao plano | Brasília → Goiânia = 176,7 km |
| **A5** | Parquet por ano | Por ano **e por mês** (`parte-MM.parquet`), para caber na memória | 8 anos, 938 MB |
| **A6** | Status diário de cada satélite e `referencia` | `pipeline/a2_disponibilidade.py` | SNPP ausente de 27/07 a 10/08/2022, com `referencia = n20` |
| **A7** | Células com `type` 2 ou 3 | No `a1_observacoes.py`; os focos NRT nessas células já saem de `observacoes/` | 28.118 células |
| **A8** | `celulas_base.parquet` | `pipeline/a3_celulas_base.py`, ordenado por data | Sem repetição; 2019–2026 |
| **A9** | `territorios.geojson` | `pipeline/a4_territorios.py` | 811 territórios (687 UCs + 124 TIs), 2,8 MB |
| **A10** | `celula_territorio.parquet` | `pipeline/a5_celula_territorio.py` | Células dentro ≈ `area_km2` (mediana 1,000) |
| **A11** | Função para baixar os focos de uma área | `firewatch/focos.py` | 50 × 50 km em setembro de 2024 em 0,15 s |

---

## 4. Diferenças em relação ao plano (leia, Pessoas B e C)

1. **`disponibilidade`: o MODIS pode ser `parcial`.** O plano só previa `ok` ou `ausente` para o MODIS. Mas Terra + Aqua somados nunca chegam a zero, e assim as lacunas da auditoria ficavam escondidas. Agora o MODIS é `parcial` quando **um** dos dois está fora do ar (32 dias; por exemplo, o Aqua de 01 a 16/04/2022).
   → **Pessoa B: deixe os dias com MODIS `parcial` fora da calibração e da deriva.**
   Colunas extras: `n_snpp`, `n_n20`, `n_modis`, `n_terra`, `n_aqua`, `n_n21`, `status_terra`, `status_aqua`, `status_n21`.

2. **`celula_territorio` tem a grade completa.** Estão todas as células do território e do anel de 10 km, e não só as que tiveram fogo.
   - **A área do entorno é a contagem de células `entorno`**, já que cada célula tem 1 km². Ela não existe em nenhum outro arquivo, e é o denominador da densidade dentro × entorno.
   - O `JOIN` com `celulas_dia` funciona igual: células sem fogo simplesmente não casam.
   - Uma célula pode estar em vários territórios, e pode estar dentro de um e no entorno de outro.

3. **Os territórios foram selecionados sem buffer.** O PLANO2 cita um buffer de 15 km, mas é a seleção sem buffer que dá os 811 territórios dos dois planos (com o buffer seriam 907). Cada território entra **inteiro**, sem recorte pela borda do Cerrado.

4. **`territorios.geojson` tem duas colunas extras:**
   - `uf`: siglas, como `"GO"` ou `"BA, MA, PI, TO"`. É a mesma regra para UCs e TIs.
   - `limite_aproximado`: `true` em 155 UCs cujo polígono é uma "estimativa" ou uma "representação esquemática". O app deve mostrar o aviso "limite aproximado".

5. **Territórios pequenos:**
   - 448 dos 811 têm menos de 10 km². Com o mínimo de área, **o painel de alerta fica com 363 territórios**.
   - 184 têm menos de 2 km² e **não têm nenhuma célula `dentro`**, porque nenhum centro de célula de 1 km cai neles. Para esses, o app usa `focos_da_area` com o polígono.

6. **SNPP em 2026:** o arquivo NRT baixado **termina em 02/11/2026**. Por isso o SNPP aparece `ausente` de 03 a 14/11, e a referência passa para o N20. Pode ser uma falha real ou um download cortado. Vale baixar de novo no FIRMS para confirmar.

---

## 5. Para a Pessoa C: baixar os focos de uma área

```python
from firewatch.focos import focos_da_area, focos_csv

df = focos_da_area(geometria, "2024-09-01", "2024-09-30")   # geometria em lat/lon (EPSG:4326)
if df.attrs["truncado"]:
    st.warning(df.attrs["aviso"])
st.download_button("Baixar CSV", focos_csv(df), "focos.csv", "text/csv")
```

- A `geometria` pode ser um polígono shapely, um GeoJSON (dict) ou uma linha do `territorios.geojson` (GeoDataFrame).
- A função lê só os meses pedidos, em lotes, e filtra pelo polígono. Para em **500 mil linhas** e avisa.
- Colunas: os nomes originais do FIRMS (`latitude`, `longitude`, `confidence`…), mais `satelite`, `sensor`, `produto`, `data_local` e `id_obs`.
- Inclui todos os satélites, inclusive o N21. Para filtrar: `satelites=["SNPP", "N20"]`.

---

## 6. Memória: cuidado ao rodar scripts pesados

Uma máquina de 7,5 GB de RAM **travou por completo** com scripts sem limite de memória. Por isso, **rode os scripts com `./rodar.sh`**:

```bash
./rodar.sh pipeline/a3_celulas_base.py
MEM=3G ./rodar.sh meu_script.py        # limite diferente (o padrão é 2 GB)
```

Se o script passar do limite, **só ele é encerrado** (código 137), e o computador continua normal. Isso só funciona no Linux com systemd. Em outros sistemas, o `rodar.sh` roda sem limite e mostra um aviso.

Outras dicas:
- Processe em pedaços (por mês, por território).
- Evite `buffer()` em muitos polígonos completos de uma vez.
- No DuckDB, filtre antes de trazer os dados para o pandas.

---

## 7. Se precisar regenerar `saida/`

Normalmente não é preciso. Se algum parâmetro do `config.yaml` mudar:

```bash
./pipeline/rodar_pipeline.sh          # tudo, cerca de 4 min
./pipeline/rodar_pipeline.sh a4 a5    # só algumas etapas
```

| Etapa | Script | Gera | Depende de |
|---|---|---|---|
| a0 | `a0_extrair_zips.py` | CSVs em `data/raw/nasa/` (das zips em `data/raw/zip/`) | — |
| a1 | `a1_observacoes.py` | `observacoes/`, `fontes_fixas.parquet` | a0 |
| a2 | `a2_disponibilidade.py` | `disponibilidade.parquet` | a1 |
| a3 | `a3_celulas_base.py` | `celulas_base.parquet` | a1 |
| a4 | `a4_territorios.py` | `territorios.geojson` | — |
| a5 | `a5_celula_territorio.py` | `celula_territorio.parquet` | a4 |

Os arquivos intermediários ficam em `saida/_tmp/`, fora do Git.

**Nunca escreva números direto no código:** todos os parâmetros (datas, limiares, tamanho da célula) estão no `config.yaml`.

---

## 8. Estrutura

```
FireWatch/
├── README.md               ← este arquivo
├── config.yaml             ← TODOS os parâmetros
├── requirements.txt
├── rodar.sh                ← roda Python com limite de memória
├── firewatch/
│   ├── config.py           ← lê o config.yaml e os caminhos
│   └── focos.py            ← focos_da_area() para o app (A11)
├── pipeline/               ← scripts da Parte A (a0 a a5) + rodar_pipeline.sh
├── tests/test_parte_a.py   ← confere saida/ contra o contrato
├── saida/                  ← arquivos gerados (no Git, prontos para usar)
└── data/                   ← dados brutos (README próprio + auditoria)
```
