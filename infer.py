import os
import sys
import argparse
import numpy as np
import rasterio
import torch
import requests
import json
from rasterio.features import shapes
from shapely.geometry import shape
from scipy.ndimage import distance_transform_edt
from skimage.morphology import disk, binary_dilation
from pathlib import Path

# Add preprocessing dir to path to import helpers
sys.path.append(str(Path(__file__).parent / "preprocessing"))
from flood_detector import generate_dem_from_sar

from model import UNet

TILE = 256
STRIDE = 200
DILATION_RADIUS_PX = 20  # 20 pixels = roughly 200m spread bounds for contour vis
ELEVATION_BUFFER_M = 1.5
ASSUMED_VELOCITY_M_PER_S = 0.01  # ~36 meters per hour lateral spread

def get_sliding_window_patches(height, width):
    patches = []
    for y in range(0, height, STRIDE):
        for x in range(0, width, STRIDE):
            y0 = min(y, height - TILE)
            y0 = max(y0, 0)
            x0 = min(x, width - TILE)
            x0 = max(x0, 0)
            patches.append((y0, x0))
    return list(set(patches))

def infer(image_path, model_path, node_url):
    device = torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))
    
    model = UNet()
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()

    print(f"Loading {image_path}...")
    with rasterio.open(image_path) as src:
        image = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs
        sar_meta = {
            "crs": crs,
            "transform": transform,
            "width": src.width,
            "height": src.height,
            "nodata": src.nodata
        }

    # Normalize image per-patch strategy globally
    v_min, v_max = image.min(), image.max()
    if v_max - v_min > 1e-6:
        image_norm = (image - v_min) / (v_max - v_min)
    else:
        image_norm = np.zeros_like(image)

    height, width = image.shape
    accum_mask = np.zeros((height, width), dtype=np.float32)
    accum_weight = np.zeros((height, width), dtype=np.float32)

    patches = get_sliding_window_patches(height, width)
    print(f"Running U-Net inference across {len(patches)} sliding windows...")

    with torch.no_grad():
        for y0, x0 in patches:
            patch = image_norm[y0:y0+TILE, x0:x0+TILE]
            pad_y = max(0, TILE - patch.shape[0])
            pad_x = max(0, TILE - patch.shape[1])
            if pad_y > 0 or pad_x > 0:
                patch = np.pad(patch, ((0, pad_y), (0, pad_x)), mode='reflect')
            
            patch_tensor = torch.from_numpy(patch).unsqueeze(0).unsqueeze(0).to(device)
            pred = model(patch_tensor).squeeze().cpu().numpy()
            
            if pad_y > 0 or pad_x > 0:
                pred = pred[:TILE-pad_y, :TILE-pad_x]
                
            accum_mask[y0:y0+TILE, x0:x0+TILE] += pred
            accum_weight[y0:y0+TILE, x0:x0+TILE] += 1.0

    accum_weight[accum_weight == 0] = 1.0
    avg_mask = accum_mask / accum_weight
    water_mask = (avg_mask > 0.5).astype(bool)

    # -------------------------------------------------------------
    # SPREAD PREDICTION & ETA VELOCITY CONTOURS
    # -------------------------------------------------------------
    import logging
    logging.getLogger("resq.flood").setLevel(logging.WARNING) # Mute generation logs
    print("Generating Synthetic DEM and Spread Constraints...")
    dem_data, _ = generate_dem_from_sar(image, sar_meta)
    
    if water_mask.sum() > 0:
        mean_flood_elev = float(np.nanmean(dem_data[water_mask]))
    else:
        mean_flood_elev = 0.0
        
    max_allowed = mean_flood_elev + ELEVATION_BUFFER_M
    structuring_element = disk(DILATION_RADIUS_PX)
    dilated_mask = binary_dilation(water_mask, footprint=structuring_element)
    
    elevation_ok = dem_data <= max_allowed
    full_predicted_mask = (dilated_mask & elevation_ok) | water_mask
    spread_only_mask = full_predicted_mask & ~water_mask
    
    print("Calculating Hydrodynamic Velocity Pixels...")
    # Distance transform from standard dry surface strictly out
    background = ~water_mask
    dist_map_px = distance_transform_edt(background)
    dist_map_m = dist_map_px * 10.0  # Approx 10m/px for Sentinel-1
    eta_hours = dist_map_m / (ASSUMED_VELOCITY_M_PER_S * 3600)

    print("Vectorising shapes into GeoJSON Time Contours...")
    polygons = []
    
    # 1. Base flood (Current)
    for geom, value in shapes(water_mask.astype(np.uint8), transform=transform):
        if value == 1:
            polygons.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {"hazard_type": "flood_current"}
            })
            
    # 2. Spread Zone (Time Contours)
    bands = [
        (0.0, 1.0, "< 1 Hour"),
        (1.0, 3.0, "1 - 3 Hours"),
        (3.0, float('inf'), "3+ Hours")
    ]
    
    for (min_hr, max_hr, label) in bands:
        band_mask = spread_only_mask & (eta_hours > min_hr) & (eta_hours <= max_hr)
        band_uint8 = band_mask.astype(np.uint8)
        for geom, value in shapes(band_uint8, transform=transform):
            if value == 1:
                polygons.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "hazard_type": "flood_spread",
                        "eta_category": label
                    }
                })

    feature_collection = {
        "type": "FeatureCollection",
        "features": polygons
    }

    print(f"Generated GeoJSON with {len(polygons)} categorized polygons (Current + Spread).")

    if node_url:
        print(f"POSTing payload to NODE_URL: {node_url}")
        try:
            resp = requests.post(node_url, json=feature_collection, timeout=120)
            resp.raise_for_status()
            print("Successfully POSTed to backend.")
        except Exception as e:
            print(f"Failed to POST to {node_url}: {e}")
            
    out_name = image_path.replace(".tif", "_inference.geojson")
    with open(out_name, "w") as f:
        json.dump(feature_collection, f)
    print(f"Saved locally to {out_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Flood U-Net Inference & Velocity Modeling")
    parser.add_argument("--image", required=True, help="Input SAR .tif image path")
    parser.add_argument("--model", required=True, help="Path to trained .pth model file")
    
    args = parser.parse_args()
    target_node_url = os.environ.get("NODE_URL", None)
    
    infer(args.image, args.model, target_node_url)
