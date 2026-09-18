from locust import HttpUser, task, between

# Medicao isolada do baseline REST, sem nenhum trafego GraphQL competindo
# pelos mesmos microsservicos. Usado para gerar a linha "REST" da Tabela 1
# sob total isolamento - nao faz parte do benchmark oficial (locustfile.py).

class BenchmarkRest(HttpUser):
    wait_time = between(1, 2)

    @task
    def testar_rest_direto(self):
        with self.client.get("/usuarios", name="REST: Listar Usuários", catch_response=True) as response:
            if response.status_code == 200:
                usuarios = response.json()
                for usuario in usuarios:
                    u_id = usuario["id"]
                    self.client.get(f"http://pedidos-service:8003/pedidos?usuario_id={u_id}", name="REST: Buscar Pedidos do Usuário")
            else:
                response.failure("Falha ao listar usuários no REST")
