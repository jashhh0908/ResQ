import os
import random
import numpy as np
import rasterio
import torch
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.dataset import random_split
from pathlib import Path


class FloodDataset(Dataset):
    def __init__(self, image_dir, mask_dir, split="train", augment=True):
        """
        Args:
            image_dir (str): Path to directory with SAR images (e.g., S1Hand).
            mask_dir (str): Path to directory with Labels (e.g., LabelHand).
            split (str): 'train' or 'val'. Alters cropping strategy.
            augment (bool): Whether to apply data augmentation.
        """
        self.image_dir = Path(image_dir)
        self.mask_dir = Path(mask_dir)
        self.split = split
        self.augment = augment
        self.crop_size = 256

        # Discover valid pairs
        # Assume standard SEN1FLOODS11 naming, or identical names.
        self.image_files = []
        self.mask_files = []

        if self.image_dir.exists() and self.mask_dir.exists():
            for img_name in os.listdir(self.image_dir):
                if not img_name.endswith(".tif"):
                    continue
                
                # Attempt to find corresponding mask
                mask_name_candidates = [
                    img_name,                                  # exact match
                    img_name.replace("S1Hand", "LabelHand"),   # Sen1Floods11 match
                ]
                
                for m_name in mask_name_candidates:
                    mask_path = self.mask_dir / m_name
                    if mask_path.exists():
                        self.image_files.append(img_name)
                        self.mask_files.append(m_name)
                        break

        # Sort for reproducible order
        self.image_files.sort()
        self.mask_files.sort()

    def __len__(self):
        return len(self.image_files)

    def _normalize(self, image):
        """Per-patch min-max normalization, gracefully ignoring NaNs."""
        image = np.nan_to_num(image, nan=0.0) # Handle NaN / Nodata
        v_min = image.min()
        v_max = image.max()
        if v_max - v_min < 1e-6:
            return np.zeros_like(image)
        return (image - v_min) / (v_max - v_min)

    def _binarize(self, mask):
        """Dynamic binarization based on actual values > 0."""
        # SEN1FLOODS11 typically has 0=nodata/unlabeled, 1=water, 2=not water etc
        # Alternatively, just use whatever the max value is as positive class, but >0 is safe if strictly binary.
        # Let's use standard >0 as 1. If we discover unique values (e.g. 0, 1, -1),
        # water is typically 1. We'll map == 1 to 1, everything else 0.
        u_vals = np.unique(mask)
        if 1 in u_vals and 2 in u_vals:
            # specifically for sen1floods11: 1=water, 2=not water, 0=nodata
            return (mask == 1).astype(np.float32)
        elif mask.max() > 0:
            return (mask == mask.max()).astype(np.float32)
        else:
            return np.zeros_like(mask, dtype=np.float32)

    def __getitem__(self, idx):
        img_path = self.image_dir / self.image_files[idx]
        mask_path = self.mask_dir / self.mask_files[idx]

        # Load image with rasterio (Band 1/VV)
        with rasterio.open(str(img_path)) as src:
            image = src.read(1).astype(np.float32)

        # Load mask
        with rasterio.open(str(mask_path)) as src:
            mask = src.read(1).astype(np.float32)

        # Handle size / Cropping
        h, w = image.shape
        if h > self.crop_size or w > self.crop_size:
            if self.split == "train":
                y = random.randint(0, max(0, h - self.crop_size))
                x = random.randint(0, max(0, w - self.crop_size))
            else:
                y = max(0, h - self.crop_size) // 2
                x = max(0, w - self.crop_size) // 2

            image = image[y:y+self.crop_size, x:x+self.crop_size]
            mask = mask[y:y+self.crop_size, x:x+self.crop_size]

        # Normalize and Binarize
        image = self._normalize(image)
        mask = self._binarize(mask)

        # Add channel dim
        image = np.expand_dims(image, axis=0) # [1, H, W]
        mask = np.expand_dims(mask, axis=0)

        # Augmentation
        if self.augment and self.split == "train":
            # H-flip
            if random.random() > 0.5:
                image = np.flip(image, axis=2).copy()
                mask = np.flip(mask, axis=2).copy()
            # V-flip
            if random.random() > 0.5:
                image = np.flip(image, axis=1).copy()
                mask = np.flip(mask, axis=1).copy()
            # 90-rot
            if random.random() > 0.5:
                k = random.randint(1, 3)
                image = np.rot90(image, k, axes=(1, 2)).copy()
                mask = np.rot90(mask, k, axes=(1, 2)).copy()

        return torch.from_numpy(image), torch.from_numpy(mask)


def get_dataloaders(image_dir, mask_dir, val_split=0.2, batch_size=8, augment=True):
    # Base dataset to get total lengths
    full_dataset = FloodDataset(image_dir, mask_dir, split="train", augment=augment)
    total_len = len(full_dataset)
    
    if total_len == 0:
        return None, None
        
    val_len = int(total_len * val_split)
    train_len = total_len - val_len
    
    # We must construct 2 distinct dataset objects so they can have split="train" vs "val"
    # To do this safely, we will shuffle the indices explicitly.
    indices = torch.randperm(total_len).tolist()
    train_idx = indices[:train_len]
    val_idx = indices[train_len:]
    
    train_dataset = FloodDataset(image_dir, mask_dir, split="train", augment=augment)
    val_dataset = FloodDataset(image_dir, mask_dir, split="val", augment=False)
    
    # PyTorch Subset
    train_subset = torch.utils.data.Subset(train_dataset, train_idx)
    val_subset = torch.utils.data.Subset(val_dataset, val_idx)
    
    train_loader = DataLoader(train_subset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_subset, batch_size=batch_size, shuffle=False)
    
    # Print dataset summary
    first_img, first_mask = full_dataset[0]
    u_vals = np.unique(first_mask.numpy())
    print(f"Dataset: {total_len} pairs found | Image shape: {first_img.shape[1]}x{first_img.shape[2]} | Mask unique values: {u_vals}")
    
    return train_loader, val_loader
