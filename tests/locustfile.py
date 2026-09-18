from locust import HttpUser, task, between

class BenchmarkUsuario(HttpUser):
    # Tempo de espera simulado entre as requisições de cada usuário (1 a 2 segundos)
    wait_time = between(1, 2)

    @task(weight=2)
    def testar_rest_direto(self):
        """Simula um cliente buscando dados diretamente via REST nos microsserviços"""
        # No Locust, o 'client' vai bater na URL base que definirmos na interface.
        # Para o teste REST, vamos apontar diretamente para o serviço de usuários.
        with self.client.get("/usuarios", name="REST: Listar Usuários", catch_response=True) as response:
            if response.status_code == 200:
                usuarios = response.json()
                for usuario in usuarios:
                    # Simula o frontend buscando os pedidos de cada usuário exposto
                    u_id = usuario["id"]
                    self.client.get(f"http://pedidos-service:8003/pedidos?usuario_id={u_id}", name="REST: Buscar Pedidos do Usuário")
            else:
                response.failure("Falha ao listar usuários no REST")

    @task(weight=1)
    def testar_graphql_aninhado(self):
        """Dispara a consulta complexa aninhada (N+1) contra o Gateway GraphQL"""
        query = """
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
        """
        # O gateway roda na porta 8000, faremos o post na rota /graphql
        with self.client.post(
            "http://gateway-service:8000/graphql",
            json={"query": query},
            name="GraphQL: Consulta Aninhada Complexa (N+1)",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "errors" in data and data["errors"]:
                        response.failure(f"GraphQL Error: {data['errors'][0].get('message', 'Erro desconhecido')}")
                except Exception as e:
                    response.failure(f"Erro ao analisar JSON: {e}")