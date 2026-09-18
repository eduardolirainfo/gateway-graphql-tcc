from fastapi import FastAPI, HTTPException
from typing import List, Optional

app = FastAPI(title="Microsserviço de Pedidos")

# Dados simulados relacionando os IDs de usuários e produtos
PEDIDOS = [
    {"id": "901", "usuario_id": "1", "produto_ids": ["101", "102"]},
    {"id": "902", "usuario_id": "1", "produto_ids": ["103"]},
    {"id": "903", "usuario_id": "2", "produto_ids": ["102"]},
]

@app.get("/pedidos")
def listar_pedidos(usuario_id: Optional[str] = None):
    # Permite filtrar os pedidos de um usuário específico (útil para o gateway)
    if usuario_id:
        filtrados = [p for p in PEDIDOS if p["usuario_id"] == usuario_id]
        return filtrados
    return PEDIDOS

@app.get("/pedidos/{pedido_id}")
def obter_pedido(pedido_id: str):
    for pedido in PEDIDOS:
        if pedido["id"] == pedido_id:
            return pedido
    raise HTTPException(status_code=404, detail="Pedido não encontrado")

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)