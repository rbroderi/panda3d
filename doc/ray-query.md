# Ray queries in the Vulkan renderer

Status: first slice, on branch `ray-query` (off `glass-accord-vulkan`).
Written 2026-10-30.

## Goal

Let a Panda application trace rays against its own scene from ordinary
shaders, so it can add shadows and bounced light from moving, short-lived
lights (fires, blasts, engine glow, lamps) on top of baked lighting.
The first users are fragment shaders (shadow rays to a point light) and
compute shaders (probe or one-bounce passes).  Ray tracing *pipelines*
(raygen/closest-hit shaders and shader binding tables) are out of scope:
ray queries from existing stages cover what is needed, with less API.

## Hardware

The target is a Radeon 780M (RDNA3 iGPU), driver 25.20.24.19, Vulkan 1.4.325.
`vulkaninfo` shows:

| | |
|---|---|
| VK_KHR_acceleration_structure | rev 13: `accelerationStructure`, indirect build, capture/replay; **no host commands** |
| VK_KHR_ray_query | `rayQuery` |
| VK_KHR_ray_tracing_pipeline, _maintenance1, _position_fetch | present (unused) |
| VK_KHR_deferred_host_operations, buffer device address | present |
| maxGeometryCount / maxInstanceCount | 16 777 216 |
| maxPrimitiveCount | 536 870 912 |
| minAccelerationStructureScratchOffsetAlignment | 256 |

No host commands means every build runs on the GPU, in a command buffer.

## API

Two new classes in `gobj`, both plain data on the CPU side:

```python
mesh = RayTraceMesh("crate")          # bottom-level structure (BLAS)
mesh.add_geom(geom, transform)        # copies its triangles, returns geometry index

scene = RayTraceScene("world")        # top-level structure (TLAS); a ShaderBuffer
i = scene.add_instance(mesh, np.get_mat(render), mask=0xff, custom_index=0)
scene.set_instance_transform(i, mat)  # cheap; marks the scene for a rebuild
node.set_shader_input("scene", scene)
```

```glsl
#version 460
#extension GL_EXT_ray_query : require
uniform accelerationStructureEXT scene;
...
rayQueryEXT q;
rayQueryInitializeEXT(q, scene, gl_RayFlagsTerminateOnFirstHitEXT, 0xFF,
                      origin, 0.0, dir, dist);
while (rayQueryProceedEXT(q)) {}
bool hit = rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT;
```

Choices:

- **A mesh is a set of Geoms, a scene a set of placed meshes.**  This is
  Vulkan's two levels as they are.  Instancing a mesh (the same building
  model many times, a ship class) costs one BLAS.  A helper that walks a
  NodePath's GeomNodes into meshes and instances belongs to the
  application for now (the game's `ray_scene.py`), because gobj cannot see
  pgraph; a `NodePath`-level helper could go in pgraph later.
- **Triangles are copied on `add_geom`.**  The mesh owns float3 positions
  and uint32 indices; each Geom becomes one geometry (so a hit's geometry
  index says which Geom).  Copying avoids touching Panda's vertex buffers
  (their usage flags, the munger's formats, animation) and lets the GSG
  build from any Geom, munged or not.  The cost is CPU memory and an upload
  per build; static voxel buildings and terrain are built once.
- **`RayTraceScene` derives from `ShaderBuffer`.**  So it reuses
  `ShaderInput`'s buffer path, `ShaderBufferBinding`, `prepare_now` and
  release with no new input type.  A shader parameter of the new
  `ShaderType::AccelerationStructure` binds through `ShaderBufferBinding`
  and the Vulkan shader context writes a
  `VK_DESCRIPTOR_TYPE_ACCELERATION_STRUCTURE_KHR` descriptor.  Passing a
  plain ShaderBuffer there is reported; passing nothing gives a null
  descriptor (robustness2 `nullDescriptor`), which every ray misses, so a
  shader can be shared by scenes that have no structure.
- **Rebuilding, not refitting.**  Any change to a scene's instances bumps an
  `UpdateSeq`; the next use builds a *new* TLAS and queues the old one for
  destruction when the frame using it has finished.  No write-after-read
  hazard with frames in flight, and no barrier that waits on earlier work.
  A TLAS over a few thousand instances builds in well under a millisecond.
- **Thread safety.**  The scene's instance list is under a `LightMutex`;
  the GSG copies it under the lock when building, so the App thread can
  move instances while Draw builds (`threading-model Cull/Draw`).

Meshes changed after first use are rebuilt the next time a scene using them
is rebuilt (a changed BLAS changes its address, so its TLAS needs a rebuild
anyway).

## Vulkan implementation

- **Device.**  `VulkanGraphicsPipe` checks for the extensions and the
  `rayQuery`, `accelerationStructure` and `bufferDeviceAddress` features.
  The GSG enables them (config `vulkan-ray-query`, default true), plus
  VK_KHR_deferred_host_operations which the AS extension requires.
- **Memory.**  With ray queries on, every memory page is allocated with
  `VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT`, so build inputs, scratch and AS
  storage can come from Panda's normal page allocator.
- **Builds** are recorded into the GSG's transfer command buffer, which is
  submitted before the frame's render command buffer, outside any dynamic
  rendering instance.  Descriptor writes happen while drawing; that is
  where `use_ray_trace_scene()` is called, and it records the build then.
  - BLAS: all meshes needing a build go in one `vkCmdBuildAccelerationStructuresKHR`,
    from a host-visible input buffer freed after the frame; then a barrier
    (AS build write -> AS build read).
  - TLAS: instances written to a host-visible buffer (Panda's row-vector
    matrices transposed into `VkTransformMatrixKHR`), built, then a barrier
    (AS build write -> all commands, AS read).
  - Scratch buffers are per build, aligned to the device's
    `minAccelerationStructureScratchOffsetAlignment`, freed after the frame.
- **Lifetime.**  The GSG keeps a `PT(RayTraceMesh)` -> BLAS map.  When the
  GSG holds the last reference, the BLAS is destroyed (checked on each
  scene build).  The TLAS lives in the scene's `VulkanBufferContext`.
- **Shaders.**  glslang already compiles `GL_EXT_ray_query` under Panda's
  OpenGL-client, SPIR-V 1.0 settings (`#version 460` needed), and the module
  validates for Vulkan 1.3.  Panda's SPIR-V reflection learns
  `OpTypeAccelerationStructureKHR` (as the new ShaderType) and
  `OpTypeRayQueryKHR` (an untyped local).

## Test and measurements

`samples/ray-query/shadows.py` (run it with `run.ps1` from this checkout's
build; `-Validate` turns on the Khronos layer with synchronization checks):

- `--check` renders 24 voxel boxes on a ground plane from above under a
  point light, one shadow ray per pixel, and compares every second ground
  pixel with a CPU ray-box test: 1 of 60 085 pixels differs (an edge).
  Validation: 0 messages.
- 300 frames with all boxes moving (the TLAS rebuilt every frame):
  validation 0 messages.
- `--bench` alternates settings in one process (frame times drift too much
  between runs on the laptop).  1600x1000 window, Radeon 780M, frames
  CPU-bound at ~2.5 ms:

  | | median frame |
  |---|---|
  | no rays | 2.4-2.7 ms |
  | 1 shadow ray per pixel | +0.05-0.3 ms |
  | 4 rays per pixel | +0.6 ms |
  | 16 rays per pixel | +7 ms |
  | TLAS of 2000 instances rebuilt every frame | +1.4 ms (after 2.2 ms of Python moving them) |
  | TLAS of 10 000 instances rebuilt every frame | +7 ms (after 9.8 ms of Python) |

  The ray costs are for a trivial scene (25 boxes); deeper BLAS and
  incoherent rays will cost more.  The rebuild cost is mostly CPU: copying
  the instance list, allocating the buffers, writing the instances.

## First use: Glass Accord's colony view

The game's shot lights (fires, blasts, guns: up to 8 point lights, no
shadows before) now trace one shadow ray per light per lit fragment, in
the surface, land and debris shaders, against a RayTraceScene of the
colony's buildings and ground (one RayTraceMesh per Geom, one instance per
GeomNode; 13 buildings + ground = 39 instances, 91 472 triangles, built in
0.6 ms of Python plus the GPU build once).  Same-session A/B on the 780M at
1920x1200, frames alternating traced/untraced:

| lights near the buildings | untraced | traced |
|---|---|---|
| 4 (a ring round the HQ) | 24.3 ms | 25.9 ms (+1.6) |
| 8 (18 m reach, 25 power) | 22.3-24.0 ms | 24.8-27.4 ms (+2.5-3.5) |

Validation with sync checks over the run: no ray-query messages.  (Each
`save_screenshot` of the window leaves its image in TRANSFER_SRC layout at
present: an existing readback bug, not this work.)

## Second use: one bounce into the colony's probes

Engine additions for it:

- **Position fetch.**  Where VK_KHR_ray_tracing_position_fetch is present
  (the 780M has it) it is enabled and meshes are built with
  `ALLOW_DATA_ACCESS`, so a shader reads a hit triangle's corners
  (`rayQueryGetIntersectionTriangleVertexPositionsEXT`) for its normal.
- **Ray queries in compute shaders** work through the same descriptor path
  (`samples/ray-query/compute.py`: 16 384 rays, distance, fetched normal and
  instance index all match a CPU reference).
- **Compute dispatch inside a frame.**  A `ComputeNode` drawn in a scene
  used to dispatch inside the window's dynamic rendering pass, which Vulkan
  forbids.  The GSG now ends the pass, dispatches, and resumes it with
  LOAD (attachments are always stored).  This matters for cost:
  `GraphicsEngine::dispatch_compute` from the App thread waits for the draw
  thread, which cost the game ~16 ms a frame; a ComputeNode in its own
  display region (sorted first) costs the App thread 0.1 ms.

The game's pass (`ray_bounce.py`): for each probe of the baked 2 m grid
(66x66x10 here) within reach of a shot light, 4 cosine-weighted rays per
side (24 a probe), closest hit, normal from the fetched corners (a back
face marks the probe as inside), the shot lights' direct light at the hit
(one shadow ray each) times the instance's albedo (packed in its custom
index).  A quarter of the probes a frame.  The shaders read the volume
like the baked probes and add `diffuse * bounce`.

Same-session A/B, 4 lights round the HQ, 1920x1200: none 23.0 ms,
shadows 24.0 ms, shadows + bounce 26.7 ms.  Validation: no messages from
the bounce pass, the compute dispatch or the resumed pass.

Known: under the validation layer, a process that leaves Panda's global
GraphicsEngine to close the GSG at exit aborts in the layer
(`vkDeviceWaitIdle` after the layer is torn down); and an offscreen
buffer is destroyed at exit while its last frame is in flight (two
VUID-vkDestroyImage-image-01000).  Both are older than this work.

## Toward live global illumination

Measured so far, a shadow ray costs well under a millisecond per million
pixels, and a few thousand instances rebuild in about a millisecond.  So:

1. **One-bounce light from the dynamic lights into the colony's probe
   grid** is the cheap route to "blasts light up nearby walls and ground".
   The game already reads a 2 m six-sided probe grid in its shaders.  A
   compute pass each frame updates the probes near active lights: each
   probe casts N rays (16-32) against the scene, and at each hit adds the
   shot lights' direct light there (one shadow ray per light) times the
   hit's albedo.  32x32x16 probes x 16 rays = 260k rays a frame, a small
   fraction of the per-pixel shadow cost.  Needs: hit normals (the 780M has
   VK_KHR_ray_tracing_position_fetch, or per-geometry normal buffers) and
   albedo (a per-instance material table indexed by the instance custom
   index), plus ray queries in compute shaders (same descriptor path as
   fragment shaders; not tested yet).
2. **Per-pixel one-bounce** (screen-space-sized ray budget, 1-2 rays a
   pixel, temporal accumulation and a denoiser) gives sharper contact
   bounce but costs several ms on this GPU; worth it only after 1.
3. Engine work for both: TLAS refit (`ALLOW_UPDATE`) for many moving
   instances, `get_supports_ray_query()` on the GSG, a NodePath helper, and
   building from Panda's vertex buffers for big meshes.

## Not done / next

1. Pipelined (per-frame) TLAS updates with
   `ALLOW_UPDATE` + `MODE_UPDATE` for scenes whose instances move every
   frame, with a ring of structures per frame in flight; and BLAS
   compaction for big static meshes.
2. Build from Panda's own vertex buffers (needs `SHADER_DEVICE_ADDRESS`
   and `AS_BUILD_INPUT` usage on them) to skip the CPU copy.
3. A NodePath helper (`RayTraceScene.add_node(np)` in pgraph or a Python
   extension) that flattens GeomNodes into meshes and instances.
4. `GraphicsStateGuardian::get_supports_ray_query()` so applications can
   choose a path without knowing the GSG class.
5. The OpenGL backend: GL_EXT_ray_query does not exist there; nothing to do.
6. Hit attributes beyond the hit itself (barycentrics, primitive and
   instance indices) already work through GLSL; reading the hit's material
   needs per-geometry buffers the application provides (SSBOs indexed by
   `rayQueryGetIntersectionInstanceCustomIndexEXT`).
