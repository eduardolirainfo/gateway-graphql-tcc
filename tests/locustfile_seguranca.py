import uuid

from locust import HttpUser, task, between

QUERY_ALIAS_ABUSO = """
query {
  usuarios {
    pedidos {
      p0: produtos { nome preco }
      p1: produtos { nome preco }
      p2: produtos { nome preco }
      p3: produtos { nome preco }
      p4: produtos { nome preco }
      p5: produtos { nome preco }
      p6: produtos { nome preco }
      p7: produtos { nome preco }
      p8: produtos { nome preco }
      p9: produtos { nome preco }
    }
  }
}
"""


class ThrottlingAbuseUser(HttpUser):
    """Dispara rajadas de requisições com o mesmo X-Client-Id para estourar
    o limite de 10 req/s do throttling (slowapi) no Gateway."""

    wait_time = between(2, 4)

    def on_start(self):
        self.client_id = f"locust-throttle-{uuid.uuid4()}"

    @task
    def rajada_mesmo_cliente(self):
        query = "query { __typename }"
        respostas = []
        for _ in range(15):
            with self.client.post(
                "http://gateway-service:8000/graphql",
                json={"query": query},
                headers={"X-Client-Id": self.client_id},
                name="Seguranca: Rajada de Throttling (429 esperado)",
                catch_response=True,
            ) as response:
                respostas.append(response.status_code)
                if response.status_code in (200, 429):
                    response.success()
                else:
                    response.failure(f"Status inesperado: {response.status_code}")

        if 429 not in respostas:
            pass  # a rajada não atingiu o limite; ver latência de rede do ambiente


class QueryCostAbuseUser(HttpUser):
    """Envia uma consulta com muitos campos irmãos (aliases) para estourar
    o limite de custo (max_cost=50) sem violar a profundidade máxima (3)."""

    wait_time = between(1, 2)

    @task
    def consulta_custo_excessivo(self):
        with self.client.post(
            "http://gateway-service:8000/graphql",
            json={"query": QUERY_ALIAS_ABUSO},
            name="Seguranca: Consulta com Custo Excessivo (bloqueio esperado)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status inesperado: {response.status_code}")
                return
            data = response.json()
            errors = data.get("errors") or []
            if any("Custo da consulta" in e.get("message", "") for e in errors):
                response.success()
            else:
                response.failure("Consulta de custo excessivo não foi bloqueada")
