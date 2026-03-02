---
name: model-training
description: Machine learning model training with PyTorch, JAX, training loops, and experiment tracking
version: 1.0.0
triggers:
  - pytorch
  - torch
  - jax
  - training
  - model
  - neural network
  - deep learning
  - machine learning
  - ml
  - training loop
  - wandb
  - tensorboard
tags:
  - python
  - ml
  - pytorch
  - training
  - deep-learning
---

# Model Training Development

## Summary

ML model training workflows:
1. **Data preparation** - Datasets, dataloaders, preprocessing
2. **Model definition** - Architecture, layers, parameters
3. **Training loop** - Forward, loss, backward, optimize
4. **Evaluation** - Metrics, validation, testing
5. **Experiment tracking** - Logging, checkpointing, hyperparameters
6. **Deployment** - Export, serving, optimization

**Project structure:**
```
ml-project/
├── configs/           # Hydra/YAML configs
├── data/
│   ├── raw/
│   └── processed/
├── src/
│   ├── data/          # Datasets, transforms
│   ├── models/        # Model architectures
│   ├── training/      # Training logic
│   └── evaluation/    # Metrics, evaluation
├── scripts/           # Training scripts
├── notebooks/         # Exploration
├── checkpoints/       # Saved models
└── outputs/           # Logs, results
```

**Key principles:**
- Reproducibility (seeds, versioning)
- Modular design (separate concerns)
- Configuration-driven (hydra/yaml)
- Experiment tracking (wandb/mlflow)

## Details

### PyTorch Dataset and DataLoader

```python
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms

class CustomDataset(Dataset):
    def __init__(self, data_path: str, transform=None):
        self.data = self.load_data(data_path)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        item = self.data[idx]
        image, label = item['image'], item['label']

        if self.transform:
            image = self.transform(image)

        return image, label

# Transforms
train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(10),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225]),
])

# DataLoader
train_loader = DataLoader(
    dataset=train_dataset,
    batch_size=32,
    shuffle=True,
    num_workers=4,
    pin_memory=True,
)
```

### Model Definition

```python
import torch.nn as nn
import torch.nn.functional as F

class ConvNet(nn.Module):
    def __init__(self, num_classes: int = 10):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(64 * 8 * 8, 256)
        self.fc2 = nn.Linear(256, num_classes)
        self.dropout = nn.Dropout(0.5)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)  # Flatten
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x

# Initialize
model = ConvNet(num_classes=10)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
```

### Training Loop

```python
def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> dict[str, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (inputs, targets) in enumerate(loader):
        inputs, targets = inputs.to(device), targets.to(device)

        # Forward pass
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)

        # Backward pass
        loss.backward()
        optimizer.step()

        # Track metrics
        total_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

    return {
        "loss": total_loss / len(loader),
        "accuracy": 100.0 * correct / total,
    }

@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for inputs, targets in loader:
        inputs, targets = inputs.to(device), targets.to(device)
        outputs = model(inputs)
        loss = criterion(outputs, targets)

        total_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

    return {
        "loss": total_loss / len(loader),
        "accuracy": 100.0 * correct / total,
    }
```

### Full Training Script

```python
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path

def train(config: dict) -> None:
    # Setup
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(config["seed"])

    # Data
    train_loader, val_loader = get_dataloaders(config)

    # Model
    model = ConvNet(num_classes=config["num_classes"]).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(
        model.parameters(),
        lr=config["learning_rate"],
        weight_decay=config["weight_decay"],
    )
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=config["epochs"]
    )

    # Training loop
    best_val_acc = 0.0
    checkpoint_dir = Path(config["checkpoint_dir"])
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(config["epochs"]):
        train_metrics = train_epoch(model, train_loader, optimizer, criterion, device)
        val_metrics = evaluate(model, val_loader, criterion, device)
        scheduler.step()

        print(f"Epoch {epoch+1}/{config['epochs']}")
        print(f"  Train Loss: {train_metrics['loss']:.4f}, Acc: {train_metrics['accuracy']:.2f}%")
        print(f"  Val Loss: {val_metrics['loss']:.4f}, Acc: {val_metrics['accuracy']:.2f}%")

        # Save best model
        if val_metrics["accuracy"] > best_val_acc:
            best_val_acc = val_metrics["accuracy"]
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_accuracy": best_val_acc,
            }, checkpoint_dir / "best_model.pt")

    print(f"Best Validation Accuracy: {best_val_acc:.2f}%")
```

### Experiment Tracking with W&B

```python
import wandb

def train_with_wandb(config: dict) -> None:
    # Initialize W&B
    wandb.init(
        project="my-project",
        config=config,
        name=f"run_{config['learning_rate']}",
    )

    # ... setup code ...

    for epoch in range(config["epochs"]):
        train_metrics = train_epoch(...)
        val_metrics = evaluate(...)

        # Log to W&B
        wandb.log({
            "epoch": epoch,
            "train/loss": train_metrics["loss"],
            "train/accuracy": train_metrics["accuracy"],
            "val/loss": val_metrics["loss"],
            "val/accuracy": val_metrics["accuracy"],
            "learning_rate": scheduler.get_last_lr()[0],
        })

    # Log final model
    wandb.save(str(checkpoint_dir / "best_model.pt"))
    wandb.finish()
```

## Advanced

### Mixed Precision Training

```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for inputs, targets in train_loader:
    inputs, targets = inputs.to(device), targets.to(device)

    optimizer.zero_grad()

    # Forward with autocast
    with autocast():
        outputs = model(inputs)
        loss = criterion(outputs, targets)

    # Backward with scaling
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
```

### Gradient Accumulation

```python
accumulation_steps = 4
optimizer.zero_grad()

for i, (inputs, targets) in enumerate(train_loader):
    inputs, targets = inputs.to(device), targets.to(device)

    outputs = model(inputs)
    loss = criterion(outputs, targets) / accumulation_steps
    loss.backward()

    if (i + 1) % accumulation_steps == 0:
        optimizer.step()
        optimizer.zero_grad()
```

### Distributed Training

```python
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

def setup(rank: int, world_size: int):
    dist.init_process_group("nccl", rank=rank, world_size=world_size)
    torch.cuda.set_device(rank)

def train_distributed(rank: int, world_size: int, config: dict):
    setup(rank, world_size)

    model = ConvNet().to(rank)
    model = DDP(model, device_ids=[rank])

    # Use DistributedSampler
    sampler = DistributedSampler(train_dataset, num_replicas=world_size, rank=rank)
    train_loader = DataLoader(train_dataset, sampler=sampler, ...)

    # Training loop
    for epoch in range(config["epochs"]):
        sampler.set_epoch(epoch)  # Important for shuffling
        train_epoch(model, train_loader, ...)

    dist.destroy_process_group()
```

### Model Export

```python
# Save for inference
torch.save(model.state_dict(), "model.pt")

# ONNX export
dummy_input = torch.randn(1, 3, 32, 32).to(device)
torch.onnx.export(
    model,
    dummy_input,
    "model.onnx",
    input_names=["input"],
    output_names=["output"],
    dynamic_axes={"input": {0: "batch_size"}},
)

# TorchScript
scripted_model = torch.jit.script(model)
scripted_model.save("model_scripted.pt")
```

### Hyperparameter Tuning

```python
import optuna

def objective(trial: optuna.Trial) -> float:
    config = {
        "learning_rate": trial.suggest_float("lr", 1e-5, 1e-2, log=True),
        "batch_size": trial.suggest_categorical("batch_size", [16, 32, 64]),
        "dropout": trial.suggest_float("dropout", 0.1, 0.5),
    }

    # Train and return validation accuracy
    val_acc = train(config)
    return val_acc

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=100)
print(f"Best params: {study.best_params}")
```

## Resources

- [PyTorch Docs](https://pytorch.org/docs/)
- [PyTorch Lightning](https://lightning.ai/docs/)
- [Weights & Biases](https://docs.wandb.ai/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers/)
- [Optuna](https://optuna.readthedocs.io/)
