import uuid

from locust import HttpUser, task, between

# Medicao isolada do cenario Nativo (N+1), sem o DataLoader competindo pelo
# mesmo produtos-service. Usado uma unica vez para gerar o baseline
# comparativo da Tabela 1 sob o ambiente controlado atual - nao faz parte
# do benchmark oficial (locustfile.py), que documenta REST + DataLoader.

class BenchmarkNativo(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self.client_id = f"locust-nativo-{uuid.uuid4()}"

    @task(weight=2)
    def testar_rest_direto(self):
        with self.client.get("/usuarios", name="REST: Listar Usuários", catch_response=True) as response:
            if response.status_code == 200:
                usuarios = response.json()
                for usuario in usuarios:
                    u_id = usuario["id"]
                    self.client.get(f"http://pedidos-service:8003/pedidos?usuario_id={u_id}", name="REST: Buscar Pedidos do Usuário")
            else:
                response.failure("Falha ao listar usuários no REST")

    @task(weight=1)
    def testar_graphql_nativo(self):
        """Mesma consulta aninhada, mas via produtosNativo (sem batching) - reproduz o N+1"""
        query = """
        query {
          usuarios {
            nome
            pedidos {
              id
              produtosNativo {
                nome
                preco
              }
            }
          }
        }
        """
        with self.client.post(
            "http://gateway-service:8000/graphql",
            json={"query": query},
            headers={"X-Client-Id": self.client_id},
            name="GraphQL: Nativo (N+1)",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "errors" in data and data["errors"]:
                        response.failure(f"GraphQL Error: {data['errors'][0].get('message', 'Erro desconhecido')}")
                except Exception as e:
                    response.failure(f"Erro ao analisar JSON: {e}")
