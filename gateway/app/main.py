import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import Depends, FastAPI, Request
from contextlib import asynccontextmanager
import httpx
from typing import List
from strawberry.dataloader import DataLoader
# 1. IMPORTAR O LIMITADOR DE PROFUNDIDADE NATIVO E DESABILITAR INTROSPECÇÃO
from strawberry.extensions import QueryDepthLimiter, DisableIntrospection
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .query_cost import QueryCostLimiter

@strawberry.type
class ProdutoType:
    id: str
    nome: str
    preco: float

@strawberry.type
class PedidoType:
    id: str
    usuario_id: str
    produto_ids: List[str]

    @strawberry.field
    async def produtos(self, info: strawberry.Info) -> List[ProdutoType]:
        loader = info.context["produtos_loader"]
        return await loader.load_many(self.produto_ids)

    @strawberry.field
    async def produtos_nativo(self, info: strawberry.Info) -> List[ProdutoType]:
        # Reproduz o cenario pre-DataLoader (uma chamada HTTP por produto)
        # usando o mesmo client persistente, para comparacao isolada na
        # Tabela 1 sob o ambiente controlado atual.
        client = info.context["client"]
        produtos = []
        for produto_id in self.produto_ids:
            response = await client.get(f"http://produtos-service:8002/produtos/{produto_id}")
            response.raise_for_status()
            produtos.append(ProdutoType(**response.json()))
        return produtos

@strawberry.type
class UsuarioType:
    id: str
    nome: str
    email: str

    @strawberry.field
    async def pedidos(self, info: strawberry.Info) -> List[PedidoType]:
        client = info.context["client"]
        response = await client.get(f"http://pedidos-service:8003/pedidos?usuario_id={self.id}")
        response.raise_for_status()
        dados = response.json()
        return [PedidoType(**p) for p in dados]

async def get_usuarios(info: strawberry.Info) -> List[UsuarioType]:
    client = info.context["client"]
    response = await client.get("http://usuarios-service:8001/usuarios")
    response.raise_for_status()
    dados = response.json()
    return [UsuarioType(**u) for u in dados]

@strawberry.type
class Query:
    usuarios: List[UsuarioType] = strawberry.field(resolver=get_usuarios)

async def custom_context(request: Request):
    client = request.app.state.http_client
    
    async def load_produtos(keys: List[str]) -> List[ProdutoType]:
        ids_str = ",".join(keys)
        response = await client.get(f"http://produtos-service:8002/produtos/lote?ids={ids_str}")
        response.raise_for_status()
        produtos_dados = response.json()
        produtos_map = {p["id"]: ProdutoType(**p) for p in produtos_dados}
        return [produtos_map.get(k) for k in keys]

    return {
        "produtos_loader": DataLoader(load_fn=load_produtos),
        "client": client
    }

# 2. ATIVAR A EXTENSÃO COM LIMITE MÁXIMO DE 3 NÍVEIS, CUSTO DE CONSULTA E DESABILITAR INTROSPECÇÃO
# Pesos maiores para pedidos/produtos: campos que disparam chamadas HTTP
# downstream por item resolvido, cobrindo ataques de largura (aliases
# repetidos) que o QueryDepthLimiter, sozinho, não detecta.
# produtosNativo (baseline N+1 da Tabela 1) tem o mesmo peso de produtos: sem
# isso, aliases repetidos dele custariam 3 pontos cada e escapariam do limite.
schema = strawberry.Schema(
    query=Query,
    extensions=[
        QueryDepthLimiter(max_depth=3),
        QueryCostLimiter(
            max_cost=50,
            field_costs={"pedidos": 5, "produtos": 5, "produtosNativo": 5},
        ),
        DisableIntrospection()
    ]
)

graphql_app = GraphQLRouter(schema, context_getter=custom_context)

# 3. THROTTLING: limite de requisições por cliente (identificado pelo header
# X-Client-Id; sem o header, cai no IP de origem).
# Limitação conhecida: o header é controlado pelo cliente, então quem alterna
# o valor a cada requisição escapa do limite. Ele é mantido porque o benchmark
# precisa de um bucket por usuário virtual (todos saem do mesmo IP). Em
# produção, a chave deveria ser o IP real (atrás de proxy confiável) ou uma
# identidade autenticada.
def get_client_identifier(request: Request) -> str:
    return request.headers.get("X-Client-Id", get_remote_address(request))

limiter = Limiter(key_func=get_client_identifier)

@limiter.limit("10/second")
async def enforce_rate_limit(request: Request) -> None:
    return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()

app = FastAPI(title="Gateway GraphQL Otimizado e Protegido - TCC", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(graphql_app, prefix="/graphql", dependencies=[Depends(enforce_rate_limit)])

# Instrumentação do Prometheus
Instrumentator().instrument(app).expose(app)
