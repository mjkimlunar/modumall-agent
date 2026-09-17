# -*- coding: utf-8 -*-
"""멀티턴 채점기.  `python evaluate_multiturn.py [--mode concat|messages]`

`evaluate.py` 는 각 대화의 **첫 에이전트 턴만** 채점한다(34건). 정답셋에는 에이전트 턴이
56개 있으므로 **22턴이 한 번도 측정된 적이 없다.** 이 스크립트는 대화를 턴 순서대로
재생하며 56턴 전부를 채점한다. (`evaluate.py` 는 대회 규칙상 수정하지 않는다.)

문맥을 넘기는 방식 두 가지를 비교할 수 있다.
  concat   : 고객 발화만 공백으로 이어 붙인다 — 지금 agent.py 의 with_history() 방식
  marked   : 앞 발화는 [이전 대화]로, 마지막 발화는 [지금 답해야 할 문의]로 구분해 넘긴다
  customer : 고객 발화만 턴을 살려 human 메시지로 나눠 넘긴다(AI 답변 제외)
  messages : 역할(human/ai)을 살린 메시지 목록으로 넘긴다 — 강의가 "정석"이라 한 방식

라우트는 턴에 route 가 있으면 그것을, 없으면 대화의 route 를 쓴다(라우팅 오류가 섞이지
않도록 정답 라우트를 쓰는 것은 evaluate.py 와 같은 원칙).
"""
import argparse
import json
import re

import pandas as pd

from answer import tool_app
from common import pmap
from config import BASE, MAX_TOOL_TURNS, ensure_data
from context import build_answer_prompt
from evaluate import AUTO_ACTIONS, score_turn
from tools import TOOLS


def load_conversations():
    gold = json.loads((BASE / "answer_goldenset_multiturn.json").read_text(encoding="utf-8"))
    return gold["conversations"]


def turn_route(conv, expect):
    """턴에 route 가 있으면 우선, 없으면 대화 route 의 마지막 구간."""
    return expect.get("route") or conv["route"].split("→")[-1].strip()


def ask_model(messages, route):
    """메시지 목록을 그대로 그래프에 넣고 (답변, 호출된 도구 결과) 를 받는다."""
    init = {"messages": [("system", build_answer_prompt("", route))] + messages}
    out = tool_app.invoke(init, {"recursion_limit": 2 * MAX_TOOL_TURNS + 1})
    used = {}
    for m in out["messages"]:
        if getattr(m, "name", None) in TOOLS:
            try:
                used[m.name] = json.loads(m.content)
            except json.JSONDecodeError:
                used[m.name] = m.content
    return out["messages"][-1].content, used


def classify_action(results, text):
    """evaluate.py run_case 와 동일한 판정 로직 — 숫자를 비교 가능하게 유지한다."""
    if results.get("get_order_status", {}).get("is_external_channel"):
        return "OUT_OF_SCOPE"
    if not results and re.search(r"\?|주시겠|알려주|말씀해", text):
        return "ASK"
    return "ANSWER"


def replay(conv, mode):
    """대화 하나를 턴 순서대로 재생하며 에이전트 턴마다 채점한다."""
    said, msgs, rows = [], [], []
    for t in conv["turns"]:
        if t["role"] == "customer":
            said.append(t["text"])
            msgs.append(("human", t["text"]))
            continue
        expect = t.get("expect")
        if not expect:
            continue
        if mode == "concat":                     # 고객 발화만 이어 붙인 한 덩어리
            payload = [("human", " ".join(said))]
        elif mode == "marked":                    # 앞 발화는 맥락으로, 마지막이 현재 질문
            head = "\n".join(f"- {s}" for s in said[:-1])
            payload = [("human", (f"[이전 대화에서 고객이 한 말]\n{head}\n\n"
                                  f"[지금 답해야 할 문의]\n{said[-1]}") if head else said[-1])]
        elif mode == "customer":                  # 고객 발화만 턴을 살려 나눠서
            payload = [("human", s) for s in said]
        else:                                     # 역할을 살린 메시지 목록(AI 답변 포함)
            payload = msgs
        text, results = ask_model(payload, turn_route(conv, expect))
        action = classify_action(results, text)
        ok, fails = score_turn(expect, text, list(results), action)
        rows.append({"conv": conv["conv_id"], "turn": t["turn"], "차수": len(rows) + 1,
                     "기대": expect["action"], "실제": action, "ok": ok,
                     "fails": "; ".join(fails), "answer": text})
        msgs.append(("ai", text))
    return rows


def warmup():
    """LangChain 모델의 cached_property 를 메인 스레드에서 미리 계산해 둔다.

    안 해두면 pmap(스레드 풀)이 동시에 직렬화하다가
    RuntimeError: dictionary changed size during iteration 로 터진다.
    """
    from answer import llm_t
    try:
        _ = llm_t.bound._serialized
    except AttributeError:
        pass


def main(mode, report=True):
    warmup()
    convs = [c for c in load_conversations()
             if any(t.get("expect", {}).get("action") in AUTO_ACTIONS for t in c["turns"])]
    res = pd.DataFrame([r for rows in pmap(lambda c: replay(c, mode), convs) for r in rows])
    scored = res[res["기대"].isin(AUTO_ACTIONS)]

    rate = scored["ok"].mean()
    print(f"── 멀티턴 채점 (mode={mode}) ──────────────────────")
    print(f'채점 {len(scored)}턴 / 통과 {scored["ok"].sum()}턴 ({100 * rate:.1f}%)'
          f"   (자동 판정 불가 {len(res) - len(scored)}턴 제외)")

    if report:
        print("\n[턴 차수별] — 1차는 evaluate.py 가 재는 범위, 2차 이상은 미측정이던 구간")
        print(scored.groupby("차수")["ok"].agg(["count", "sum", "mean"])
              .rename(columns={"count": "턴수", "sum": "통과", "mean": "통과율"}).to_string())
        print("\n[실패 유형]")
        kinds = [f.split(":")[0] for s in scored.loc[~scored["ok"], "fails"] for f in s.split("; ") if f]
        print(pd.Series(kinds).value_counts().to_string() if kinds else "  없음")
        print("\n[2차 이상 턴의 실패] — 문맥 유지가 안 되면 여기서 드러난다")
        for _, r in scored[(~scored["ok"]) & (scored["차수"] >= 2)].iterrows():
            print(f'  {r["conv"]} T{r["turn"]} 기대={r["기대"]} 실제={r["실제"]}  {r["fails"][:70]}')
            print(f'      답변: {r["answer"][:80]}')
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="멀티턴 56턴을 전부 채점한다")
    ap.add_argument("--mode", choices=["concat", "marked", "customer", "messages"], default="concat",
                    help="문맥 전달 방식 (기본 concat = 현재 agent.py 방식)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    ensure_data()
    main(args.mode, report=not args.quiet)
