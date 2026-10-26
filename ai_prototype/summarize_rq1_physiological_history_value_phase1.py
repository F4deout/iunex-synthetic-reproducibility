import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "rq1_physiological_history_value_phase1"
RESULTS = OUT / "results.json"


def fmt(value):
    return f"{value:.4f}"


def interval(block):
    return f"{fmt(block['mean'])} [{fmt(block['ci95'][0])}, {fmt(block['ci95'][1])}]"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    summary = payload["summary"]
    lines = [
        "# RQ1 생리·수행 이력 Phase 1 본실험 보고서",
        "",
        "## 1. 실행 범위",
        "",
        "- 자료구조: NATURALISTIC, CONTROLLED_CHANGE",
        "- 최종 시드: 110, 220, 330, 440, 550",
        "- 이력 길이: 0, 5, 10, 20, 30, 50, 75, 100",
        "- 정보조건: C1~C7",
        "- 주 비교: k=20에서 C1(현재정보)과 C5(과거 자기보고를 제외한 전체 객관적 이력)",
        "- 이 보고서는 Phase 1 결과이며, 사전등록 최종 판정에 필요한 identity/time-order destruction 및 민감도 분석은 아직 수행하지 않음.",
        "",
        "## 2. 실행 무결성",
        "",
        "- 560개 예측 설정 완료",
        "- AFT 적합 210개 모두 수렴",
        "- subject-disjoint 72/24/24 분할 및 train-only 전처리 유지",
        "- 생성기·프로토콜·parameter 변경 없음",
        "",
    ]
    targets = [
        ("pre_fatigue_latent", "활동 전 잠재 피로"),
        ("pre_condition_construct", "활동 전 잠재 현재상태"),
        ("post_burden_latent", "활동 후 잠재 부담"),
        ("pre_fatigue", "활동 전 자기보고 피로"),
        ("pre_condition", "활동 전 자기보고 현재상태"),
        ("post_burden", "활동 후 자기보고 부담"),
        ("recovery_delay_h", "회복 지연시간"),
    ]
    for dataset_index, dataset in enumerate(payload["datasets"], start=1):
        lines += [f"## 3.{dataset_index} {dataset} 주 비교", "", "| 예측대상 | C1 MAE | C5 MAE | C1−C5 paired MAE [95% CI] | 개선 시드 |", "|---|---:|---:|---:|---:|"]
        block = summary[dataset]["20"]
        for key, label in targets:
            base = block["C1"]["continuous"][key]["mae"]
            item = block["C5"]["continuous"][key]
            lines.append(f"| {label} | {fmt(base['mean'])} | {fmt(item['mae']['mean'])} | {interval(item['C1_minus_condition'])} | {item['improved_seeds']}/5 |")
        for key, label, metric in (("completion", "완료 여부(Brier)", "brier"), ("stopped_time", "관측 중단시간 MAE(분)", "mae")):
            base = block["C1"][key][metric]
            item = block["C5"][key]
            lines.append(f"| {label} | {fmt(base['mean'])} | {fmt(item[metric]['mean'])} | {interval(item['C1_minus_condition'])} | {item['improved_seeds']}/5 |")
        lines += ["", "### k별 C5 MAE", "", "| k | 잠재 피로 | 자기보고 피로 | 잠재 부담 | 회복 지연(시간) | 완료 Brier | 중단시간(분) | AFT C-index |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for k in payload["history_lengths"]:
            item = summary[dataset][str(k)]["C5"]
            lines.append("| " + " | ".join([
                str(k),
                fmt(item["continuous"]["pre_fatigue_latent"]["mae"]["mean"]),
                fmt(item["continuous"]["pre_fatigue"]["mae"]["mean"]),
                fmt(item["continuous"]["post_burden_latent"]["mae"]["mean"]),
                fmt(item["continuous"]["recovery_delay_h"]["mae"]["mean"]),
                fmt(item["completion"]["brier"]["mean"]),
                fmt(item["stopped_time"]["mae"]["mean"]),
                fmt(item["aft"]["c_index"]["mean"]),
            ]) + " |")
        lines += ["", "### k=20 정보군 비교", "", "| 조건 | 잠재 피로 MAE | 자기보고 피로 MAE | 잠재 부담 MAE | 회복 지연 MAE | 완료 Brier | 중단시간 MAE(분) |", "|---|---:|---:|---:|---:|---:|---:|"]
        for condition in payload["conditions"]:
            item = block[condition]
            lines.append(f"| {condition} | {fmt(item['continuous']['pre_fatigue_latent']['mae']['mean'])} | {fmt(item['continuous']['pre_fatigue']['mae']['mean'])} | {fmt(item['continuous']['post_burden_latent']['mae']['mean'])} | {fmt(item['continuous']['recovery_delay_h']['mae']['mean'])} | {fmt(item['completion']['brier']['mean'])} | {fmt(item['stopped_time']['mae']['mean'])} |")
        lines.append("")
    lines += [
        "## 4. Phase 1 해석",
        "",
        "- 객관적 이력(C5)은 두 자료구조에서 잠재 피로·현재상태·부담 MAE를 5/5 시드에서 감소시켰으나, 주 생리상태 target의 평균 개선은 사전등록 최소폭 0.02에 미달함.",
        "- 자기보고 피로·현재상태·부담은 C5에서 일관되게 개선되지 않았고 일부는 악화됨.",
        "- 과거 자기보고를 허용한 C6·C7에서는 자기보고 target 오차가 크게 감소하여, 보고성향 정보의 별도 경로가 확인됨. 이는 생리적 개인화 성공판정에 사용하지 않음.",
        "- 회복 지연, 완료 여부 및 관측 중단시간에서는 C5의 개선 방향이 두 자료구조 모두 5/5 시드에서 일치함.",
        "- 따라서 Phase 1만으로 PHYSIOLOGICAL_HISTORY_VALUE를 확정할 수 없으며, 객관적 이력의 생리상태 개선폭은 현재 사전등록 기준상 불충분함.",
        "- TASK_HISTORY_VALUE의 최종 판정은 수행·회복 이력 제거 및 identity/time-order destruction 후 가능함.",
        "",
        "## 5. 동결 해시",
        "",
    ]
    artifact_names = ["results.json", "summary.csv", "split_manifest.json", "raw_predictions.jsonl.gz"]
    hashes = {name: sha(OUT / name) for name in artifact_names}
    hashes["runner"] = sha(ROOT / "run_rq1_physiological_history_value_phase1.py")
    for name, value in hashes.items():
        lines.append(f"- `{name}`: `{value}`")
    (OUT / "PHASE1_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "PHASE1_FREEZE_SHA256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
