FROM python:3.14-slim

WORKDIR /app

# Copia as dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY ./app ./app

# Expõe a porta
EXPOSE 8002

# Comando para iniciar o servidor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]