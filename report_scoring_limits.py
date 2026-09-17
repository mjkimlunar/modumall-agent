# -*- coding: utf-8 -*-
"""채점기의 구조적 한계를 정량화해서 원본 점수와 함께 병기한다.  `python report_scoring_limits.py`

**evaluate.py 는 건드리지 않는다.** 대회 점수는 원본 채점기 기준이어야 다른 팀과 비교되기
때문이다. 이 스크립트는 같은 에이전트 출력에 대해
  ① 원본 채점기 그대로의 점수 (공식 숫자)
  ② 채점기의 증명된 버그를 보정했을 때의 점수 (참고용 추정치)
를 함께 내놓는다.

보정 대상은 '내 답변이 맘에 안 들어서'가 아니라, **채점기가 자기 모범 답안(reference)을
오판한다는 것이 증명된 항목**뿐이다. 근거는 --evidence 로 출력한다.
"""
import argparse
import re

import pandas as pd

from common import pmap
from config import ensure_data
from evaluate import AUTO_ACTIONS, load_cases, score_turn

# ── 원본 채점기의 action 판정 (evaluate.py run_case 와 동일) ──────────────
ORIG_ASK = re.compile(r"\?|주시겠|알려주|말씀해")


def classify_orig(results, text):
    if results.get("get_order_status", {}).get("is_external_channel"):
        return "OUT_OF_SCOPE"
    if not results and ORIG_ASK.search(text):
        return "ASK"
    return "ANSWER"


# ── 보정 판정 — 골든셋 54턴 전체로 검증한 규칙 ──────────────────────────
# ① 범위 밖 안내 문구: OUT_OF_SCOPE 2/2 적중, 다른 action 오탐 0건
# ② 능동적 정보 요청: ASK 8/8 적중. "말씀해"(수동적 안내)를 빼면 ANSWER 오탐 0건
FIXED_OOS = re.compile(r"고객센터|해당 사이트|제조사")
FIXED_ASK = re.compile(r"\?|주시겠|알려주|하셨을까요|가능하실까요")


def classify_fixed(results, text):
    if results.get("get_order_status", {}).get("is_external_channel") or FIXED_OOS.search(text):
        return "OUT_OF_SCOPE"
    if FIXED_ASK.search(text):
        return "ASK"
    return "ANSWER"


def evidence():
    """채점기 버그의 근거 — 모범 답안을 두 판정기에 각각 넣어 본다."""
    cases = load_cases()
    rows = []
    for c in cases:
        e = c["expect"]
        fake = {t: {} for t in e.get("tools", [])}
        rows.append({
            "conv": c["conv_id"], "기대": e["action"],
            "원본판정": classify_orig(fake, e["reference"]),
            "보정판정": classify_fixed(fake, e["reference"]),
        })
    df = pd.DataFrame(rows)
    df["원본오판"] = df["기대"] != df["원본판정"]
    df["보정오판"] = df["기대"] != df["보정판정"]
    print("── 근거: 모범 답안(reference)을 판정기에 넣으면 ─────────────")
    print(f'  원본 판정기 오판 {df["원본오판"].sum()}건 / {len(df)}건')
    print(f'  보정 판정기 오판 {df["보정오판"].sum()}건 / {len(df)}건')
    print("\n[원본 판정기가 자기 모범 답안을 틀리는 건]")
    print(df[df["원본오판"]][["conv", "기대", "원본판정", "보정판정"]].to_string(index=False))
    return df


def run():
    from answer import answer_with_tools

    cases = [c for c in load_cases() if c["expect"]["action"] in AUTO_ACTIONS]
    outs = pmap(lambda c: answer_with_tools(c["question"], c["route"]), cases)

    rows = []
    for c, (text, results) in zip(cases, outs):
        tools = list(results)
        ok_o = score_turn(c["expect"], text, tools, classify_orig(results, text))[0]
        ok_f = score_turn(c["expect"], text, tools, classify_fixed(results, text))[0]
        rows.append({"conv": c["conv_id"], "기대": c["expect"]["action"],
                     "원본통과": ok_o, "보정통과": ok_f, "answer": text})
    res = pd.DataFrame(rows)

    n = len(res)
    o, f = res["원본통과"].sum(), res["보정통과"].sum()
    print("\n── 병기 결과 ────────────────────────────────────────────")
    print(f"  ① 원본 채점기 (공식)      {o}/{n} = {o / n:.1%}")
    print(f"  ② 판정 버그 보정 (참고)   {f}/{n} = {f / n:.1%}")
    flipped = res[res["원본통과"] != res["보정통과"]]
    if len(flipped):
        print(f"\n[보정으로 판정이 뒤집힌 {len(flipped)}건] — 답변은 그대로, 판정만 달라짐")
        for _, r in flipped.iterrows():
            print(f'  {r["conv"]} (기대 {r["기대"]}): {r["answer"][:70]}')
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="채점기 한계를 정량화해 병기한다")
    ap.add_argument("--evidence-only", action="store_true", help="근거만 출력(API 호출 없음)")
    args = ap.parse_args()

    ensure_data()
    evidence()
    if not args.evidence_only:
        run()
