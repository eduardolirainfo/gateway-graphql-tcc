from fastapi import FastAPI, HTTPException

app = FastAPI(title="Microsserviço de Usuários")

# Simulando dados para cenário de e-commerce
USUARIOS = {
    "1": {"id": "1", "nome": "Eduardo Lira", "email": "eduardolira@email.com"},
    "2": {"id": "2", "nome": "Alain Fuentes", "email": "alain@email.com"},
    "3": {"id": "3", "nome": "Fulano de Tal", "email": "fulano@email.com"},
}

@app.get("/usuarios")
def listar_usuarios():
    return list(USUARIOS.values())

@app.get("/usuarios/{usuario_id}")
def obter_usuario(usuario_id: str):
    usuario = USUARIOS.get(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario