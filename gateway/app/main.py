import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI

@strawberry.type
class Query:
    @strawberry.field
    def ping(self) -> str:
        return "pong"

# Cria o schema do Strawberry e injeta na rota do FastAPI
schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="Gateway GraphQL - TCC")
app.include_router(graphql_app, prefix="/graphql")