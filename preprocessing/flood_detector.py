"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ResQ  ·  Autonomous Flood Detection & Spread Prediction Worker            ║
║──────────────────────────────────────────────────────────────────────────────║
║  Pipeline:                                                                 ║
║    1. Download Sentinel-1 SAR from SEN1FLOODS11 (Google Cloud Storage)     ║
║    2. Otsu threshold on VV backscatter  → binary water mask                ║
║    3. Morphological dilation + DEM-constrained expansion  → spread mask    ║
║    4. Vectorise BOTH masks → two GeoJSON FeatureCollections (EPSG:4326)    ║
║       • flood_current  – areas currently under water                       ║
║       • flood_spread   – areas where water may expand next                 ║
║    5. POST combined GeoJSON to Node.js backend webhook                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Data source : SEN1FLOODS11  (Cloud-to-Street / IEEE)
              512×512 Sentinel-1 GRD chips, VV+VH, EPSG:4326, 10 m
              https://github.com/cloudtostreet/Sen1Floods11

Author  : ResQ AI Team
Licence : MIT
"""

# ── Standard library ─────────────────────────────────────────────────────────
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# ── Third-party ──────────────────────────────────────────────────────────────
import numpy as np                          # Array math
import rasterio                             # Geospatial raster I/O
from rasterio.features import shapes       # Raster → vector polygons
from rasterio.transform import Affine      # Pixel ↔ geographic mapping
from rasterio.crs import CRS              # Coordinate reference systems
from skimage.filters import threshold_otsu # Otsu's automatic thresholding
from skimage.morphology import (
    binary_dilation,                        # Expand binary regions
    disk,                                   # Circular structuring element
)
import pandas as pd                         # DataFrame operations (concat)
import geopandas as gpd                     # Vector geospatial operations
from shapely.geometry import shape          # GeoJSON geometry → Shapely
import requests                             # HTTP client for webhook

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("resq.flood")


# ── Configuration constants ──────────────────────────────────────────────────
WEBHOOK_URL = "http://localhost:5000/api/hazards"   # Node.js backend endpoint
DILATION_RADIUS_PX  = 5     # Pixels to dilate flood mask (≈ time step proxy)
ELEVATION_BUFFER_M  = 1.5   # DEM tolerance above mean flood elevation (m)

# ── SEN1FLOODS11 GCS bucket (public, no auth required) ──────────────────────
#   Files are Cloud-Optimized GeoTIFFs served over HTTPS.
#   Naming: {Event}_{ChipID}_S1Hand.tif  →  2-band (VV, VH), 512×512, EPSG:4326
GCS_BASE = "https://storage.googleapis.com/sen1floods11"
S1_PATH  = "v1.1/data/flood_events/HandLabeled/S1Hand"

# Curated list of known-good chips with visible flooding (hand-labeled split).
# Each entry:  (event_country, chip_id, description)
SAMPLE_CHIPS = [
    ("India",     "698338",  "NE India, Assam floods 2016-08"),
    ("India",     "804466",  "India flooding event"),
    ("India",     "566697",  "India flooding event"),
    ("India",     "373039",  "India flooding event"),
    ("India",     "56450",   "India flooding event"),
    ("Sri-Lanka", "249079",  "Sri Lanka floods"),
    ("Pakistan",  "548910",  "Pakistan floods"),
    ("Somalia",   "685158",  "Somalia floods"),
    ("Bolivia",   "233925",  "Bolivia floods"),
    ("USA",       "933610",  "USA flood event"),
    ("Nigeria",   "81933",   "Nigeria floods"),
    ("Mekong",    "922373",  "Mekong Delta floods"),
    ("Ghana",     "234935",  "Ghana floods"),
]

# Default chip to use when no arguments are provided
DEFAULT_CHIP = SAMPLE_CHIPS[0]   # India_698338 (good flood visibility)


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  SEN1FLOODS11  DATA DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════

def build_s1_url(event: str, chip_id: str) -> str:
    """
    Construct the HTTPS URL for a SEN1FLOODS11 Sentinel-1 chip.

    Example
    -------
    >>> build_s1_url("India", "698338")
    'https://storage.googleapis.com/sen1floods11/v1.1/data/flood_events/HandLabeled/S1Hand/India_698338_S1Hand.tif'
    """
    filename = f"{event}_{chip_id}_S1Hand.tif"
    return f"{GCS_BASE}/{S1_PATH}/{filename}"


def download_s1_chip(
    event: str,
    chip_id: str,
    output_dir: str | None = None,
) -> str:
    """
    Download a SEN1FLOODS11 Sentinel-1 GRD chip from Google Cloud Storage.

    The file is a Cloud-Optimized GeoTIFF with 2 bands:
      • Band 1 = VV polarisation  (used for flood detection)
      • Band 2 = VH polarisation

    Parameters
    ----------
    event : str
        Country/region name (e.g. "India", "Sri-Lanka", "Pakistan").
    chip_id : str
        Unique chip identifier (e.g. "698338").
    output_dir : str | None
        Directory to save the downloaded file.  Defaults to ./data/.

    Returns
    -------
    local_path : str
        Absolute path to the downloaded .tif file.
    """
    url = build_s1_url(event, chip_id)
    filename = f"{event}_{chip_id}_S1Hand.tif"

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "data")
    os.makedirs(output_dir, exist_ok=True)

    local_path = os.path.join(output_dir, filename)

    # Skip download if file already exists (idempotent)
    if os.path.exists(local_path):
        log.info("S1 chip already cached: %s", local_path)
        return local_path

    log.info("Downloading S1 chip from SEN1FLOODS11 …")
    log.info("  URL : %s", url)

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    # Stream to disk to handle large files gracefully
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)

    size_mb = downloaded / (1024 * 1024)
    log.info("  ✓ Saved → %s  (%.2f MB)", local_path, size_mb)
    return local_path


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  DATA  INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

def load_sar(filepath: str, band: int = 1) -> tuple[np.ndarray, dict]:
    """
    Open a SEN1FLOODS11 Sentinel-1 GeoTIFF and extract one band.

    SEN1FLOODS11 S1 chips have 2 bands:
      Band 1 = VV polarisation (best for flood detection — dark on water)
      Band 2 = VH polarisation

    Parameters
    ----------
    filepath : str
        Path to a SEN1FLOODS11 S1Hand .tif file (local or HTTP URL).
    band : int
        Which band to read (1 = VV, 2 = VH).  Default is VV.

    Returns
    -------
    data : np.ndarray
        2-D float32 array of SAR backscatter values.
    meta : dict
        Rasterio metadata dict (CRS, transform, nodata, shape …).
    """
    log.info("Loading SAR (band %d): %s", band, filepath)

    with rasterio.open(filepath) as src:
        log.info("  ↳ bands=%d  size=%dx%d  crs=%s",
                 src.count, src.width, src.height, src.crs)

        # Read the requested band as float32
        data = src.read(band).astype(np.float32)

        meta = {
            "crs":       src.crs,
            "transform": src.transform,
            "nodata":    src.nodata,
            "width":     src.width,
            "height":    src.height,
        }

    log.info("  ↳ shape=%s  nodata=%s  range=[%.4f, %.4f]",
             data.shape, meta["nodata"],
             float(np.nanmin(data)), float(np.nanmax(data)))
    return data, meta


def load_raster(filepath: str) -> tuple[np.ndarray, dict]:
    """
    Open a single-band GeoTIFF and return the pixel data + metadata.
    Used for DEM or any generic single-band raster.

    Parameters
    ----------
    filepath : str
        Path to a .tif raster file.

    Returns
    -------
    data : np.ndarray
        2-D float32 array of pixel values.
    meta : dict
        Rasterio metadata dict (CRS, transform, nodata, shape …).
    """
    log.info("Loading raster: %s", filepath)

    with rasterio.open(filepath) as src:
        data = src.read(1).astype(np.float32)
        meta = {
            "crs":       src.crs,
            "transform": src.transform,
            "nodata":    src.nodata,
            "width":     src.width,
            "height":    src.height,
        }

    log.info("  ↳ shape=%s  crs=%s  nodata=%s", data.shape, meta["crs"], meta["nodata"])
    return data, meta


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  SYNTHETIC DEM GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_dem_from_sar(
    sar_data: np.ndarray,
    sar_meta: dict,
    output_path: str | None = None,
) -> tuple[np.ndarray, dict]:
    """
    Generate a synthetic DEM that aligns with a SAR chip.

    SEN1FLOODS11 does not include DEM data, so we synthesise one.
    The trick:  use the SAR backscatter itself as a proxy for terrain.
      • Low backscatter (water) → low elevation
      • High backscatter (land) → higher elevation

    This is a *hackathon-grade* approximation.  For production, you'd use
    SRTM / Copernicus DEM 30m via OpenTopography API.

    Parameters
    ----------
    sar_data : np.ndarray
        2-D SAR backscatter array (VV band, float32).
    sar_meta : dict
        Rasterio metadata from the SAR chip.
    output_path : str | None
        If provided, write the synthetic DEM to this .tif file.

    Returns
    -------
    dem : np.ndarray (float32)
        Synthetic elevation array (metres), same shape as sar_data.
    meta : dict
        Same metadata as sar_meta (aligned CRS, transform, etc.).
    """
    log.info("Generating synthetic DEM from SAR backscatter proxy …")

    # Normalise SAR values to [0, 1] range
    valid = sar_data[np.isfinite(sar_data) & (sar_data > -9000)]
    if valid.size == 0:
        valid = sar_data.ravel()
    vmin, vmax = float(np.percentile(valid, 2)), float(np.percentile(valid, 98))

    if vmax - vmin < 1e-6:
        # Flat image — create gentle random terrain
        dem = np.random.uniform(2.0, 6.0, sar_data.shape).astype(np.float32)
    else:
        # Scale: low SAR (water) → ~1 m,  high SAR (land) → ~10 m
        normalised = np.clip((sar_data - vmin) / (vmax - vmin), 0, 1)
        dem = 1.0 + 9.0 * normalised

        # Add gentle random micro-terrain for realism
        dem += np.random.normal(0, 0.3, dem.shape).astype(np.float32)
        dem = np.clip(dem, 0.0, 30.0).astype(np.float32)

    log.info("  ↳ DEM range: [%.1f, %.1f] m", float(dem.min()), float(dem.max()))

    # Optionally save to disk
    if output_path:
        profile = {
            "driver":    "GTiff",
            "dtype":     "float32",
            "width":     sar_meta["width"],
            "height":    sar_meta["height"],
            "count":     1,
            "crs":       sar_meta["crs"],
            "transform": sar_meta["transform"],
            "nodata":    -9999.0,
        }
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(dem, 1)
        log.info("  ↳ Saved synthetic DEM → %s", output_path)

    meta = {**sar_meta, "nodata": -9999.0}
    return dem, meta


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  FLOOD DETECTION  –  OTSU THRESHOLDING
# ═══════════════════════════════════════════════════════════════════════════════

def detect_water_otsu(sar_data: np.ndarray, nodata_value: float | None) -> np.ndarray:
    """
    Apply Otsu's method to SAR backscatter to isolate standing water.

    SAR images of water appear *dark* (low backscatter) because smooth
    water surfaces act as specular reflectors, sending the radar pulse
    away from the sensor.  Otsu finds the optimal threshold that separates
    the bimodal histogram (water vs. land).

    Parameters
    ----------
    sar_data : np.ndarray
        2-D SAR backscatter array (float32), typically VV polarisation.
    nodata_value : float | None
        Pixel value representing "no data" (e.g. image edges).

    Returns
    -------
    water_mask : np.ndarray (bool)
        True where a pixel is classified as water/flooded.
    """
    # -------------------------------------------------------------------
    # Step A:  Build a validity mask.
    #   We must ignore nodata pixels (often zero or NaN at swath edges)
    #   because they would skew the histogram.
    # -------------------------------------------------------------------
    if nodata_value is not None:
        valid_mask = (sar_data != nodata_value) & np.isfinite(sar_data)
    else:
        valid_mask = np.isfinite(sar_data)

    # Also exclude exact-zero pixels (common no-data sentinel in SEN1FLOODS11)
    valid_mask = valid_mask & (sar_data != 0.0)

    valid_pixels = sar_data[valid_mask]

    if valid_pixels.size == 0:
        log.warning("No valid pixels found — returning empty mask")
        return np.zeros_like(sar_data, dtype=bool)

    # -------------------------------------------------------------------
    # Step B:  Compute the Otsu threshold on the valid pixel distribution.
    #   threshold_otsu minimises within-class variance of the two groups.
    # -------------------------------------------------------------------
    threshold = threshold_otsu(valid_pixels)
    log.info("Otsu threshold = %.4f", threshold)

    # -------------------------------------------------------------------
    # Step C:  Classify.
    #   Water = pixels *below* the threshold  (dark in SAR).
    #   Also enforce validity so nodata edges aren't falsely classified.
    # -------------------------------------------------------------------
    water_mask = (sar_data < threshold) & valid_mask

    flood_pixels = int(water_mask.sum())
    total_valid  = int(valid_mask.sum())
    log.info(
        "Water pixels detected: %s / %s (%.1f%%)",
        flood_pixels, total_valid, 100 * flood_pixels / max(total_valid, 1),
    )
    return water_mask


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  FLOOD SPREAD PREDICTION  –  MORPHOLOGICAL + DEM CONSTRAINT
# ═══════════════════════════════════════════════════════════════════════════════

def predict_flood_spread(
    water_mask: np.ndarray,
    dem_data:   np.ndarray,
    dilation_px: int   = DILATION_RADIUS_PX,
    elev_buffer: float = ELEVATION_BUFFER_M,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simulate where floodwater is *likely* to spread next.

    The trick (ideal for a hackathon) is:
      1. Dilate the current flood mask outward by `dilation_px` pixels.
         This represents the passage of time — water expanding.
      2. For each newly-wet pixel, check the DEM.  Only keep it if
         its elevation ≤ (mean flood elevation + buffer).
         This prevents water from "climbing" hills.

    Parameters
    ----------
    water_mask : np.ndarray (bool)
        Current detected flood extent from Otsu.
    dem_data : np.ndarray (float32)
        Matching DEM raster (elevations in metres).
    dilation_px : int
        Radius (in pixels) of the circular structuring element.
    elev_buffer : float
        Metres of tolerance above the mean flood elevation.

    Returns
    -------
    full_predicted_mask : np.ndarray (bool)
        Expanded flood extent (current + spread), constrained by topography.
    spread_only_mask : np.ndarray (bool)
        ONLY the newly-predicted spread area (excludes current flood).
        This is the "ring" around the current flood.
    """
    # -------------------------------------------------------------------
    # Step A:  Calculate the mean elevation of currently flooded pixels.
    #   This gives us a "water level" reference.
    # -------------------------------------------------------------------
    if water_mask.sum() == 0:
        log.warning("Empty water mask — skipping spread prediction")
        return water_mask.copy(), np.zeros_like(water_mask, dtype=bool)

    mean_flood_elev = float(np.nanmean(dem_data[water_mask]))
    max_allowed     = mean_flood_elev + elev_buffer
    log.info(
        "Mean flood elevation: %.2f m  →  max allowed: %.2f m  (buffer=%.1f m)",
        mean_flood_elev, max_allowed, elev_buffer,
    )

    # -------------------------------------------------------------------
    # Step B:  Morphological dilation.
    #   disk(r) creates a circular structuring element with radius r.
    #   binary_dilation expands True regions outward by that footprint.
    # -------------------------------------------------------------------
    structuring_element = disk(dilation_px)
    dilated_mask = binary_dilation(water_mask, footprint=structuring_element)
    log.info(
        "Dilation: radius=%d px  →  expanded from %d to %d pixels",
        dilation_px, int(water_mask.sum()), int(dilated_mask.sum()),
    )

    # -------------------------------------------------------------------
    # Step C:  DEM constraint.
    #   Only allow newly-flooded pixels if their elevation is low enough.
    #   Original flood pixels are always kept.
    # -------------------------------------------------------------------
    elevation_ok        = dem_data <= max_allowed
    full_predicted_mask = (dilated_mask & elevation_ok) | water_mask

    # -------------------------------------------------------------------
    # Step D:  Isolate the SPREAD-ONLY zone.
    #   Subtract the current flood from the full prediction to get
    #   only the pixels where water *may* expand next.
    #   This ensures the two output polygons never overlap.
    # -------------------------------------------------------------------
    spread_only_mask = full_predicted_mask & ~water_mask

    log.info(
        "After DEM constraint: %d total px  |  %d current flood  |  %d spread-only",
        int(full_predicted_mask.sum()),
        int(water_mask.sum()),
        int(spread_only_mask.sum()),
    )
    return full_predicted_mask, spread_only_mask


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  VECTORISATION  –  RASTER MASK → GeoJSON POLYGONS
# ═══════════════════════════════════════════════════════════════════════════════

def vectorise_mask(
    mask:        np.ndarray,
    transform:   Affine,
    src_crs:     CRS,
    hazard_type: str = "flood",
) -> gpd.GeoDataFrame:
    """
    Convert a boolean raster mask into a GeoDataFrame of polygons,
    re-projected to WGS-84 (EPSG:4326).

    Parameters
    ----------
    mask : np.ndarray (bool)
        A binary flood extent mask.
    transform : Affine
        Pixel → geographic coordinate mapping from the source raster.
    src_crs : CRS
        Coordinate reference system of the source raster.
    hazard_type : str
        Label to tag every polygon with — e.g. 'flood_current' or
        'flood_spread'.  Stored in the 'hazard_type' property of
        each GeoJSON feature.

    Returns
    -------
    gdf : gpd.GeoDataFrame
        Polygons in EPSG:4326 with a 'hazard_type' column.
    """
    log.info("Vectorising mask  [%s] …", hazard_type)

    # -------------------------------------------------------------------
    # Step A:  Convert boolean mask to uint8 (rasterio.features needs int).
    # -------------------------------------------------------------------
    mask_uint8 = mask.astype(np.uint8)

    # -------------------------------------------------------------------
    # Step B:  Extract polygon geometries for regions where mask == 1.
    #   `shapes()` yields (geometry_dict, pixel_value) tuples.
    #   We only keep features with value == 1 (flooded).
    # -------------------------------------------------------------------
    flood_polygons = [
        shape(geom)
        for geom, value in shapes(mask_uint8, transform=transform)
        if value == 1
    ]

    if not flood_polygons:
        log.warning("  No polygons extracted for [%s]", hazard_type)
        return gpd.GeoDataFrame(
            columns=["geometry", "hazard_type"], crs="EPSG:4326",
        )

    log.info("  ↳ %d polygon(s) extracted", len(flood_polygons))

    # -------------------------------------------------------------------
    # Step C:  Build a GeoDataFrame in the source CRS, then reproject.
    # -------------------------------------------------------------------
    gdf = gpd.GeoDataFrame(
        {"geometry": flood_polygons, "hazard_type": hazard_type},
        crs=src_crs,
    )

    # Reproject to WGS-84 for interoperability with web maps / APIs
    # (SEN1FLOODS11 is already EPSG:4326, but this handles any CRS)
    if src_crs and str(src_crs) != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)
        log.info("  ↳ Reprojected to EPSG:4326 (WGS-84)")
    else:
        log.info("  ↳ Already in EPSG:4326")

    return gdf


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  GeoJSON FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════

def to_geojson(gdf: gpd.GeoDataFrame) -> dict:
    """
    Convert a GeoDataFrame to a standard GeoJSON FeatureCollection dict.

    The output conforms to RFC 7946 and is ready for POST-ing.
    """
    geojson_str = gdf.to_json()          # Serialise to JSON string
    geojson     = json.loads(geojson_str) # Parse back to dict for requests

    feature_count = len(geojson.get("features", []))
    log.info("GeoJSON FeatureCollection with %d feature(s)", feature_count)
    return geojson


# ═══════════════════════════════════════════════════════════════════════════════
# 8.  WEBHOOK  –  FIRE DATA TO THE NODE.JS BACKEND
# ═══════════════════════════════════════════════════════════════════════════════

def post_to_backend(
    geojson: dict,
    url: str = WEBHOOK_URL,
    source_event: str = "unknown",
) -> bool:
    """
    POST the GeoJSON FeatureCollection to the ResQ backend.

    The backend expects a GeoJSON FeatureCollection with an optional
    `source_event` field identifying which SEN1FLOODS11 chip was used.

    Parameters
    ----------
    geojson : dict
        A valid GeoJSON FeatureCollection.
    url : str
        The webhook endpoint (default: localhost:5000/api/hazards).
    source_event : str
        Identifier for the SAR source (e.g. "India_698338").

    Returns
    -------
    success : bool
        True if the server responded with 2xx.
    """
    # Inject source_event metadata into the FeatureCollection
    # (not part of GeoJSON spec, but the backend reads it)
    payload = {**geojson, "source_event": source_event}

    n_features = len(payload.get("features", []))
    payload_mb = len(json.dumps(payload)) / (1024 * 1024)
    log.info("POSTing %d features (%.1f MB) to %s …", n_features, payload_mb, url)

    try:
        response = requests.post(
            url,
            json=payload,          # Sets Content-Type: application/json
            timeout=120,           # Large payloads need more time
        )
        response.raise_for_status()
        log.info("  ✓ Server responded %d: %s", response.status_code, response.text[:300])
        return True

    except requests.ConnectionError:
        log.error("  ✗ Connection refused — is the backend running at %s ?", url)
        return False

    except requests.Timeout:
        log.error("  ✗ Request timed out after 120 s")
        return False

    except requests.HTTPError as exc:
        log.error("  ✗ HTTP error: %s", exc)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 9.  ORCHESTRATION  –  FULL PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline(
    sar_path: str,
    dem_path: str | None    = None,
    webhook_url: str        = WEBHOOK_URL,
    dilation_px: int        = DILATION_RADIUS_PX,
    elevation_buffer: float = ELEVATION_BUFFER_M,
) -> dict | None:
    """
    Execute the full ResQ flood detection pipeline end-to-end.

    Produces **two** GeoJSON polygon layers:
      • flood_current  – regions currently under water (Otsu detection)
      • flood_spread   – regions where water may expand next (DEM-gated
                         morphological dilation, excluding current flood)

    Parameters
    ----------
    sar_path : str
        File path to the SAR GeoTIFF (.tif).  Can be a SEN1FLOODS11
        chip (2-band VV+VH) or any single-band SAR backscatter raster.
    dem_path : str | None
        File path to the matching DEM GeoTIFF (.tif).
        If None, a synthetic DEM will be generated from the SAR data.
    webhook_url : str
        Backend endpoint to POST results to.
    dilation_px : int
        Morphological dilation radius for spread prediction.
    elevation_buffer : float
        DEM elevation tolerance (metres) for spread constraint.

    Returns
    -------
    combined_geojson : dict | None
        A single GeoJSON FeatureCollection containing features from both
        layers, each tagged with its hazard_type.  None on failure.
    """
    log.info("=" * 72)
    log.info("ResQ  ·  Flood Detection Pipeline  ·  START")
    log.info("=" * 72)

    # ── 1. Ingest SAR ────────────────────────────────────────────────────
    #   Try loading as multi-band SEN1FLOODS11 chip first (VV = band 1).
    #   Fall back to single-band for generic SAR.
    try:
        with rasterio.open(sar_path) as probe:
            n_bands = probe.count
    except Exception as e:
        log.error("Cannot open SAR file: %s — %s", sar_path, e)
        return None

    if n_bands >= 2:
        # SEN1FLOODS11 format:  Band 1 = VV,  Band 2 = VH
        log.info("Detected multi-band SAR (%d bands) — using Band 1 (VV)", n_bands)
        sar_data, sar_meta = load_sar(sar_path, band=1)
    else:
        log.info("Single-band SAR detected")
        sar_data, sar_meta = load_raster(sar_path)

    # ── 2. Load or generate DEM ──────────────────────────────────────────
    if dem_path and os.path.exists(dem_path):
        dem_data, dem_meta = load_raster(dem_path)
        # Sanity check: the two rasters must have matching dimensions
        if sar_data.shape != dem_data.shape:
            log.error(
                "Shape mismatch!  SAR=%s  DEM=%s  — aborting.",
                sar_data.shape, dem_data.shape,
            )
            return None
    else:
        # No DEM provided → synthesise one from SAR backscatter
        log.info("No DEM file provided — generating synthetic DEM from SAR")
        dem_output = str(Path(sar_path).parent / "synthetic_dem.tif")
        dem_data, dem_meta = generate_dem_from_sar(sar_data, sar_meta, dem_output)

    # ── 3. Detect current flood (Otsu) ───────────────────────────────────
    water_mask = detect_water_otsu(sar_data, sar_meta["nodata"])

    # ── 4. Predict spread (morphology + DEM) ─────────────────────────────
    #   Returns TWO masks:
    #     full_mask    = current flood + predicted expansion
    #     spread_only  = ONLY the predicted expansion ring
    _full_mask, spread_only_mask = predict_flood_spread(
        water_mask, dem_data,
        dilation_px=dilation_px,
        elev_buffer=elevation_buffer,
    )

    # ── 5. Vectorise – TWO separate layers ───────────────────────────────
    transform = sar_meta["transform"]
    src_crs   = sar_meta["crs"]

    #  Layer 1 :  Current flood (from Otsu)
    gdf_current = vectorise_mask(
        water_mask, transform, src_crs, hazard_type="flood_current",
    )
    #  Layer 2 :  Predicted spread zone (expansion ring only)
    gdf_spread = vectorise_mask(
        spread_only_mask, transform, src_crs, hazard_type="flood_spread",
    )

    # ── 6. Log layer stats ───────────────────────────────────────────────
    log.info(
        "Layer summary  →  flood_current: %d polygon(s)  |  flood_spread: %d polygon(s)",
        len(gdf_current), len(gdf_spread),
    )

    if gdf_current.empty and gdf_spread.empty:
        log.warning("No flood features to send — pipeline complete (no data)")
        return None

    # ── 7. Format GeoJSON – one per layer + combined ─────────────────────
    geojson_current = to_geojson(gdf_current) if not gdf_current.empty else None
    geojson_spread  = to_geojson(gdf_spread)  if not gdf_spread.empty  else None

    # Combined FeatureCollection merges both layers so the backend gets
    # everything in a single POST.  Each feature's `hazard_type` property
    # tells the frontend how to render it (e.g. red vs. orange).
    gdf_combined = gpd.GeoDataFrame(
        pd.concat([gdf_current, gdf_spread], ignore_index=True),
        crs="EPSG:4326",
    )
    combined_geojson = to_geojson(gdf_combined)

    # ── 8. Fire webhook (combined payload) ───────────────────────────────
    #   Extract source event name from the SAR filename (e.g. "India_698338")
    sar_stem = Path(sar_path).stem                  # "India_698338_S1Hand"
    source_event = sar_stem.replace("_S1Hand", "")  # "India_698338"
    post_to_backend(combined_geojson, url=webhook_url, source_event=source_event)

    # ── 9. Save locally for debugging (one file per layer + combined) ────
    base = Path(sar_path).parent

    if geojson_current:
        p = base / "flood_current.geojson"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(geojson_current, f, indent=2)
        log.info("Saved  →  %s  (%d features)", p, len(geojson_current["features"]))

    if geojson_spread:
        p = base / "flood_spread.geojson"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(geojson_spread, f, indent=2)
        log.info("Saved  →  %s  (%d features)", p, len(geojson_spread["features"]))

    p = base / "flood_combined.geojson"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(combined_geojson, f, indent=2)
    log.info("Saved  →  %s  (%d features)", p, len(combined_geojson["features"]))

    log.info("=" * 72)
    log.info("ResQ  ·  Pipeline  ·  COMPLETE")
    log.info("=" * 72)

    return combined_geojson


# ═══════════════════════════════════════════════════════════════════════════════
# 10.  AVAILABLE CHIPS  (helper to list what's available)
# ═══════════════════════════════════════════════════════════════════════════════

def list_available_chips():
    """Print a table of pre-configured SEN1FLOODS11 chips."""
    print("\n  Available SEN1FLOODS11 chips:")
    print("  " + "─" * 55)
    for i, (event, chip_id, desc) in enumerate(SAMPLE_CHIPS):
        tag = " ← default" if i == 0 else ""
        print(f"    [{i:2d}]  {event}_{chip_id:>10s}   {desc}{tag}")
    print("  " + "─" * 55)
    print()

# ═══════════════════════════════════════════════════════════════════════════════
# 11.  DATASET FETCHER
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_dataset(limit: int = 50, split: str = "train"):
    """
    Download actual SEN1FLOODS11 S1Hand and LabelHand images for U-Net training.
    """
    url = f"https://storage.googleapis.com/sen1floods11/v1.1/splits/flood_handlabeled/flood_{split}_data.csv"
    log.info("Fetching dataset split: %s from %s", split, url)
    df = pd.read_csv(url, header=None)
    
    # Workspace root data dir
    base_dir = Path(__file__).parent.parent / "data"
    img_dir = base_dir / "images"
    mask_dir = base_dir / "masks"
    img_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    
    pairs = df.values.tolist()
    if limit:
        pairs = pairs[:limit]
        
    log.info("Downloading %d pairs...", len(pairs))
    
    s1_base = f"{GCS_BASE}/v1.1/data/flood_events/HandLabeled/S1Hand"
    label_base = f"{GCS_BASE}/v1.1/data/flood_events/HandLabeled/LabelHand"
    
    for i, row in enumerate(pairs):
        s1_file = row[0]
        label_file = row[1] if len(row) > 1 else s1_file.replace("S1Hand", "LabelHand")
        
        s1_url = f"{s1_base}/{s1_file}"
        label_url = f"{label_base}/{label_file}"
        
        s1_local = img_dir / s1_file
        label_local = mask_dir / label_file
        
        if not s1_local.exists():
            log.info("[%d/%d] Downloading %s", i+1, len(pairs), s1_file)
            resp = requests.get(s1_url)
            resp.raise_for_status()
            s1_local.write_bytes(resp.content)
            
        if not label_local.exists():
            log.info("[%d/%d] Downloading %s", i+1, len(pairs), label_file)
            resp = requests.get(label_url)
            resp.raise_for_status()
            label_local.write_bytes(resp.content)
            
    log.info("Finished downloading %d pairs to %s and %s", len(pairs), img_dir, mask_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# 11.  __main__  –  DEMO / TEST ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Quick-start test using real SEN1FLOODS11 satellite data.

    Usage:
        python flood_detector.py                          # downloads default India chip
        python flood_detector.py --list                   # show available chips
        python flood_detector.py --chip 3                 # use chip #3 from the list
        python flood_detector.py --event India --id 698338    # specify event + chip ID
        python flood_detector.py sar.tif                  # local SAR file (auto DEM)
        python flood_detector.py sar.tif dem.tif          # local SAR + DEM files
        python flood_detector.py sar.tif dem.tif <url>    # local files + custom webhook
    """

    import argparse

    parser = argparse.ArgumentParser(
        description="ResQ Flood Detector — SEN1FLOODS11 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true",
                        help="List available SEN1FLOODS11 chips and exit")
    parser.add_argument("--chip", type=int, default=None,
                        help="Index of a pre-configured chip (see --list)")
    parser.add_argument("--event", type=str, default=None,
                        help="SEN1FLOODS11 event name (e.g. 'India', 'Pakistan')")
    parser.add_argument("--id", type=str, default=None, dest="chip_id",
                        help="SEN1FLOODS11 chip ID (e.g. '698338')")
    parser.add_argument("--webhook", type=str, default=WEBHOOK_URL,
                        help="Backend webhook URL")
    parser.add_argument("sar_file", nargs="?", default=None,
                        help="Path to local SAR .tif (overrides SEN1FLOODS11)")
    parser.add_argument("dem_file", nargs="?", default=None,
                        help="Path to local DEM .tif (optional)")
    parser.add_argument("--download-dataset", action="store_true",
                        help="Download actual SEN1FLOODS11 dataset and exit")
    parser.add_argument("--limit", type=int, default=50,
                        help="Limit number of dataset pairs to download")

    args = parser.parse_args()

    # ── List mode ────────────────────────────────────────────────────────
    if args.list:
        list_available_chips()
        sys.exit(0)

    # ── Dataset Download mode ────────────────────────────────────────────
    if args.download_dataset:
        fetch_dataset(limit=args.limit)
        sys.exit(0)

    # ── Determine SAR source ─────────────────────────────────────────────
    sar_file = args.sar_file
    dem_file = args.dem_file
    webhook  = args.webhook

    if sar_file is None:
        # No local file — download from SEN1FLOODS11
        if args.event and args.chip_id:
            event, chip_id = args.event, args.chip_id
            desc = f"{event}_{chip_id}"
        elif args.chip is not None:
            if 0 <= args.chip < len(SAMPLE_CHIPS):
                event, chip_id, desc = SAMPLE_CHIPS[args.chip]
            else:
                log.error("Chip index %d out of range (0–%d). Use --list.",
                          args.chip, len(SAMPLE_CHIPS) - 1)
                sys.exit(1)
        else:
            # Default chip
            event, chip_id, desc = DEFAULT_CHIP

        log.info("Selected SEN1FLOODS11 chip: %s_%s  (%s)", event, chip_id, desc)
        sar_file = download_s1_chip(event, chip_id)
        # DEM will be auto-generated inside run_pipeline

    log.info("SAR file : %s", sar_file)
    log.info("DEM file : %s", dem_file or "(auto-generate)")
    log.info("Webhook  : %s", webhook)

    # ── Run the full pipeline ────────────────────────────────────────────
    result = run_pipeline(
        sar_path=sar_file,
        dem_path=dem_file,
        webhook_url=webhook,
    )

    if result:
        # Count features by hazard_type for a clear summary
        features = result.get("features", [])
        n_current = sum(1 for f in features if f["properties"].get("hazard_type") == "flood_current")
        n_spread  = sum(1 for f in features if f["properties"].get("hazard_type") == "flood_spread")
        print(f"\n✓ Pipeline succeeded — dispatched {len(features)} feature(s):")
        print(f"    • flood_current : {n_current} polygon(s)  (currently flooded)")
        print(f"    • flood_spread  : {n_spread} polygon(s)  (predicted expansion)")
    else:
        print("\n✗ Pipeline produced no output. Check logs above.")
