# -*- coding: utf-8 -*-
"""프롬프트가 길어진 대가를 토큰으로 잰다.  `python report_tokens.py`

오늘 ROUTE_GUIDE 와 ANSWER_RULES 를 여러 번 늘렸는데 비용을 한 번도 재지 않았다.
원본(수정 전) prompts.py 가 남아 있으면 before/after 를 함께 보여준다.

API 호출은 하지 않는다. tiktoken 으로 로컬에서만 센다.
"""
import json
from pathlib import Path

import tiktoken

from answer import LC_TOOLS
from config import BASE, MODEL, ANSWER_MODEL, ROUTES
from context import build_context, sections
import prompts

ORIGINAL = Path.home() / "Downloads" / "modumall-agent-src" / "modumall-agent" / "prompts.py"

# 강의에서 제시된 비용 최적화 등급 입력 단가. 답변 등급은 자료에 단가가 없어 같은 값으로
# 가정하고 계산하므로, 아래 금액은 '하한 추정'으로 읽어야 한다.
USD_PER_1M_INPUT = 0.20
KRW_PER_USD = 1400

enc = tiktoken.get_encoding("o200k_base")


def n(text):
    return len(enc.encode(text))


def load_original():
    """수정 전 prompts.py 의 두 상수를 읽어 온다. 없으면 None."""
    if not ORIGINAL.exists():
        return None
    ns = {}
    exec(ORIGINAL.read_text(encoding="utf-8"), ns)          # 임포트 없는 상수 파일이라 안전
    return {"ROUTE_GUIDE": ns["ROUTE_GUIDE"], "ANSWER_RULES": ns["ANSWER_RULES"]}


def tool_schema_tokens():
    """도구 정의도 매 호출 입력에 실려 간다 — 보통 잊어버리는 비용."""
    from langchain_core.utils.function_calling import convert_to_openai_tool
    schemas = [convert_to_openai_tool(t) for t in LC_TOOLS]
    return n(json.dumps(schemas, ensure_ascii=False)), len(schemas)


def main():
    orig = load_original()

    print("── 1. 프롬프트 (오늘 수정한 부분) ─────────────────────")
    rows = [("ROUTE_GUIDE", prompts.ROUTE_GUIDE), ("ANSWER_RULES", prompts.ANSWER_RULES)]
    for name, text in rows:
        now = n(text)
        if orig:
            was = n(orig[name])
            print(f"  {name:14s} {was:5d} → {now:5d} 토큰  ({now - was:+d}, {now / was:.1f}배)")
        else:
            print(f"  {name:14s} {now:5d} 토큰")

    print("\n── 2. 매뉴얼 컨텍스트 (라우트별) ──────────────────────")
    full = n("\n\n".join(v for v in sections.values()))
    print(f"  매뉴얼 전문(부록 제외)      {full:5d} 토큰")
    for r in ROUTES:
        c = n(build_context(r))
        print(f"  {r:14s} {c:5d} 토큰  (전문 대비 {c / full:.0%})")

    print("\n── 3. 도구 정의 ───────────────────────────────────────")
    tok, cnt = tool_schema_tokens()
    print(f"  도구 {cnt}개 스키마          {tok:5d} 토큰  ← 매 호출 입력에 항상 실린다")

    print("\n── 4. 문의 1건당 입력 토큰 (답변 경로) ────────────────")
    ctx = n(build_context("SHIPPING"))
    rules = n(prompts.ANSWER_RULES)
    per_call = rules + ctx + tok
    print(f"  ANSWER_RULES {rules} + 컨텍스트 {ctx} + 도구 {tok} = {per_call} 토큰 / 1회 호출")
    print(f"  도구 호출 루프로 평균 3회 왕복한다고 보면  약 {per_call * 3:,} 토큰 / 문의 1건")

    print("\n── 5. 비용 추정 (입력 기준, 1M당 ${:.2f} 가정) ─────────".format(USD_PER_1M_INPUT))
    for label, count in [("문의 100건", 100), ("문의 1,000건", 1000), ("문의 10,000건", 10000)]:
        toks = per_call * 3 * count
        usd = toks / 1_000_000 * USD_PER_1M_INPUT
        print(f"  {label:12s} {toks:12,} 토큰  ≈ ${usd:7.2f}  (약 {usd * KRW_PER_USD:,.0f}원)")

    if orig:
        print("\n── 6. 오늘 늘어난 만큼의 추가 비용 ────────────────────")
        delta = n(prompts.ANSWER_RULES) - n(orig["ANSWER_RULES"])
        toks = delta * 3 * 10000
        usd = toks / 1_000_000 * USD_PER_1M_INPUT
        print(f"  ANSWER_RULES 증가분 {delta:+d} 토큰 × 3회 × 10,000건 = {toks:,} 토큰")
        print(f"  ≈ ${usd:.2f} (약 {usd * KRW_PER_USD:,.0f}원) — 통과율 62.5%→81.2% 의 대가")

    print("\n  * 출력 토큰과 답변 등급의 실제 단가는 자료에 없어 제외했으므로 하한 추정이다.")


if __name__ == "__main__":
    main()
