import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI
import httpx
from typing import List

# 1. Definição dos Tipos com os Resolvers de Relacionamento (Gera o comportamento N+1)
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

    # Resolver aninhado: Para CADA pedido, vai fazer requisições HTTP para o serviço de produtos
    @strawberry.field
    async def produtos(self) -> List[ProdutoType]:
        detalhes_produtos = []
        async with httpx.AsyncClient() as client:
            for p_id in self.produto_ids:
                # Dispara uma chamada REST por ID de produto (Padrão N+1 em cascata)
                response = await client.get(f"http://produtos-service:8002/produtos/{p_id}")
                if response.status_code == 200:
                    detalhes_produtos.append(ProdutoType(**response.json()))
        return detalhes_produtos

@strawberry.type
class UsuarioType:
    id: str
    nome: str
    email: str

    # Resolver aninhado: Para CADA usuário, busca a lista de pedidos dele no microsserviço
    @strawberry.field
    async def pedidos(self) -> List[PedidoType]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://pedidos-service:8003/pedidos?usuario_id={self.id}")
            dados = response.json()
            return [PedidoType(**p) for p in dados]

# 2. Consultas de Entrada (Root Queries)
async def get_usuarios() -> List[UsuarioType]:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://usuarios-service:8001/usuarios")
        dados = response.json()
        return [UsuarioType(**u) for u in dados]

@strawberry.type
class Query:
    usuarios: List[UsuarioType] = strawberry.field(resolver=get_usuarios)

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="Gateway GraphQL - TCC")
app.include_router(graphql_app, prefix="/graphql")