# AI 모델 평가 결과 — resnet18-v1

- 평가일: 2026-10-28
- 기준: 6일차 AI 폐렴예측 API 설계 명세서 6장 (`NFR-PRED-001`)
- 평가 스크립트: `worker/evaluate.py` (서비스와 같은 `worker.predict.predict_pneumonia` 사용)

| 항목 | 값 |
|---|---|
| 모델 이름·버전 (`AI_MODEL_NAME`) | resnet18-v1 (`worker/models/best_resnet18.pth`) |
| 평가 데이터 (출처, 표본 수, 폐렴/정상 비율) | `train.csv`의 검증 분할 (학습 노트북 `폐_분류_개선_v2.ipynb`와 동일: stratify 8:2, `random_state=42`), 1044장, 폐렴 776 / 정상 268 |
| 폐렴 판정 임계값 | argmax (폐렴 확률 0.5) — 서비스와 동일 |
| TP / FP / FN / TN | 769 / 3 / 7 / 265 |
| Recall (기준 ≥ 0.90) | 0.9910 |
| Accuracy (기준 ≥ 0.80) | 0.9904 |
| 반영 여부 | ✅ 반영 가능 |

## 참고 지표

| 지표 | 값 |
|---|---|
| Precision | 0.9961 |
| Specificity | 0.9888 |
| F1 | 0.9935 |
| AUC | 0.9995 |

## 혼동 행렬

| | 모델: 폐렴 | 모델: 정상 |
|---|---|---|
| **실제: 폐렴** | TP 769 | FN 7 |
| **실제: 정상** | FP 3 | TN 265 |

## 평가 시 확인 사항

- **클래스 순서:** `class_id = 1`이 폐렴임을 확인했다. (명세서 10장 19번)
- **검증 데이터가 학습에 쓰이지 않았는지:** 학습 노트북은 `train.csv`를 8:2로 나눠 학습용 4,172장만 학습에 사용했고, 최종 재학습은 하지 않았다. 참고로 `train.csv` 전체(5,216장)로 평가했을 때의 오답(FP 3, FN 14) 중 FP 3개 전부와 FN 7개가 이 검증 데이터에서 나와, 검증 데이터가 학습되지 않았음과 일치한다.
- **검증 데이터의 한계:** 검증 데이터는 학습에는 쓰이지 않았지만 best epoch 선택(검증 AUC 기준)에는 사용되었다. 완전히 독립된 테스트 데이터보다 약간 유리한 결과일 수 있으므로, 정답이 있는 별도 테스트 데이터가 생기면 다시 평가한다. (대회 `test` 데이터는 정답 라벨이 없어 사용하지 못했다)
- **임계값:** 학습 노트북은 검증 데이터로 고른 임계값(F2 기준)을 사용했지만, 서비스(`predict.py`)는 argmax(0.5)를 사용하므로 서비스 기준으로 평가했다.

## 재현 방법

1. 학습 노트북과 같은 방식으로 검증 목록을 만든다.
   ```python
   from sklearn.model_selection import train_test_split
   tr_df, va_df = train_test_split(train_df, test_size=0.2, stratify=train_df["label"], random_state=42)
   ```
2. 검증 이미지를 `NORMAL/`(label 0), `PNEUMONIA/`(label 1) 폴더로 나눈다.
3. 평가를 실행한다.
   ```bash
   uv run python -m worker.evaluate --data-dir <검증 데이터 폴더> --model-name resnet18-v1
   ```
