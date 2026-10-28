# NFR-PRED-001 AI 모델 평가 기준 (6일차 명세서 6장)
#
# API가 아니라, 모델을 서비스에 반영하기 전에 실행하는 평가 스크립트다.
# 학습에 사용하지 않은 테스트 데이터로 TP/FP/FN/TN, Recall, Accuracy를 계산하고
# 기준(Recall >= 0.90, Accuracy >= 0.80)을 통과했는지 판정한 뒤 6.4 양식으로 기록한다.
#
# 서비스와 같은 전처리·판정을 쓰도록 worker.predict.predict_pneumonia를 그대로 호출한다. (6.3 0번)
#
# 테스트 데이터 폴더 구조 (폴더 이름은 대소문자 무관)
#   <data_dir>/NORMAL/*.jpeg       정상
#   <data_dir>/PNEUMONIA/*.jpeg    폐렴
#
# 실행 예
#   uv run python -m worker.evaluate --data-dir data/chest_xray/test --model-name resnet18-v1 --data-source "Kaggle chest_xray test"

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from worker.predict import predict_pneumonia

# 6.2 평가 기준
RECALL_MIN = 0.90    # 주 지표 (최소선)
ACCURACY_MIN = 0.80  # 보조 지표 (최소선)

# 현재 판정 방식 (4.5: argmax, 폐렴 확률 0.5 기준)
THRESHOLD_DESCRIPTION = "argmax (폐렴 확률 0.5)"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
LABEL_DIRS = {"normal": 0, "pneumonia": 1}  # class_id와 같은 순서 (1 = 폐렴)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


@dataclass
class Sample:
    path: Path
    label: int  # 실제값 (0 정상, 1 폐렴)


@dataclass
class EvaluationResult:
    tp: int
    fp: int
    fn: int
    tn: int
    auc: float | None
    skipped: list[Path]

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def recall(self) -> float:
        # 실제 폐렴 환자를 얼마나 놓치지 않는가 (주 지표)
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def accuracy(self) -> float:
        return _ratio(self.tp + self.tn, self.total)

    @property
    def precision(self) -> float:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def specificity(self) -> float:
        return _ratio(self.tn, self.tn + self.fp)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return _ratio(2 * p * r, p + r)

    @property
    def passed(self) -> bool:
        # 6.3 2번: Recall이 0.90 미만이면 Accuracy와 관계없이 반영하지 않는다.
        return self.recall >= RECALL_MIN and self.accuracy >= ACCURACY_MIN


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def collect_samples(data_dir: Path) -> list[Sample]:
    """NORMAL / PNEUMONIA 하위 폴더에서 이미지와 실제값을 모은다."""
    samples: list[Sample] = []
    found_dirs = set()
    for sub_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        label = LABEL_DIRS.get(sub_dir.name.lower())
        if label is None:
            continue
        found_dirs.add(sub_dir.name.lower())
        for path in sorted(sub_dir.rglob("*")):
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                samples.append(Sample(path=path, label=label))

    missing = set(LABEL_DIRS) - found_dirs
    if missing:
        raise SystemExit(f"테스트 데이터 폴더에 {', '.join(sorted(missing)).upper()} 폴더가 없습니다: {data_dir}")
    if not samples:
        raise SystemExit(f"평가할 이미지가 없습니다: {data_dir}")
    return samples


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """폐렴 확률로 AUC를 계산한다 (참고용, 순위 기반). 한쪽 클래스만 있으면 None."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None

    # 같은 점수는 평균 순위를 준다.
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        average_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1

    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def evaluate(samples: list[Sample]) -> EvaluationResult:
    tp = fp = fn = tn = 0
    labels: list[int] = []
    pneumonia_scores: list[float] = []
    skipped: list[Path] = []

    for index, sample in enumerate(samples, start=1):
        try:
            with Image.open(sample.path) as image:
                result = predict_pneumonia(image)
        except (UnidentifiedImageError, OSError):
            skipped.append(sample.path)
            continue

        predicted = result["class_id"]
        # confidence는 예측된 클래스의 확률이므로 폐렴 확률로 바꿔 AUC에 사용
        pneumonia_prob = result["confidence"] if predicted == 1 else 1 - result["confidence"]
        labels.append(sample.label)
        pneumonia_scores.append(pneumonia_prob)

        if sample.label == 1 and predicted == 1:
            tp += 1
        elif sample.label == 0 and predicted == 1:
            fp += 1
        elif sample.label == 1 and predicted == 0:
            fn += 1  # 폐렴 환자를 정상으로 오진 (가장 위험)
        else:
            tn += 1

        if index % 50 == 0 or index == len(samples):
            print(f"  {index}/{len(samples)} 평가 중...", file=sys.stderr)

    return EvaluationResult(tp=tp, fp=fp, fn=fn, tn=tn, auc=roc_auc(labels, pneumonia_scores), skipped=skipped)


def format_report(result: EvaluationResult, model_name: str, data_source: str) -> str:
    """6.4 평가 결과 기록 양식."""
    # 읽지 못해 제외한 이미지는 빼고, 실제로 평가한 표본 수로 기록
    pneumonia = result.tp + result.fn
    normal = result.fp + result.tn
    auc = f"{result.auc:.4f}" if result.auc is not None else "-"
    decision = "✅ 반영 가능" if result.passed else "❌ 반영 불가"
    reasons = []
    if result.recall < RECALL_MIN:
        reasons.append(f"Recall {result.recall:.4f} < {RECALL_MIN}")
    if result.accuracy < ACCURACY_MIN:
        reasons.append(f"Accuracy {result.accuracy:.4f} < {ACCURACY_MIN}")
    if reasons:
        decision += f" ({', '.join(reasons)})"

    lines = [
        f"# AI 모델 평가 결과 — {model_name}",
        "",
        f"- 평가일: {date.today().isoformat()}",
        "- 기준: 6일차 AI 폐렴예측 API 설계 명세서 6장 (`NFR-PRED-001`)",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 모델 이름·버전 (`AI_MODEL_NAME`) | {model_name} |",
        f"| 평가 데이터 (출처, 표본 수, 폐렴/정상 비율) | {data_source}, {result.total}장, 폐렴 {pneumonia} / 정상 {normal} |",
        f"| 폐렴 판정 임계값 | {THRESHOLD_DESCRIPTION} |",
        f"| TP / FP / FN / TN | {result.tp} / {result.fp} / {result.fn} / {result.tn} |",
        f"| Recall (기준 ≥ {RECALL_MIN}) | {result.recall:.4f} |",
        f"| Accuracy (기준 ≥ {ACCURACY_MIN}) | {result.accuracy:.4f} |",
        f"| 반영 여부 | {decision} |",
        "",
        "## 참고 지표",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| Precision | {result.precision:.4f} |",
        f"| Specificity | {result.specificity:.4f} |",
        f"| F1 | {result.f1:.4f} |",
        f"| AUC | {auc} |",
        "",
        "## 혼동 행렬",
        "",
        "| | 모델: 폐렴 | 모델: 정상 |",
        "|---|---|---|",
        f"| **실제: 폐렴** | TP {result.tp} | FN {result.fn} |",
        f"| **실제: 정상** | FP {result.fp} | TN {result.tn} |",
    ]
    if result.skipped:
        lines += ["", f"읽지 못해 제외한 이미지 {len(result.skipped)}장:", ""]
        lines += [f"- `{path}`" for path in result.skipped]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="NFR-PRED-001 AI 모델 평가 (Recall >= 0.90, Accuracy >= 0.80)")
    parser.add_argument("--data-dir", required=True, type=Path, help="NORMAL/PNEUMONIA 폴더가 있는 테스트 데이터 경로")
    parser.add_argument("--model-name", required=True, help="AI_MODEL_NAME으로 쓸 모델 이름·버전 (예: resnet18-v1)")
    parser.add_argument("--data-source", default="", help="평가 데이터 출처 (기록용)")
    parser.add_argument("--output", type=Path, help="결과 기록 파일 경로 (기본: docs/모델평가_<모델이름>.md)")
    args = parser.parse_args()

    samples = collect_samples(args.data_dir)
    normal = sum(1 for s in samples if s.label == 0)
    pneumonia = len(samples) - normal
    print(f"평가 데이터: {len(samples)}장 (폐렴 {pneumonia} / 정상 {normal})", file=sys.stderr)

    result = evaluate(samples)
    report = format_report(result, args.model_name, args.data_source or str(args.data_dir))

    output = args.output or DOCS_DIR / f"모델평가_{args.model_name}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(report)
    print(f"기록 저장: {output}", file=sys.stderr)

    # 기준을 통과하지 못하면 종료 코드 1 (배포 전 자동 확인에 사용할 수 있음)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
