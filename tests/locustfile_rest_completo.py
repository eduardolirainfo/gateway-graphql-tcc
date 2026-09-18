import time

import requests
from locust import HttpUser, task, between

# Comparacao justa com o GraphQL: mede o tempo TOTAL que um cliente REST
# precisaria para montar a mesma visao completa (usuarios + pedidos +
# produtos) que uma unica consulta GraphQL retorna. Sem um gateway/DataLoader,
# o cliente precisa buscar cada produto individualmente (nao existe endpoint
# de lote publico para consumidores REST) - e essa e a jornada cronometrada
# aqui como uma unica unidade logica, para comparar com "GraphQL: DataLoader".

USUARIOS_URL = "http://usuarios-service:8001/usuarios"
PEDIDOS_URL = "http://pedidos-service:8003/pedidos"
PRODUTO_URL = "http://produtos-service:8002/produtos/{}"


class BenchmarkRestCompleto(HttpUser):
    wait_time = between(1, 2)

    @task
    def agregar_visao_completa(self):
        start = time.time()
        total_bytes = 0
        try:
            session = requests.Session()

            r = session.get(USUARIOS_URL, timeout=10)
            r.raise_for_status()
            total_bytes += len(r.content)
            usuarios = r.json()

            for usuario in usuarios:
                r = session.get(PEDIDOS_URL, params={"usuario_id": usuario["id"]}, timeout=10)
                r.raise_for_status()
                total_bytes += len(r.content)
                pedidos = r.json()

                for pedido in pedidos:
                    for produto_id in pedido["produto_ids"]:
                        r = session.get(PRODUTO_URL.format(produto_id), timeout=10)
                        r.raise_for_status()
                        total_bytes += len(r.content)

            elapsed_ms = (time.time() - start) * 1000
            self.environment.events.request.fire(
                request_type="WORKFLOW",
                name="REST: Agregação Completa do Cliente",
                response_time=elapsed_ms,
                response_length=total_bytes,
                exception=None,
            )
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.environment.events.request.fire(
                request_type="WORKFLOW",
                name="REST: Agregação Completa do Cliente",
                response_time=elapsed_ms,
                response_length=total_bytes,
                exception=e,
            )
