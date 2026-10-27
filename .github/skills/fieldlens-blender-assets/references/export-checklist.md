# Blender to FieldLens GLB handoff

Companion to [the skill](../SKILL.md). This is a planning/checklist reference,
not an installed exporter, tested command or existing asset schema.

## Command template

After setup and script review, substitute **actual approved absolute paths**:

```text
/absolute/path/to/blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python /absolute/path/to/reviewed_asset_script.py
```

The script and executable do not exist as deliverables of this skill.
Place the error-exit option before the script. Keep the intended output path in
validated parameters; refuse overwrites outside the assigned asset directory.
Capture exit status and logs and check newly produced files, not a stale earlier
export. Fail explicitly on missing outputs, invalid geometry or unmet budgets.

`--disable-autoexec` limits embedded automatic execution; an explicitly supplied
`--python` script still executes with host permissions. Factory startup and
background mode are not security isolation. Never run third-party scripts,
addons or untrusted native files merely because these flags are present.

The authoring script must use the chosen Blender version's supported API and
record its export settings. No generated script may be executed by the application's
Meta agent. The development worker's reviewed script is a different trust boundary.

## Coordinate and identity contract

- glTF uses metres and a right-handed, +Y-up coordinate system. Blender authoring
  is Z-up; choose and verify the exporter's axis conversion once. Do not apply
  another unrecorded 90-degree rotation in the viewer.
- Define the equipment's longitudinal axis, origin/pivot, handedness and local
  attachments in both authoring and exported space. Do not infer equipment forward
  direction from the file format's scene axes.
- Verify dimensions after all modifiers and parent transforms; the Blender UI's
  unit labels and raw local mesh bounds are insufficient. Track negative/nonuniform
  scale and normals explicitly instead of applying every transform blindly.
- Preserve reusable catalog/model identity and stable semantic part keys. Map
  those keys to per-instance IDs when loading; two installations of one GLB must
  not collide. Never rely on Blender's generated `.001` names as authoritative IDs.
- Export only approved non-sensitive custom properties to glTF `extras` when the
  configured exporter supports it, or provide a stable sidecar mapping. Round-trip
  test the mapping; absence must fail validation rather than drop picking/evidence.
  Locators and engineering claims remain in the authoritative data store.

## Acceptance checks

The asset spec supplies actual dimensions, tolerances and runtime budgets before
authoring. Never fill unknown source values with this synthetic calibration data.

| Check | Required result / evidence |
|---|---|
| Synthetic scale/axes calibration | Export a separate 1 m calibration length and three distinguishable axis markers. In the consumer, length is 1 m within an approved tolerance (proposed `1e-5 m` for this synthetic fixture), axis mapping/signs agree, and pivot/attachments match. Do not ship the fixture with equipment |
| Physical geometry | Transformed assembly dimensions/attachments match validated parameters within source-specific tolerances. Generic dimensions are separately labeled and excluded from engineering measurements |
| Topology/normals | No nonfinite coordinates, degenerate faces or unintended inverted normals; open boundaries are documented (for example an open-ended tube), not automatically filled to force watertightness |
| Evaluated export | Intended modifiers/bakes appear; no preview helpers, lights, cameras or unrelated objects leak into the runtime asset |
| Portable materials | Supported PBR materials/textures reproduce acceptably under the viewer's defined lighting/color management; procedural nodes are baked or explicitly rejected |
| GLB resources | Required images/buffers are embedded or explicitly approved local resources; no external network URI or missing texture is accepted |
| Format validation | A locally run pinned glTF validator reports zero errors; warnings are reviewed/dispositioned. Do not upload private assets to an online validator |
| Clean reload | Re-import into a fresh scene, then load through the locked Three.js loader; compare bounds, axes, pivot, part IDs and missing-resource warnings |
| Instance/picking | Two instances have distinct runtime IDs; intended subparts select the correct evidence without duplicated or lost identity |
| Resource budget | Record triangle/vertex/material counts, GLB/texture sizes, draw calls, frame time and memory for the approved fixture; all specified thresholds pass |
| Rebuild | Re-run the reviewed recipe in a clean output directory; semantic IDs, transforms, dimensions and counts agree within specified tolerances. Do not promise byte-identical GLBs without testing |
| History and presentation | Changing as-of selection does not mutate the reusable asset into fabricated historical geometry; generic/exaggerated/unlocated states stay labeled |

If no runtime viewer exists yet, record consumer checks as **unrun**. Do not
label the asset runtime-verified, invent measurements or create a dummy app merely
to turn the checklist green.

## Minimal asset manifest content

The owning feature specifies a concrete format/path. Include:

- Asset/model/variant revision; immutable source/parameter/file hashes.
- Per-attribute evidence class, validation state, original/normalized units and
  document/page/table locators or cited catalog references; missing fields.
- Exact Blender/exporter version, platform, reviewed script revision, modifier/
  bake/compression settings and reproducible commands.
- Authoring/exported axes, pivot, dimensions, tolerances, attachment and part-ID
  mapping; installation identity/placement is supplied separately by source data.
- Source `.blend`, approved textures, runtime `.glb`, previews and reuse terms;
  binary storage/versioning decision before committing any large asset.
- Executed checks/results/limits, unrun consumer tests and residual warnings.
