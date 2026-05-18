from fastapi import FastAPI, HTTPException, Query
from typing import List

app = FastAPI(title="Microsserviço de Produtos")

# Dados simulados de produtos para o e-commerce
PRODUTOS = {
    "101": {"id": "101", "nome": "Mouse Gamer Sem Fio RGB", "preco": 150.00},
    "102": {"id": "102", "nome": "Teclado Mecânico Switch Blue", "preco": 350.00},
    "103": {"id": "103", "nome": "Monitor IPS 24 polegadas", "preco": 899.90},
}

@app.get("/produtos")
def listar_produtos():
    return list(PRODUTOS.values())

@app.get("/produtos/lote")
def obter_produtos_por_lote(ids: str = Query(..., description="IDs dos produtos separados por vírgula")):
    """Retorna uma lista de produtos de uma vez só para atender ao DataLoader"""
    lista_ids = ids.split(",")
    resultado = []
    for p_id in lista_ids:
        produto = PRODUTOS.get(p_id.strip())
        if produto:
            resultado.append(produto)
    return resultado

@app.get("/produtos/{produto_id}")
def obter_produto(produto_id: str):
    produto = PRODUTOS.get(produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto