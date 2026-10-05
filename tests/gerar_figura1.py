"""Gera a Figura 1 do TCC (latência média x usuários) a partir da Tabela 1.

Uso: python tests/gerar_figura1.py [saida.png]
Requer matplotlib e o arquivo tests/results/tabela1_consolidada.csv
(gerado por tests/consolidar_tabela1.py). As barras de erro são o
desvio-padrão da latência média entre as execuções.
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

RESULTS = Path(__file__).parent / "results"
SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS / "figura1_curva_degradacao.png"
# (cenário no CSV, rótulo da legenda, cor, marcador, deslocamento vertical do valor final)
SERIES = [
    ("REST: Agregação Completa do Cliente", "REST (completo)", "#2f66d0", "o", -9),
    ("GraphQL: Nativo (N+1)", "GraphQL: Nativo (N+1)", "#e8603c", "s", 0),
    ("GraphQL: DataLoader", "GraphQL: DataLoader", "#12a58a", "^", 9),
]

instaladas = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = next(
    (f for f in ("Arial", "Liberation Sans") if f in instaladas), "DejaVu Sans"
)

with open(RESULTS / "tabela1_consolidada.csv", encoding="utf-8") as f:
    linhas = list(csv.DictReader(f))

cargas = sorted({int(l["usuarios"]) for l in linhas})
fig, ax = plt.subplots(figsize=(9.5, 6), dpi=200)
for nome, rotulo, cor, marcador, desloc in SERIES:
    pts = {int(l["usuarios"]): l for l in linhas if l["cenario"] == nome}
    y = [float(pts[c]["lat_media_ms"]) for c in cargas]
    dp = [float(pts[c]["lat_media_dp_ms"]) for c in cargas]
    ax.errorbar(range(len(cargas)), y, yerr=dp, label=rotulo, color=cor, marker=marcador,
                markersize=7, linewidth=2, capsize=4, linestyle="--")
    ax.annotate(f"{y[-1]:.1f} ms".replace(".", ","), (len(cargas) - 1, y[-1]),
                textcoords="offset points", xytext=(12, desloc), va="center",
                fontsize=11, fontweight="bold", color="#222222")

ax.set_xticks(range(len(cargas)))
ax.set_xticklabels([f"{c} usuários" for c in cargas], fontsize=11)
ax.set_xlim(-0.2, len(cargas) - 0.4)
ax.set_ylabel("Latência média (ms)", fontsize=12)
ax.set_ylim(0, 260)
ax.grid(axis="y", color="#dddddd")
ax.set_axisbelow(True)
for lado in ("top", "right"):
    ax.spines[lado].set_visible(False)
ax.legend(frameon=False, fontsize=11, loc="upper left")
fig.text(0.01, 0.01,
         "Barras: desvio-padrão entre execuções (3 execuções de 10 a 100 usuários; 4 execuções a 200)",
         fontsize=9, color="#555555")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(SAIDA)
print(f"Figura gravada em {SAIDA}")
