# Gateway GraphQL sobre Microsserviços

Projeto experimental de TCC que avalia o impacto de desempenho e a escalabilidade de um **API Gateway GraphQL** (Python + [Strawberry](https://strawberry.rocks/)) atuando sobre um ecossistema de microsserviços **REST** puros (Usuários, Pedidos e Produtos), com foco no problema de consultas em cascata (N+1) e nas estratégias de mitigação.

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
- **prometheus**: coleta métricas de latência/erros expostas pelos serviços em `/metrics`.
- **locust-tests**: injeta carga sintética (10 a 200 usuários virtuais) para medir a curva de degradação do sistema.

## Estratégias de otimização e governança implementadas

- **DataLoader** (`strawberry.dataloader.DataLoader`): agrupa (batching) as chamadas de produtos por pedido em uma única requisição ao endpoint `/produtos/lote`, eliminando o problema N+1.
- **QueryDepthLimiter** (`max_depth=3`): bloqueia consultas GraphQL com aninhamento acima do limite seguro, protegendo a CPU do servidor contra queries abusivas.
- **DisableIntrospection**: desativa a exposição do schema (`__schema`) para reduzir a superfície de mapeamento por agentes externos.
- **Instrumentação Prometheus** (`prometheus-fastapi-instrumentator`): expõe métricas de latência e taxa de erro em `/metrics`.

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
| Locust (interface web)| http://localhost:8089             |

## Testes de carga

O script `tests/locustfile.py` simula dois tipos de tráfego:

- Chamadas REST diretas aos microsserviços (baseline).
- Uma consulta GraphQL aninhada (`usuarios → pedidos → produtos`) contra o Gateway, usada para reproduzir e medir o problema N+1 e o efeito do DataLoader.

Acesse `http://localhost:8089` após subir os containers para configurar o número de usuários virtuais e a taxa de spawn.

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

## Estrutura do repositório

```
gateway/            # API Gateway GraphQL (Strawberry + FastAPI)
services/usuarios/  # Microsserviço REST de Usuários
services/pedidos/   # Microsserviço REST de Pedidos
services/produtos/  # Microsserviço REST de Produtos
tests/locustfile.py # Script de testes de carga (Locust)
prometheus.yml       # Configuração de scraping do Prometheus
docker-compose.yml    # Orquestração de todos os serviços
```
