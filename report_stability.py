# -*- coding: utf-8 -*-
"""노이즈가 어디서 나오는지 케이스별로 본다.  `python report_stability.py [-n 4]`

같은 입력을 N 번 돌려 케이스마다 몇 번 통과하는지 센다.
  N/N 또는 0/N  → 안정. 이 케이스는 점수 변동에 기여하지 않는다.
  그 사이        → 불안정. 여기가 ±9%p 의 실제 출처다.

`evaluate.py` 는 수정하지 않고 채점 함수만 가져다 쓴다.
"""
import argparse
import re
from collections import defaultdict

import pandas as pd

from common import pmap
from config import ensure_data
from evaluate import AUTO_ACTIONS, load_cases, score_turn


def classify_action(results, text):
    """evaluate.py run_case 와 동일한 판정."""
    if results.get("get_order_status", {}).get("is_external_channel"):
        return "OUT_OF_SCOPE"
    if not results and re.search(r"\?|주시겠|알려주|말씀해", text):
        return "ASK"
    return "ANSWER"


def one_round(cases):
    from answer import answer_with_tools

    def run(c):
        text, results = answer_with_tools(c["question"], c["route"])
        action = classify_action(results, text)
        ok, fails = score_turn(c["expect"], text, list(results), action)
        return c["conv_id"], ok, fails, sorted(results), text

    return pmap(run, cases)


def main(n):
    from answer import llm_t
    try:                                   # 스레드 경합 방지 — 캐시를 미리 채운다
        _ = llm_t.bound._serialized
    except AttributeError:
        pass

    cases = [c for c in load_cases() if c["expect"]["action"] in AUTO_ACTIONS]
    passes = defaultdict(int)
    detail = defaultdict(list)
    rates = []

    for i in range(n):
        rows = one_round(cases)
        rates.append(sum(ok for _, ok, _, _, _ in rows) / len(rows))
        for cid, ok, fails, tools, text in rows:
            passes[cid] += ok
            detail[cid].append((ok, "; ".join(fails), tuple(tools)))
        print(f"  {i + 1}회차 통과율 {100 * rates[-1]:.1f}%")

    print(f"\n{n}회 평균 {100 * sum(rates) / n:.1f}%  (최저 {100 * min(rates):.1f}% · "
          f"최고 {100 * max(rates):.1f}% · 폭 {100 * (max(rates) - min(rates)):.1f}%p)")

    stable_pass = [c for c, v in passes.items() if v == n]
    stable_fail = [c for c, v in passes.items() if v == 0]
    unstable = sorted((c for c, v in passes.items() if 0 < v < n), key=lambda c: passes[c])

    print(f"\n── 케이스 {len(cases)}건의 안정성 ──────────────────────")
    print(f"  항상 통과   {len(stable_pass):2d}건")
    print(f"  항상 실패   {len(stable_fail):2d}건  {sorted(stable_fail)}")
    print(f"  **흔들림**  {len(unstable):2d}건  ← 점수 변동의 출처")
    print(f"\n  흔들리는 {len(unstable)}건만으로 이론상 최대 "
          f"{100 * len(unstable) / len(cases):.1f}%p 까지 움직인다 "
          f"(한 건 = {100 / len(cases):.1f}%p)")

    if unstable:
        print("\n── 흔들리는 케이스가 무엇 때문에 갈리는가 ─────────")
        for cid in unstable:
            print(f"\n  [{cid}] {passes[cid]}/{n} 통과")
            for ok, fails, tools in detail[cid]:
                mark = "통과" if ok else "실패"
                print(f"    {mark} | 도구={list(tools)}")
                if fails:
                    print(f"         {fails[:88]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="케이스별 안정성을 재서 노이즈의 출처를 찾는다")
    ap.add_argument("-n", type=int, default=4, help="반복 횟수 (기본 4)")
    args = ap.parse_args()
    ensure_data()
    main(args.n)
