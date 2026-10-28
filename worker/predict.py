
from pathlib import Path

import torch
from torch import nn
from torchvision import models, transforms
from PIL import Image


# 모델 가중치 파일 경로
MODEL_PATH = Path(__file__).parent / "models" / "best_resnet18.pth"

# 실행 장치 설정
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 조원이 학습한 ResNet18 모델 구조 생성
model = models.resnet18(weights=None)

in_features = model.fc.in_features
model.fc = nn.Sequential(
    nn.Dropout(0.5),
    nn.Linear(in_features, 2),
)


# 모델을 한 번만 로드 (서버 시작 시 lifespan에서 load_model()을 호출한다)
_loaded_model = None


def load_model():
    """학습된 가중치를 불러와 전역에 보관한다. (서버 시작 시 한 번 호출)"""
    global _loaded_model

    checkpoint = torch.load(
        MODEL_PATH,
        map_location=DEVICE,
        weights_only=True,
    )

    model.load_state_dict(checkpoint)
    model.to(DEVICE)
    model.eval()

    _loaded_model = model
    return model


# X-ray 이미지 전처리
transform = transforms.Compose([
    transforms.Grayscale(num_output_channels=3),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])


def predict_pneumonia(image: Image.Image) -> dict:
    """X-ray 이미지를 받아 정상/폐렴을 예측한다."""
    global _loaded_model

    if _loaded_model is None:
        _loaded_model = load_model()

    image_tensor = transform(image.convert("RGB")).unsqueeze(0).to(DEVICE)

    with torch.inference_mode():
        outputs = _loaded_model(image_tensor)
        probabilities = torch.softmax(outputs, dim=1)[0]

    predicted_class = int(torch.argmax(probabilities).item())

    return {
        "class_id": predicted_class,
        "label": "Pneumonia" if predicted_class == 1 else "Normal",
        "confidence": float(probabilities[predicted_class].item()),
    }
