# Reprodutibilidade — guia passo a passo

Este documento mostra, comando por comando, como reproduzir do zero **todo**
número, tabela, figura e afirmação de segurança citados no TCC ("Gateway
GraphQL sobre microsserviços sob carga controlada"). Todo comando abaixo foi
executado e conferido nesta máquina antes de entrar neste documento — nada
aqui é hipotético.

## 0. Pré-requisitos

- Docker e o plugin Docker Compose (`docker compose version`).
- Python 3.10+ com `pip install matplotlib scipy` (para os scripts de
  consolidação, gráfico e teste estatístico em `tests/`).

## 1. Subir o ambiente

```bash
git clone https://github.com/eduardolirainfo/gateway-graphql-tcc.git
cd gateway-graphql-tcc
docker compose up -d usuarios-service produtos-service pedidos-service gateway-service prometheus
```

Confirme que o Gateway responde:

```bash
curl -s -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ usuarios { nome } }"}'
```

Deve retornar os 3 usuários de exemplo (`Eduardo Lira`, `Alain Fuentes`,
`Fulano de Tal`).

### Quero só ver funcionando no navegador, sem rodar comando nenhum

As Figuras 1 e 2 do TCC já são imagens estáticas, embutidas no próprio
`.docx`/`.pdf` — não é preciso rodar nada pra "ver" elas, só abrir o
documento. Os passos abaixo (e o resto deste guia) servem para quem quer
*verificar*/*reproduzir* os números por trás delas, não para visualizá-las.

Dito isso, com o ambiente de pé (passo 1), três interfaces visuais ficam
disponíveis de graça, sem nenhum comando extra:

| O quê | Onde | O que mostra |
|---|---|---|
| GraphiQL (explorador do Gateway) | http://localhost:8000/graphql | Editor de consultas GraphQL interativo, no navegador |
| Prometheus (métricas ao vivo) | http://localhost:9090/graph | Gráficos das queries PromQL (ex.: CPU do Gateway) |
| Locust (benchmark, interface web) | http://localhost:8089 | Dispara carga e mostra gráficos de RPS/latência em tempo real |
| Locust (segurança, interface web) | http://localhost:8090 | Mesma coisa, para os testes de throttling/Query Cost |

As interfaces do Locust só aparecem se ele for iniciado **sem** `--headless`.
Para isso, em vez de `docker compose run --rm ...`, use:

```bash
docker compose up locust-tests       # benchmark, abre em localhost:8089
docker compose up locust-seguranca   # seguranca, abre em localhost:8090
```

Aí é só abrir o endereço no navegador, definir número de usuários e taxa de
spawn, e clicar em "Start" — os gráficos de latência/RPS atualizam ao vivo
na própria página do Locust.

## 2. Reproduzir a Tabela 1 (métricas de desempenho)

A Tabela 1 do TCC usa 3 repetições por carga para 10/50/100 usuários e 4
repetições para 200 usuários (a carga mais sensível à contenção de host — ver
a nota metodológica no README). Cada cenário roda isolado, em bateria
própria, para não disputar os mesmos microsserviços downstream:

| Script | Cenário | `--host` |
|---|---|---|
| `tests/locustfile_rest_completo.py` | REST: Agregação Completa do Cliente | `http://usuarios-service:8001` (URLs internas já são absolutas) |
| `tests/locustfile_nativo.py` | GraphQL Nativo (N+1) + REST | `http://usuarios-service:8001` |
| `tests/locustfile.py` | REST + GraphQL DataLoader (benchmark oficial) | `http://usuarios-service:8001` |

Para cada carga (10, 50, 100, 200) e repetição, rode (exemplo: REST completo,
carga de 50, repetição 1):

```bash
docker compose run --rm locust-tests \
  -f /mnt/locust/locustfile_rest_completo.py \
  --headless --host http://usuarios-service:8001 \
  -u 50 -r 50 -t 2m \
  --csv /mnt/locust/results/v2_restc_run1_50users --only-summary
```

Troque `-f` pelo script (`locustfile_nativo.py` → prefixo `nat`,
`locustfile.py` → prefixo `dl`), `-u`/`--csv` pela carga/repetição, e `-t`
para `2m` (10/50/100 usuários) ou mantenha `2m` também em 200 (a 4ª
repetição é só mais uma rodada igual, não precisa de parâmetro especial).

Cada execução grava `<prefixo>_run<N>_<carga>users_stats.csv` (e
`_failures.csv`) em `tests/results/`. É exatamente esse padrão de nome que
`tests/consolidar_tabela1.py` espera.

### Consolidar a Tabela 1

```bash
python3 tests/consolidar_tabela1.py --csv tests/results/tabela1_consolidada.csv
```

Imprime a tabela com média, desvio-padrão, mínimo e máximo entre execuções —
os mesmos números da Tabela 1 do TCC.

## 3. Gerar a Figura 1 (curva de degradação)

```bash
python3 tests/gerar_figura1.py
```

Lê `tests/results/tabela1_consolidada.csv` e grava
`tests/results/figura1_curva_degradacao.png`.

## 4. Gerar a Figura 2 (utilização de CPU via Prometheus)

Com o ambiente de pé (passo 1), dispare uma carga pesada e, logo em seguida
(ou enquanto ela roda), gere a figura:

```bash
docker compose run --rm locust-tests \
  -f /mnt/locust/locustfile_nativo.py \
  --headless --host http://usuarios-service:8001 \
  -u 200 -r 200 -t 2m --csv /mnt/locust/results/figura2_run --only-summary &

sleep 90
python3 tests/gerar_figura2.py
```

`tests/gerar_figura2.py` consulta a API do Prometheus (`query_range`) pelos
últimos minutos, detecta sozinho o trecho sob carga (onde a CPU sobe acima
da linha de base) para sombrear, e grava
`tests/results/figura2_cpu_utilizacao.png` no mesmo estilo visual da Figura
1. Para um intervalo específico (ex.: reaproveitar um teste já rodado), use
`--inicio`/`--fim` em ISO 8601 UTC:

```bash
python3 tests/gerar_figura2.py --inicio 2026-10-05T06:21:40Z --fim 2026-10-05T06:23:40Z
```

O resultado não é pixel-idêntico ao da Figura 1 do TCC a cada execução — é
telemetria ao vivo, varia entre execuções como qualquer medição deste
projeto (mesma razão da Tabela 1 reportar desvio-padrão) — mas reproduz o
mesmo método e a mesma forma de curva (subida, platô sob carga, queda).

Se preferir só explorar visualmente sem gerar a figura, a interface web do
Prometheus (`http://localhost:9090/graph`, aba "Graph") mostra a mesma
métrica ao vivo — mas é uma ferramenta de depuração, não produz a figura
publicável; para isso, use o script acima.

## 5. Testes de segurança (Throttling e Query Cost Analysis)

```bash
docker compose run --rm locust-seguranca \
  -f /mnt/locust/locustfile_seguranca.py \
  --headless --host http://gateway-service:8000 \
  -u 4 -r 4 -t 30s \
  --csv /mnt/locust/results/seguranca_final --only-summary
```

Resultado esperado: rajadas de um mesmo cliente batendo 429 (throttling) e
consultas com aliases excedendo o custo máximo (50 pontos) sendo bloqueadas
com a mensagem "Custo da consulta excede o limite máximo permitido" — exatamente
o que a seção "Validação de Segurança e Throttling" do TCC descreve.

## 6. Teste estatístico (REST x DataLoader)

```bash
pip install scipy  # se ainda não tiver
python3 tests/teste_estatistico.py
```

Roda um teste-t pareado por carga sobre os CSVs reais de `tests/results/`
(os mesmos `v2_restc_run*`/`v2_dl_run*` usados na Tabela 1) usando
`scipy.stats.ttest_rel`. Resultado: só a carga de 50 usuários tem diferença
estatisticamente significativa (p ≈ 0,016); nas demais cargas a diferença
está dentro do ruído (p > 0,05).

## 7. Mapa: o que no TCC vem de qual comando

| No TCC | Como reproduzir |
|---|---|
| Tabela 1 | Passo 2 (todas as repetições) + `consolidar_tabela1.py` |
| Figura 1 | Passo 3 |
| Figura 2 | Passo 4 |
| "rajadas... retornando 429" / "Custo da consulta excede..." | Passo 5 |
| Comparação REST x DataLoader (desvio-padrão, "sem teste estatístico") | Passo 2, dados brutos |
| Teste-t citado como verificação adicional | Passo 6 |

## 8. Encerrar o ambiente

```bash
docker compose down
```

---

Qualquer divergência nos números em relação ao TCC dentro da margem de
desvio-padrão reportada (ver Tabela 1 e a nota metodológica no README) é
esperada — é a mesma variância documentada entre execuções no próprio
trabalho, por causa de carga do host local.
