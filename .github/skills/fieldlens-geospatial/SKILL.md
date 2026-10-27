---
name: fieldlens-geospatial
description: 'Inspect or implement FieldLens geospatial ingestion, CRS/datum transforms, terrain/bathymetry alignment, formation layers, and planar GeoPandas joins. Use for coordinate, spatial-reference and geodata validation; never substitute planar geometry for 3D well analysis.'
license: MIT
metadata:
  upstream-author: K-Dense Inc.
  upstream-revision: 5f2bc0341354fd5590aef76a533ada1e1e5b4e62
---

# FieldLens Geospatial Validation

Adapted from K-Dense's GeoPandas skill. The local procedure is self-contained;
upstream scripts, package pins and optional PostGIS/cloud workflows are not bundled.
[Source and modifications](../../../docs/DEVELOPMENT_SKILLS.md).
[License notice](../../../docs/licenses/k-dense-MIT.txt).

## Workflow

1. Read the approved data/feature spec and inspect only authorized local samples.
   Record source hash, format, parser version, feature IDs, geometry types, extent,
   units, coordinate axes and original CRS. Do not infer a CRS from plausible numbers.
2. Inventory null, empty, invalid, mixed-dimensional and duplicate geometries
   separately. Identify vertical datum/depth reference independently of horizontal
   CRS. Record true/grid/magnetic azimuth and required offsets for well surveys.
3. Use pyproj directly for coordinate transformations when sufficient. Add GeoPandas
   only for actual vector-layer/table operations. `set_crs()` assigns metadata;
   `to_crs()` transforms values. Never use reassignment to disguise a mismatch.
4. Specify coordinate-array order, for example `always_xy=True` where the contract
   is x/y. Check area of use, datum grids and transformation accuracy. Report missing
   grids or ballpark transformations; do not silently accept them or enable downloads.
5. Use a justified projected CRS for planar distances/areas, with explicit unit
   conversion. Geographic degrees and Web Mercator are not general engineering
   measurement coordinates. Detect projection-boundary/antimeridian cases.
6. Treat GeoPandas/Shapely operations as planar: spatial joins ignore Z. Route 3D
   well separation, trajectory interpolation and depth conversion to deterministic
   engineering tools with independent fixtures.
7. State join cardinality and predicate semantics before joins. Audit unmatched
   and multiplied records. Validate repairs/precision changes against the original:
   geometry repair can change type, topology or dimensionality.
8. Align terrain/bathymetry and geological layers with wells in a common physical
   frame, then apply the renderer's local-origin transform. Label interpreted
   surfaces; formation picks alone do not prove a reservoir boundary or volume.
9. Reopen outputs and verify counts, CRS, units, IDs, bounds and evidence locators.
   Test missing CRS/datum, axis swaps, feet/metres, incompatible revisions and
   overlapping XY paths separated in Z.

## Boundaries

No automatic remote GDAL paths, geocoding, grid downloads, geometry "repair" or
PostGIS deployment. A browser screenshot is not coordinate validation. Keep
precise private coordinates out of logs, prompts and third-party services unless
explicitly authorized.
