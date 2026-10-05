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
- **QueryCostLimiter** (`gateway/app/query_cost.py`, `max_cost=50`): bloqueia consultas com muitos campos irmãos/aliases no mesmo nível — cobre ataques de largura que o limitador de profundidade não detecta. Os campos que disparam chamadas downstream (`pedidos`, `produtos` e `produtosNativo`) pesam 5; o `produtosNativo` precisa do mesmo peso porque, com peso 1, 10 aliases dele custariam 36 pontos e passariam pelo limite.
- **Throttling** (`slowapi`): limita a 10 requisições/segundo por cliente (identificado pelo header `X-Client-Id`, com fallback para IP). **Limitação:** o header é controlado pelo cliente, então alternar o valor a cada requisição escapa do limite (verificado: 30 requisições com 30 IDs diferentes, todas 200). Ele é mantido porque o benchmark precisa de um bucket por usuário virtual; em produção a chave deveria ser o IP real atrás de proxy confiável ou uma identidade autenticada.
- **DisableIntrospection**: desativa a exposição do schema (`__schema`) para reduzir a superfície de mapeamento por agentes externos. Está sempre ativo (não depende de variável de ambiente).
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

Para consolidar a Tabela 1 a partir dos CSVs (com desvio-padrão e mín./máx. das médias entre execuções):

```bash
python tests/consolidar_tabela1.py --csv tests/results/tabela1_consolidada.csv
```

Para gerar a Figura 1 (curva de degradação, latência média x usuários) a partir da Tabela 1 consolidada:

```bash
python tests/gerar_figura1.py
```

O ensaio de segurança (throttling e Query Cost, incluindo o caso via `produtosNativo`) roda com:

```bash
docker compose run --rm locust-seguranca -f /mnt/locust/locustfile_seguranca.py \
  --headless --host http://gateway-service:8000 -u 4 -r 4 -t 30s \
  --csv /mnt/locust/results/seguranca_final --only-summary
```

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

Cargas de 10/50/100 usuários: média de 3 execuções de 2 minutos. Carga de 200 usuários: média de **4 execuções limpas** (ver nota abaixo sobre isolamento do host). Todas medem o tempo total para montar a mesma visão agregada (usuários + pedidos + produtos) em cada abordagem:

| Usuários virtuais | REST completo | GraphQL + DataLoader | GraphQL Nativo (N+1) |
|---:|---:|---:|---:|
| 10  | 18,7 | 20,8 | 26,3 |
| 50  | 20,3 | 25,2 | 32,0 |
| 100 | 25,2 | 23,3 | 34,8 |
| 200 | 41,7 | 43,5 | 194,3 |

Falhas: nenhuma em 10/50/100 usuários; a 200 usuários, 0,50 (DataLoader) e 1,00 (Nativo) em média, 0 no REST completo. A leitura principal não é "GraphQL vence REST em latência bruta" — em microsserviços simples e locais, REST completo e GraphQL/DataLoader ficam com latências próximas em todas as cargas (diferença entre -1,9 ms e +4,9 ms, da mesma ordem do desvio-padrão entre execuções, 0,5 a 2,5 ms; sem teste estatístico, a 50 usuários o REST foi 4,9 ms mais rápido). O ganho do DataLoader aparece na comparação com o **GraphQL Nativo (N+1)**, que degrada mais de 4x só de 100 para 200 usuários (34,8ms → 194,3ms) por fazer uma chamada HTTP por produto sem batching — o mesmo problema estrutural que o REST evita apenas porque não existe um endpoint de lote público equivalente para consumidores externos.

#### Nota metodológica: baseline REST

A primeira versão do baseline REST (`tests/locustfile_rest.py`, usada nos runs `rest_run{1,2,3}_*users`) buscava apenas `/usuarios` e `/pedidos`, sem nunca chamar `/produtos` — ou seja, media uma REST fazendo *menos trabalho* do que a consulta GraphQL equivalente (que sempre resolve `produtos { nome preco }`). Isso inflava artificialmente a vantagem do REST. O `tests/locustfile_rest_completo.py` corrige isso buscando cada produto individualmente por pedido, fechando o mesmo grafo de dados retornado pelo GraphQL.

#### Nota metodológica: isolamento do host a 200 usuários

A Tabela 1 acima (versão atual) foi medida **depois** de uma atualização das dependências Python do projeto (correção de vulnerabilidades do Dependabot — ver histórico do repositório), que por si só já mudou a latência medida em relação a uma execução anterior. Além disso, a carga de 200 usuários no cenário Nativo (N+1) mostrou-se muito sensível a qualquer disputa de recursos no host: um processo alheio ao projeto (um SQL Server rodando na mesma máquina, consumindo memória a ponto de causar swap) inflava e desestabilizava as medições nessa carga especificamente (10-100 usuários não foram afetados, por gerar bem menos pressão de memória/CPU). Após parar esse processo, repetimos a carga de 200 usuários 4 vezes por cenário para obter uma média mais robusta — ainda assim, o cenário Nativo (N+1) a 200 usuários apresenta variância residual real (mín. ~165ms, máx. ~240ms entre execuções), o que é consistente com o sistema operando próximo ao limite de saturação de CPU do container (1 vCPU). Os arquivos `rest_run*.csv`, `dl_run*.csv`, `nat_run*.csv` (matriz original) existem só localmente (não são versionados) e `v2_*_run{1,2,3}_200users*.csv` (200 usuários pré-isolamento) são versionados apenas como registro histórico; **nenhum deles entra na Tabela 1** — os valores corretos vêm de `v2_restc/dl/nat_run{1,2,3}_{10,50,100}users*.csv` e `v2_*_run{4,5,6,7}_200users*.csv`, que o `tests/consolidar_tabela1.py` já seleciona.

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
tests/consolidar_tabela1.py     # Gera a Tabela 1 (médias, desvio-padrão, mín./máx.) a partir dos CSVs
tests/gerar_figura1.py          # Gera a Figura 1 (curva de degradação) a partir da Tabela 1 consolidada
tests/results/                  # Apenas os CSVs v2_* e do ensaio de segurança são versionados
prometheus.yml               # Configuração de scraping do Prometheus
docker-compose.yml            # Orquestração de todos os serviços
```
