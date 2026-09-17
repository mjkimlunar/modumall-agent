# -*- coding: utf-8 -*-
"""발표용 차트 3종을 PNG 로 만든다.  `python make_charts.py`

API 호출 없음 — 이미 측정해 둔 숫자만 그린다.
색은 검증된 팔레트의 앞 세 슬롯(blue/orange/aqua)만 쓴다. aqua 는 밝은 배경에서
대비가 3:1 미만이라 모든 값에 직접 라벨을 달아 보완한다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).parent / "charts"
OUT.mkdir(exist_ok=True)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update({
    "font.family": ["Malgun Gothic", "sans-serif"],
    "axes.unicode_minus": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "font.size": 11,
})


def style(ax, ylabel=None, ymax=None):
    """공통 크롬 — 격자는 실선 헤어라인, 축은 아래쪽만."""
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, linestyle="-")
    ax.xaxis.grid(False)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(length=0)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    if ymax:
        ax.set_ylim(0, ymax)


# ── 차트 A. 개선 요약 ────────────────────────────────────────────────
def chart_improvement():
    labels = ["라우팅\n정확도", "라우팅\nmacro F1", "1턴 답변\n통과율", "실전\n자동화율"]
    before = [94.2, 94.5, 57.3, 7.5]
    after = [98.0, 98.4, 77.1, 12.5]

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    xs = range(len(labels))
    w = 0.34
    b1 = ax.bar([x - w / 2 for x in xs], before, w, label="기준선", color=BLUE)
    b2 = ax.bar([x + w / 2 for x in xs], after, w, label="개선 후", color=ORANGE)

    for bars in (b1, b2):
        for p in bars:
            ax.text(p.get_x() + p.get_width() / 2, p.get_height() + 2.5,
                    f"{p.get_height():.1f}", ha="center", va="bottom",
                    fontsize=10, color=INK)

    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, color=INK2)
    style(ax, ylabel="%", ymax=118)
    ax.set_title("모두몰 고객응대 에이전트 — 개선 전후 (각 3회 측정 평균)", fontsize=14, color=INK,
                 pad=16, loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper right", ncols=2, fontsize=10, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(OUT / "01_개선요약.png", dpi=200)
    plt.close(fig)


# ── 차트 B. 멀티턴 턴 차수별 ─────────────────────────────────────────
def chart_multiturn():
    labels = ["1차 턴\n(기존 측정 범위)", "2차 턴\n(미측정이던 구간)", "3차 턴"]
    vals = [81.2, 52.6, 100.0]
    ns = ["n=32", "n=19", "n=2"]

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    bars = ax.bar(range(len(labels)), vals, 0.5, color=BLUE)
    for p, v, nn in zip(bars, vals, ns):
        ax.text(p.get_x() + p.get_width() / 2, v + 2.5, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=11, color=INK)
        ax.text(p.get_x() + p.get_width() / 2, 2.5, nn, ha="center", va="bottom",
                fontsize=9, color="#ffffff")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, color=INK2)
    style(ax, ylabel="통과율 (%)", ymax=118)
    ax.set_title("멀티턴 — 턴 차수별 통과율", fontsize=14, color=INK,
                 pad=16, loc="left", fontweight="bold")
    ax.text(0, 1.015, "2차 턴은 기존 채점기가 한 번도 재지 않던 구간이다 (3차는 표본 2턴)",
            transform=ax.transAxes, fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0.02, 0, 1, 1))
    fig.savefig(OUT / "02_멀티턴_턴차수별.png", dpi=200)
    plt.close(fig)


# ── 차트 C. 입력 토큰 구성 ───────────────────────────────────────────
def chart_tokens():
    rows = ["원본", "현재"]
    rules = [497, 2354]
    ctx = [3465, 3465]
    tools = [1062, 1062]

    fig, ax = plt.subplots(figsize=(8.4, 3.9))
    h = 0.42
    gap = 30                                   # 2px 상당의 표면 간격
    left = [0, 0]
    segs = [("지시문(ANSWER_RULES)", rules, BLUE),
            ("매뉴얼 컨텍스트", ctx, ORANGE),
            ("도구 스키마", tools, AQUA)]
    for name, vals, color in segs:
        ax.barh(rows, vals, h, left=left, color=color, label=name)
        for i, v in enumerate(vals):
            ax.text(left[i] + v / 2, i, f"{v:,}", ha="center", va="center",
                    fontsize=10, color="#ffffff")
        left = [l + v + gap for l, v in zip(left, vals)]

    for i, total in enumerate(left):
        ax.text(total + 60, i, f"합계 {total - gap * 3:,}", va="center",
                fontsize=11, color=INK)

    ax.invert_yaxis()            # 원본이 위, 현재가 아래로 읽히게
    ax.set_xlim(0, 8600)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.yaxis.grid(False)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(length=0)
    ax.set_yticklabels(rows, color=INK2, fontsize=11)
    ax.set_xlabel("1회 호출당 입력 토큰", color=INK2, fontsize=10)
    ax.set_title("프롬프트가 길어진 대가 — 입력 토큰 구성", fontsize=14, color=INK,
                 pad=16, loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.30),
              ncols=3, fontsize=10, labelcolor=INK2)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.80, bottom=0.34)
    fig.savefig(OUT / "03_토큰구성.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    chart_improvement()
    chart_multiturn()
    chart_tokens()
    for f in sorted(OUT.glob("*.png")):
        print("생성:", f)
