import argparse
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path

# Important: these must be imported exactly as requested
from model import UNet
from dataset import FloodDataset, get_dataloaders


def train_epoch(model, dataloader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    
    for images, masks in dataloader:
        images, masks = images.to(device), masks.to(device)
        
        optimizer.zero_grad()
        preds = model(images)
        loss = criterion(preds, masks)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        
    return total_loss / len(dataloader)


def validate_epoch(model, dataloader, criterion, device):
    model.eval()
    total_loss = 0.0
    intersection = 0.0
    union = 0.0
    
    with torch.no_grad():
        for images, masks in dataloader:
            images, masks = images.to(device), masks.to(device)
            
            preds = model(images)
            loss = criterion(preds, masks)
            total_loss += loss.item()
            
            # IoU Calculation: (pred>0.5 & mask).sum() / ((pred>0.5 | mask).sum() + 1e-8)
            p_bin = (preds > 0.5).float()
            intersection += (p_bin * masks).sum().item()
            union += torch.max(p_bin, masks).sum().item()
            
    val_loss = total_loss / len(dataloader)
    val_iou = intersection / (union + 1e-8)
    return val_loss, val_iou


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Flood U-Net")
    parser.add_argument("--image_dir", type=str, default="data/images", help="Path to image dir")
    parser.add_argument("--mask_dir", type=str, default="data/masks", help="Path to mask dir")
    parser.add_argument("--epochs", type=int, default=50, help="Number of epochs")
    parser.add_argument("--batch_size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--val_split", type=float, default=0.2, help="Validation split ratio")
    parser.add_argument("--save_path", type=str, default="flood_unet.pth", help="Path to save best model")
    
    # Argparse boolean trick for augment
    parser.add_argument("--augment", type=str, default="True", help="Whether to apply augmentations")
    parser.add_argument("--resume", type=str, default=None, help="Path to existing .pth to resume from")

    args = parser.parse_args()
    augment_bool = args.augment.lower() in ("true", "1", "t", "yes")

    train_loader, val_loader = get_dataloaders(
        image_dir=args.image_dir,
        mask_dir=args.mask_dir,
        val_split=args.val_split,
        batch_size=args.batch_size,
        augment=augment_bool
    )

    if train_loader is None or len(train_loader) == 0:
        print("0 image/mask pairs found.")
        print("Expected folder structure:")
        print(f"  {args.image_dir}/  <- .tif images")
        print(f"  {args.mask_dir}/   <- .tif masks")
        print("Please ensure filenames match exactly between the two folders.")
        sys.exit(0)

    # Device Selection: CUDA -> MPS -> CPU
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"Using device: {device}")

    # Build model
    model = UNet()
    model = model.to(device)

    # Resume training
    if args.resume is not None:
        if Path(args.resume).exists():
            print(f"Resuming from {args.resume}...")
            model.load_state_dict(torch.load(args.resume, map_location=device))
        else:
            print(f"Warning: resume path {args.resume} does not exist. Starting from scratch.")

    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    best_val_loss = float('inf')

    # Training Loop
    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_iou = validate_epoch(model, val_loader, criterion, device)
        
        print(f"Epoch {epoch}/{args.epochs} - train_loss: {train_loss:.4f} - val_loss: {val_loss:.4f} - val_IoU: {val_iou:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            # Save best model
            torch.save(model.state_dict(), args.save_path)

    print(f"Training complete. Best val_loss: {best_val_loss:.4f}. Model saved to {args.save_path}")
