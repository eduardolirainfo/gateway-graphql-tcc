"""Gera a Figura 2 do TCC (utilização de CPU do Gateway sob carga) a partir
de dados reais do Prometheus.

Uso típico: rodar um teste de carga pesado (ex.: locustfile_nativo.py com
200 usuários) e, logo em seguida (ou enquanto ele roda), executar:

    python tests/gerar_figura2.py

Por padrão, consulta os últimos 6 minutos de telemetria na API do
Prometheus (supondo que ele esteja em http://localhost:9090, como no
docker-compose.yml) e detecta automaticamente o trecho sob carga (onde o
uso de CPU sobe acima da linha de base) para sombrear no gráfico. Para um
intervalo específico, use --inicio/--fim (ISO 8601, UTC).

Exemplo com intervalo explícito:
    python tests/gerar_figura2.py --inicio 2026-10-05T06:20:30Z --fim 2026-10-05T06:24:30Z
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

RESULTS = Path(__file__).parent / "results"
QUERY = 'rate(process_cpu_seconds_total{job="graphql-gateway"}[30s])'
LIMITE_VCPU = 1.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--prometheus", default="http://localhost:9090")
    p.add_argument("--inicio", help="ISO 8601 UTC, ex.: 2026-10-05T06:20:00Z")
    p.add_argument("--fim", help="ISO 8601 UTC, ex.: 2026-10-05T06:24:30Z")
    p.add_argument("--minutos", type=int, default=6,
                    help="janela a consultar, se --inicio/--fim nao forem dados")
    p.add_argument("--cenario", default="Nativo (N+1), 200 usuários",
                    help="texto do cenario para o subtitulo/legenda sombreada")
    p.add_argument("--saida", default=str(RESULTS / "figura2_cpu_utilizacao.png"))
    return p.parse_args()


def consultar_prometheus(base_url, inicio, fim, passo="5s"):
    params = {"query": QUERY, "start": inicio, "end": fim, "step": passo}
    url = f"{base_url}/api/v1/query_range?{urlencode(params)}"
    with urlopen(url, timeout=10) as resp:
        data = json.load(resp)
    if data["status"] != "success" or not data["data"]["result"]:
        print("Sem dados nesse intervalo — rode um teste de carga antes.", file=sys.stderr)
        sys.exit(1)
    valores = data["data"]["result"][0]["values"]
    tempos = [datetime.fromtimestamp(float(t), tz=timezone.utc) for t, _ in valores]
    cpu = [float(v) for _, v in valores]
    return tempos, cpu


def main():
    args = parse_args()
    if args.inicio and args.fim:
        inicio, fim = args.inicio, args.fim
    else:
        fim_dt = datetime.now(timezone.utc)
        inicio_dt = fim_dt - timedelta(minutes=args.minutos)
        inicio, fim = inicio_dt.isoformat(), fim_dt.isoformat()

    tempos, cpu = consultar_prometheus(args.prometheus, inicio, fim)

    # deteccao automatica do trecho sob carga: acima da linha de base (10o
    # percentil) + margem
    base = sorted(cpu)[max(0, len(cpu) // 10)]
    limiar = base + 0.15
    acima = [i for i, v in enumerate(cpu) if v > limiar]
    janela_teste = (tempos[acima[0]], tempos[acima[-1]]) if acima else None

    instaladas = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = next(
        (f for f in ("Arial", "Liberation Sans") if f in instaladas), "DejaVu Sans"
    )

    fig, ax = plt.subplots(figsize=(9.5, 5.5), dpi=200)
    ax.plot(tempos, cpu, color="#2f66d0", linewidth=2)
    ax.axhline(LIMITE_VCPU, color="#e8603c", linestyle="--", linewidth=1.5,
               label="Limite do container (1 vCPU)")
    if janela_teste:
        ax.axvspan(*janela_teste, color="#e8603c", alpha=0.08)
        meio = janela_teste[0] + (janela_teste[1] - janela_teste[0]) / 2
        ax.annotate(f"Teste Locust em execução\n({args.cenario})", (meio, 1.02),
                    ha="center", fontsize=9, color="#555555")

    ax.set_title("Utilização de CPU do Gateway GraphQL sob carga", fontsize=13, fontweight="bold", loc="left")
    ax.text(0, 1.06, f"{QUERY} — cenário {args.cenario}, horário local (UTC)",
            transform=ax.transAxes, fontsize=9, color="#777777")
    ax.set_ylabel("Uso de CPU (núcleos, process_cpu_seconds_total)", fontsize=10)
    ax.set_ylim(0, 1.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    ax.grid(axis="y", color="#dddddd")
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    fig.savefig(args.saida)
    print(f"Figura gravada em {args.saida}")


if __name__ == "__main__":
    main()
