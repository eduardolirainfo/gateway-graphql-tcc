import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI
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

async def load_produtos(keys: List[str]) -> List[ProdutoType]:
    ids_str = ",".join(keys)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://produtos-service:8002/produtos/lote?ids={ids_str}")
        if response.status_code == 200:
            produtos_dados = response.json()
            produtos_map = {p["id"]: ProdutoType(**p) for p in produtos_dados}
            return [produtos_map.get(k) for k in keys]
    return [None] * len(keys)

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
    async def pedidos(self) -> List[PedidoType]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://pedidos-service:8003/pedidos?usuario_id={self.id}")
            dados = response.json()
            return [PedidoType(**p) for p in dados]

async def get_usuarios() -> List[UsuarioType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://usuarios-service:8001/usuarios")
        dados = response.json()
        return [UsuarioType(**u) for u in dados]

@strawberry.type
class Query:
    usuarios: List[UsuarioType] = strawberry.field(resolver=get_usuarios)

async def custom_context():
    return {
        "produtos_loader": DataLoader(load_fn=load_produtos)
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

app = FastAPI(title="Gateway GraphQL Otimizado e Protegido - TCC")
app.include_router(graphql_app, prefix="/graphql")

# Instrumentação do Prometheus
Instrumentator().instrument(app).expose(app)
