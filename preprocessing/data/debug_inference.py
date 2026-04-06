# Run this as a quick diagnostic script — save as debug_inference.py
import torch
import rasterio
import numpy as np
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from model import UNet

TILE = 256
STRIDE = 200

model = UNet()
model.load_state_dict(torch.load("flood_unet.pth", map_location="cpu"))
model.eval()

with rasterio.open("data/images/Ghana_103272_S1Hand.tif") as src:
    data = src.read(1).astype(np.float32)
    print(f"Image shape: {data.shape}")
    print(f"Image value range: {data.min():.4f} to {data.max():.4f}")
    print(f"Image mean: {data.mean():.4f}")

H, W = data.shape
all_probs = []

for y in range(0, H - TILE + 1, STRIDE):
    for x in range(0, W - TILE + 1, STRIDE):
        patch = data[y:y+TILE, x:x+TILE]
        patch_norm = (patch - patch.min()) / (patch.max() - patch.min() + 1e-8)
        t = torch.tensor(patch_norm).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            prob = model(t).squeeze().numpy()
        all_probs.append(prob)

all_probs = np.array(all_probs)
print(f"\n--- Model output stats across {len(all_probs)} tiles ---")
print(f"Prob min:    {all_probs.min():.6f}")
print(f"Prob max:    {all_probs.max():.6f}")
print(f"Prob mean:   {all_probs.mean():.6f}")
print(f"Prob median: {np.median(all_probs):.6f}")
print(f"\nPixels > 0.5:  {(all_probs > 0.5).sum()}")
print(f"Pixels > 0.3:  {(all_probs > 0.3).sum()}")
print(f"Pixels > 0.1:  {(all_probs > 0.1).sum()}")
print(f"Pixels > 0.05: {(all_probs > 0.05).sum()}")