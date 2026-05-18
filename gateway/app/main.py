import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI
import httpx
from typing import List
from strawberry.dataloader import DataLoader

# 1. Definição dos Tipos GraphQL
@strawberry.type
class ProdutoType:
    id: str
    nome: str
    preco: float

# Função de carga em lote (Batch Function) exigida pelo DataLoader
async def load_produtos(keys: List[str]) -> List[ProdutoType]:
    # keys é uma lista com todos os IDs coletados pelo GraphQL, ex: ["101", "102", "103"]
    ids_str = ",".join(keys)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://produtos-service:8002/produtos/lote?ids={ids_str}")
        if response.status_code == 200:
            produtos_dados = response.json()
            # Mapeia em um dicionário para garantir o retorno na ordem exata solicitada pelas keys
            produtos_map = {p["id"]: ProdutoType(**p) for p in produtos_dados}
            return [produtos_map.get(k) for k in keys]
    return [None] * len(keys)

@strawberry.type
class PedidoType:
    id: str
    usuario_id: str
    produto_ids: List[str]

    # Resolver Otimizado: Intercepta a chamada e repassa os IDs ao DataLoader
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

# 2. Consulta de Entrada (Root Query)
async def get_usuarios() -> List[UsuarioType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://usuarios-service:8001/usuarios")
        dados = response.json()
        return [UsuarioType(**u) for u in dados]

@strawberry.type
class Query:
    usuarios: List[UsuarioType] = strawberry.field(resolver=get_usuarios)

# 3. Contexto Customizado para instanciar o DataLoader por requisição
async def custom_context():
    return {
        "produtos_loader": DataLoader(load_fn=load_produtos)
    }

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema, context_getter=custom_context)

app = FastAPI(title="Gateway GraphQL Otimizado - TCC")
app.include_router(graphql_app, prefix="/graphql")

# CONFIGURAÇÃO REAL DO PROMETHEUS AQUI:
from prometheus_fastapi_instrumentator import Instrumentator

# Isso aqui captura automaticamente as latências de todas as requisições e cria o endpoint /metrics
Instrumentator().instrument(app).expose(app)