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

# Mesmo ataque de largura, mas pelo campo produtosNativo (sem batching): cada
# alias dispara uma chamada HTTP por produto. Precisa ser barrado como o
# ataque acima; com peso 1 ele custaria 36 pontos e passaria pelo limite de 50.
QUERY_ALIAS_ABUSO_NATIVO = QUERY_ALIAS_ABUSO.replace("produtos {", "produtosNativo {")


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
            # Registra como falha: throttling que nunca dispara invalida o ensaio.
            self.environment.events.request.fire(
                request_type="POST",
                name="Seguranca: Rajada sem nenhum 429 (throttling nao disparou)",
                response_time=0,
                response_length=0,
                exception=AssertionError(f"Nenhum 429 em {len(respostas)} requisicoes"),
            )


class QueryCostAbuseUser(HttpUser):
    """Envia uma consulta com muitos campos irmãos (aliases) para estourar
    o limite de custo (max_cost=50) sem violar a profundidade máxima (3)."""

    wait_time = between(1, 2)

    @task
    def consulta_custo_excessivo(self):
        self._enviar(
            QUERY_ALIAS_ABUSO,
            "Seguranca: Consulta com Custo Excessivo (bloqueio esperado)",
        )

    @task
    def consulta_custo_excessivo_nativo(self):
        self._enviar(
            QUERY_ALIAS_ABUSO_NATIVO,
            "Seguranca: Custo Excessivo via produtosNativo (bloqueio esperado)",
        )

    def _enviar(self, query: str, name: str):
        with self.client.post(
            "http://gateway-service:8000/graphql",
            json={"query": query},
            name=name,
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
