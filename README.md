# Gateway GraphQL sobre Microsserviços

Projeto experimental de TCC que avalia o impacto de desempenho e a escalabilidade de um **API Gateway GraphQL** (Python + [Strawberry](https://strawberry.rocks/)) atuando sobre um ecossistema de microsserviços **REST** puros (Usuários, Pedidos e Produtos), com foco no problema de consultas em cascata (N+1), nas estratégias de mitigação e em governança de borda (segurança).

## Arquitetura

```
                        ┌──────────────────────┐
   Cliente / Locust ───▶│  Gateway GraphQL       │  :8000
                        │  (Strawberry/FastAPI) │
                        └───────────┬───────────┘
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
           usuarios-service  pedidos-service  produtos-service
                :8001             :8003            :8002
```

- **usuarios-service**, **pedidos-service**, **produtos-service**: microsserviços REST independentes (FastAPI), servindo como baseline de desempenho.
- **gateway-service**: Gateway GraphQL que compõe os dados dos três microsserviços em uma única consulta.
- **prometheus**: coleta métricas de CPU/threads dos serviços em `/metrics` (telemetria complementar; as métricas de latência/RPS da Tabela 1 vêm do Locust).
- **locust-tests**: injeta carga sintética (10 a 200 usuários virtuais) para medir a curva de degradação do sistema (REST + GraphQL/DataLoader).
- **locust-seguranca**: testa throttling e Query Cost Analysis contra tráfego abusivo.

## Estratégias de otimização e governança implementadas

- **DataLoader** (`strawberry.dataloader.DataLoader`): agrupa (batching) as chamadas de produtos por pedido em uma única requisição ao endpoint `/produtos/lote`, eliminando o problema N+1.
- **Client HTTP persistente**: um único `httpx.AsyncClient` por processo (criado no `lifespan` do FastAPI), evitando reabertura de conexão TCP a cada requisição.
- **QueryDepthLimiter** (`max_depth=3`): bloqueia consultas GraphQL com aninhamento acima do limite seguro.
- **QueryCostLimiter** (`gateway/app/query_cost.py`, `max_cost=50`): bloqueia consultas com muitos campos irmãos/aliases no mesmo nível — cobre ataques de largura que o limitador de profundidade não detecta.
- **Throttling** (`slowapi`): limita a 10 requisições/segundo por cliente (identificado pelo header `X-Client-Id`, com fallback para IP).
- **DisableIntrospection**: desativa a exposição do schema (`__schema`) para reduzir a superfície de mapeamento por agentes externos.
- **Instrumentação Prometheus** (`prometheus-fastapi-instrumentator`): expõe métricas em `/metrics` nos 4 serviços (gateway, usuários, pedidos, produtos).

## Como rodar

Pré-requisitos: Docker e Docker Compose.

```bash
docker compose up --build
```

Serviços disponíveis:

| Serviço              | URL                              |
|----------------------|-----------------------------------|
| Gateway GraphQL       | http://localhost:8000/graphql    |
| Microsserviço Usuários| http://localhost:8001             |
| Microsserviço Produtos| http://localhost:8002             |
| Microsserviço Pedidos | http://localhost:8003             |
| Prometheus            | http://localhost:9090             |
| Locust (benchmark, interface web) | http://localhost:8089 |
| Locust (segurança, interface web) | http://localhost:8090 |

## Testes de carga

Três scripts, cada um com um propósito isolado (evita que um padrão de tráfego contamine a medição do outro ao disputar os mesmos microsserviços downstream):

| Script | Tráfego | Uso |
|---|---|---|
| `tests/locustfile.py` | REST + GraphQL/DataLoader | Benchmark oficial (mesma sessão, pesos 2:1) |
| `tests/locustfile_nativo.py` | REST + GraphQL Nativo (sem batching, campo `produtosNativo`) | Baseline comparativo isolado do N+1 |
| `tests/locustfile_rest_completo.py` | Apenas REST, agregação completa (usuários + pedidos + produtos) | Baseline REST 100% isolado, usado na Tabela 1 |
| `tests/locustfile_rest.py` | Apenas REST, incompleto (não busca produtos) | **Descontinuado** — comparação injusta com o GraphQL, mantido só como registro histórico (ver [Nota metodológica](#nota-metodológica-baseline-rest)) |
| `tests/locustfile_seguranca.py` | Rajadas (throttling) e queries com aliases (Query Cost) | Validação de segurança |

**Interface web** (exploração manual): acesse `http://localhost:8089` (benchmark) ou `http://localhost:8090` (segurança) e configure usuários virtuais e taxa de spawn.

**Modo headless** (reprodução da Tabela 1 — 3 repetições por carga, conforme a Metodologia): para cada script e cada carga (10, 50, 100, 200 usuários), rode:

```bash
docker compose run --rm locust-tests \
  -f /mnt/locust/locustfile_rest_completo.py \
  --headless \
  --host http://usuarios-service:8001 \
  -u 50 -r 50 -t 2m \
  --csv /mnt/locust/results/restc_run1_50users \
  --only-summary
```

Troque `-f` pelo script desejado e `-u`/`--csv` pela carga/repetição. Os arquivos `*_stats.csv` resultantes contêm Total de Requisições, RPS, Latência Média, percentis e Falhas — a mesma tabela é obtida tirando a média aritmética das 3 repetições de cada carga.

### Tabela 1 — Latência média por carga (ms)

Média de 3 execuções de 2 minutos por carga, medindo o tempo total para montar a mesma visão agregada (usuários + pedidos + produtos) em cada abordagem:

| Usuários virtuais | REST completo | GraphQL + DataLoader | GraphQL Nativo (N+1) |
|---:|---:|---:|---:|
| 10  | 21,6 | 20,1 | 27,1 |
| 50  | 24,9 | 23,3 | 44,0 |
| 100 | 23,1 | 24,3 | 62,9 |
| 200 | 41,2 | 38,1 | 151,0 |

Nenhuma execução registrou falhas. A leitura principal não é "GraphQL vence REST em latência bruta" — em microsserviços simples e locais, REST completo e GraphQL/DataLoader ficam estatisticamente empatados (diferença dentro do ruído de medição). O ganho do DataLoader aparece na comparação com o **GraphQL Nativo (N+1)**, que degrada mais de 5x sob carga (27ms → 151ms) por fazer uma chamada HTTP por produto sem batching — o mesmo problema estrutural que o REST evita apenas porque não existe um endpoint de lote público equivalente para consumidores externos.

#### Nota metodológica: baseline REST

A primeira versão do baseline REST (`tests/locustfile_rest.py`, usada nos runs `rest_run{1,2,3}_*users`) buscava apenas `/usuarios` e `/pedidos`, sem nunca chamar `/produtos` — ou seja, media uma REST fazendo *menos trabalho* do que a consulta GraphQL equivalente (que sempre resolve `produtos { nome preco }`). Isso inflava artificialmente a vantagem do REST. O `tests/locustfile_rest_completo.py` corrige isso buscando cada produto individualmente por pedido, fechando o mesmo grafo de dados retornado pelo GraphQL. Os arquivos `rest_run*.csv` foram mantidos no repositório como registro do problema, mas **não devem ser usados na Tabela 1** — os valores corretos vêm de `restc_run*.csv`.

## Exemplo de consulta GraphQL

```graphql
query {
  usuarios {
    nome
    pedidos {
      id
      produtos {
        nome
        preco
      }
    }
  }
}
```

O campo `produtosNativo` (em vez de `produtos`) reproduz o comportamento pré-DataLoader (uma chamada HTTP por produto), usado apenas para a comparação isolada da Tabela 1.

## Estrutura do repositório

```
gateway/                    # API Gateway GraphQL (Strawberry + FastAPI)
gateway/app/query_cost.py   # Extensão customizada de Query Cost Analysis
services/usuarios/          # Microsserviço REST de Usuários
services/pedidos/           # Microsserviço REST de Pedidos
services/produtos/          # Microsserviço REST de Produtos
tests/locustfile.py             # Benchmark oficial (REST + DataLoader)
tests/locustfile_nativo.py      # Baseline isolado do GraphQL Nativo (N+1)
tests/locustfile_rest_completo.py # Baseline isolado do REST (usuários + pedidos + produtos) — usado na Tabela 1
tests/locustfile_rest.py        # Baseline REST antigo/incompleto — descontinuado, ver Nota metodológica
tests/locustfile_seguranca.py   # Testes de throttling e Query Cost Analysis
prometheus.yml               # Configuração de scraping do Prometheus
docker-compose.yml            # Orquestração de todos os serviços
```
