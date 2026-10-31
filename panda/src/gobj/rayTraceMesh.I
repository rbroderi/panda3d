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
 * Returns the number of vertices in the mesh.
 */
INLINE int RayTraceMesh::
get_num_vertices() const {
  return (int)_vertices.size();
}

/**
 * Returns the number of triangles in the mesh.
 */
INLINE int RayTraceMesh::
get_num_triangles() const {
  return (int)(_indices.size() / 3);
}

/**
 * Returns the vertex positions, in the mesh's own space.
 */
INLINE const pvector<LVecBase3f> &RayTraceMesh::
get_vertices() const {
  return _vertices;
}

/**
 * Returns three vertex indices per triangle.  Indices are relative to the
 * first vertex of the triangle's GeomRange.
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
 * Returns a sequence number that changes whenever the mesh is changed.
 */
INLINE UpdateSeq RayTraceMesh::
get_modified() const {
  return _modified;
}
