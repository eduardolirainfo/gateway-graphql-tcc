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
| `tests/locustfile_rest.py` | Apenas REST | Baseline REST 100% isolado |
| `tests/locustfile_seguranca.py` | Rajadas (throttling) e queries com aliases (Query Cost) | Validação de segurança |

**Interface web** (exploração manual): acesse `http://localhost:8089` (benchmark) ou `http://localhost:8090` (segurança) e configure usuários virtuais e taxa de spawn.

**Modo headless** (reprodução da Tabela 1 — 3 repetições por carga, conforme a Metodologia): para cada script e cada carga (10, 50, 100, 200 usuários), rode:

```bash
docker compose run --rm locust-tests \
  -f /mnt/locust/locustfile.py \
  --headless \
  --host http://usuarios-service:8001 \
  -u 50 -r 50 -t 2m \
  --csv /mnt/locust/results/run1_50users \
  --only-summary
```

Troque `-f` pelo script desejado e `-u`/`--csv` pela carga/repetição. Os arquivos `*_stats.csv` resultantes contêm Total de Requisições, RPS, Latência Média, percentis e Falhas — a mesma tabela é obtida tirando a média aritmética das 3 repetições de cada carga.

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
tests/locustfile.py         # Benchmark oficial (REST + DataLoader)
tests/locustfile_nativo.py  # Baseline isolado do GraphQL Nativo (N+1)
tests/locustfile_rest.py    # Baseline isolado do REST
tests/locustfile_seguranca.py # Testes de throttling e Query Cost Analysis
prometheus.yml               # Configuração de scraping do Prometheus
docker-compose.yml            # Orquestração de todos os serviços
```
