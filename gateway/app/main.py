import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import httpx
from typing import List
from strawberry.dataloader import DataLoader
# 1. IMPORTAR O LIMITADOR DE PROFUNDIDADE NATIVO E DESABILITAR INTROSPECÇÃO
from strawberry.extensions import QueryDepthLimiter, DisableIntrospection
from prometheus_fastapi_instrumentator import Instrumentator

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

# 2. ATIVAR A EXTENSÃO COM LIMITE MÁXIMO DE 3 NÍVEIS E DESABILITAR INTROSPECÇÃO
schema = strawberry.Schema(
    query=Query, 
    extensions=[
        QueryDepthLimiter(max_depth=3),
        DisableIntrospection()
    ]
)

graphql_app = GraphQLRouter(schema, context_getter=custom_context)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()

app = FastAPI(title="Gateway GraphQL Otimizado e Protegido - TCC", lifespan=lifespan)
app.include_router(graphql_app, prefix="/graphql")

# Instrumentação do Prometheus
Instrumentator().instrument(app).expose(app)
