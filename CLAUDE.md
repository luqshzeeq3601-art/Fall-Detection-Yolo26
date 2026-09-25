# Project: Machine Learning & Python Intelligence

## Stack & Architecture
- **Language**: Python 3.10+
- **Core Libraries**: PyTorch / TensorFlow, OpenCV, Ultralytics YOLO, Pandas, NumPy, Scikit-Learn, FastAPI / Flask
- **Package Manager**: `uv` or `pip` / `requirements.txt`

## Development Guidelines
1. **Type Annotations**: Use Python type hints on all public functions and data pipelines.
2. **Reproducibility**: Set random seeds (`torch.manual_seed`, `np.random.seed`) where deterministic benchmarks are required.
3. **Hardware Acceleration**: Guard GPU / CUDA / MPS calls with automatic CPU fallback.
4. **Data Validation**: Validate tensor shapes and input dimensions before feeding inference models.

## Verification & Testing
```bash
# Run test suite
pytest tests/ -v

# Code formatting & linting
ruff check .
black --check .
```
