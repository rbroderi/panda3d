/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceMesh.I
 * @author rbroderi
 * @date 2026-10-30
 */

/**
 * Returns the number of Geoms added to the mesh.
 */
INLINE int RayTraceMesh::
get_num_geoms() const {
  return (int)_ranges.size();
}

/**
 * Returns the number of vertices in the mesh, referenced Geoms' included.
 */
INLINE int RayTraceMesh::
get_num_vertices() const {
  return _num_vertices;
}

/**
 * Returns the number of triangles in the mesh, referenced Geoms' included.
 */
INLINE int RayTraceMesh::
get_num_triangles() const {
  return _num_triangles;
}

/**
 * Returns true if any of the mesh's Geoms is animated: update_animation()
 * poses it again.
 */
INLINE bool RayTraceMesh::
is_animated() const {
  return _num_animated > 0;
}

/**
 * Returns how many of the mesh's Geoms are built from their own buffers on
 * the GPU (the rest are copied).
 */
INLINE int RayTraceMesh::
get_num_referenced_geoms() const {
  return _num_referenced;
}

/**
 * Returns the copied and posed Geoms' vertex positions, in the mesh's own
 * space.
 */
INLINE const pvector<LVecBase3f> &RayTraceMesh::
get_vertices() const {
  return _vertices;
}

/**
 * Returns three vertex indices per copied or posed triangle.  Indices are
 * relative to the first vertex of the triangle's GeomRange.
 */
INLINE const pvector<uint32_t> &RayTraceMesh::
get_indices() const {
  return _indices;
}

/**
 * Returns the vertex and triangle ranges, one per Geom.
 */
INLINE const pvector<RayTraceMesh::GeomRange> &RayTraceMesh::
get_ranges() const {
  return _ranges;
}

/**
 * Returns a sequence number that changes whenever the mesh is changed,
 * animation included.
 */
INLINE UpdateSeq RayTraceMesh::
get_modified() const {
  return _modified;
}

/**
 * Returns a sequence number that changes whenever the mesh's geometry is
 * added or removed, but not when it is only posed again: while it is the
 * same, the GPU structure can be refitted instead of rebuilt.
 */
INLINE UpdateSeq RayTraceMesh::
get_layout_modified() const {
  return _layout_modified;
}

/**
 * Returns a number that changes whenever any mesh is changed.
 */
INLINE unsigned int RayTraceMesh::
get_any_modified() {
  return _any_modified.load(std::memory_order_relaxed);
}

/**
 * Returns the lock held while the mesh is changed.  A renderer holds it while
 * it reads the mesh's ranges, vertices and indices.
 */
INLINE LightMutex &RayTraceMesh::
get_lock() const {
  return _lock;
}
