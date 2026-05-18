import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI
import httpx
from typing import List

# 1. Definição dos Tipos GraphQL que espelham nossos microsserviços REST
@strawberry.type
class UsuarioType:
    id: str
    nome: str
    email: str

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

# 2. Resoluções das consultas (Resolvers) buscando dados via HTTP assíncrono
async def get_usuarios() -> List[UsuarioType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://usuarios-service:8001/usuarios")
        dados = response.json()
        return [UsuarioType(**u) for u in dados]

async def get_produtos() -> List[ProdutoType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://produtos-service:8002/produtos")
        dados = response.json()
        return [ProdutoType(**p) for p in dados]

async def get_pedidos() -> List[PedidoType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://pedidos-service:8003/pedidos")
        dados = response.json()
        return [PedidoType(**p) for p in dados]

# 3. Mapeamento das Consultas (Shallow Queries) no Schema
@strawberry.type
class Query:
    usuarios: List[UsuarioType] = strawberry.field(resolver=get_usuarios)
    produtos: List[ProdutoType] = strawberry.field(resolver=get_produtos)
    pedidos: List[PedidoType] = strawberry.field(resolver=get_pedidos)

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="Gateway GraphQL - TCC")
app.include_router(graphql_app, prefix="/graphql")