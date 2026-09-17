# -*- coding: utf-8 -*-
"""답변 속 숫자의 출처를 역추적한다.

허용 집합 = 조회 결과 + 매뉴얼 고정값 + 한 단계 산술 유도값.
출처를 못 찾는 숫자가 있으면 위반이다. 숫자가 아닌 오류는 못 잡는다는 한계가 있다.
"""
import json
import re

from context import FIXED_POLICY

def numbers_in(obj):
    """문자열/딕셔너리/리스트에서 정수들을 모두 뽑아낸다(콤마 제거 후)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)          # 100,000 -> 100000
    return {int(m) for m in re.findall(r"\d+", text)}


def allowed_numbers(tool_results):
    """조회 결과 + 매뉴얼 고정값 + 한 단계 산술 유도값을 허용 집합으로 만든다."""
    allowed = set()
    for v in FIXED_POLICY.values():                      # 매뉴얼 고정값
        if isinstance(v, int):
            allowed.add(v)
        elif isinstance(v, list):
            allowed.update(x for x in v if isinstance(x, int))
    tool_nums = set()
    for r in (tool_results or {}).values():
        tool_nums |= numbers_in(r)
    allowed |= tool_nums
    base = sorted(allowed)
    for a in base:                                       # 한 단계 산술 유도값
        for b in base:
            if a > b:
                allowed.add(a - b)
            allowed.add(a + b)
    return allowed, tool_nums


# 검품 전에는 null 인 것이 정상인 "판정" 필드 — 매뉴얼 §6.4가 "항의가 가장 많이
# 발생하는 지점"으로 지목한 자리다. 숫자가 아니라 서술어로 단정하므로 numbers_in()으로는
# 못 잡는다.
PENDING_FIELDS = {"inspection_result", "fault_party", "shipping_fee_bearer"}
UNCERTAIN_PHRASE = re.compile(r"아직|확정되지|미확정|예정|검품\s*(후|중|에서)|추후")


def check_pending_fields(answer, tool_results):
    """null 인 판정 필드가 있는데 답변이 미확정 표현 없이 단정하는지 본다."""
    pending = {k for r in (tool_results or {}).values() if isinstance(r, dict)
               for k in PENDING_FIELDS if k in r and r[k] is None}
    if pending and not UNCERTAIN_PHRASE.search(answer):
        return {"type": "미확정 필드 단정 의심",
                "detail": f"null 인 판정 필드({sorted(pending)})가 있는데 "
                          f"'아직 확정되지 않았다' 류의 표현이 답변에 없음"}
    return None


def guardrail(answer, tool_results=None, min_check=1000):
    """답변 속 숫자의 출처를 역추적한다. 출처 불명이 있으면 위반으로 표시한다."""
    allowed, tool_nums = allowed_numbers(tool_results)
    found = numbers_in(answer)
    suspicious = sorted(n for n in found if n >= min_check and n not in allowed)

    violations = []
    if suspicious:
        violations.append({"type": "출처 불명 수치",
                           "detail": f"조회 결과·매뉴얼 고정값에 없는 숫자: {suspicious}"})
    # 조회 없이 무료배송 기준액을 단정했는지 별도 점검 (매뉴얼 4.2)
    if re.search(r"무료\s?배송", answer) and re.search(r"\d[\d,]*\s*원\s*(이상|부터)", answer):
        if "get_shipping_policy" not in (tool_results or {}):
            violations.append({"type": "툴 미호출 단정",
                               "detail": "무료배송 기준액을 get_shipping_policy 조회 없이 단정"})
    pending_violation = check_pending_fields(answer, tool_results)
    if pending_violation:
        violations.append(pending_violation)
    return {"ok": not violations, "violations": violations,
            "numbers_in_answer": sorted(found), "from_tools": sorted(tool_nums)}
