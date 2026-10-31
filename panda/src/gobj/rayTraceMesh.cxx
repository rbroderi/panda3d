/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceMesh.cxx
 * @author rbroderi
 * @date 2026-10-30
 */

#include "rayTraceMesh.h"
#include "geomPrimitive.h"
#include "geomVertexReader.h"

TypeHandle RayTraceMesh::_type_handle;

/**
 * Creates an empty mesh.
 */
RayTraceMesh::
RayTraceMesh(const std::string &name) : Namable(name) {
}

/**
 * Copies the triangles of the given Geom into the mesh, transformed by the
 * given matrix.  Points, lines and the Geom's vertex animation are ignored.
 * Returns the index of the new geometry, which a shader sees as the geometry
 * index of a hit, or -1 if the Geom has no vertex column.
 */
int RayTraceMesh::
add_geom(const Geom *geom, const LMatrix4 &transform, Thread *current_thread) {
  nassertr(geom != nullptr, -1);

  CPT(Geom) tris = geom->decompose();
  CPT(GeomVertexData) vdata = tris->get_vertex_data(current_thread);
  if (!vdata->has_column(InternalName::get_vertex())) {
    return -1;
  }

  GeomRange range;
  range._first_vertex = (uint32_t)_vertices.size();
  range._first_index = (uint32_t)_indices.size();

  LMatrix4f mat = LCAST(float, transform);
  GeomVertexReader reader(vdata, InternalName::get_vertex(), current_thread);
  int num_rows = vdata->get_num_rows();
  _vertices.reserve(_vertices.size() + num_rows);
  for (int i = 0; i < num_rows; ++i) {
    LPoint3f point = mat.xform_point(reader.get_data3f());
    _vertices.push_back(point);
  }
  range._num_vertices = (uint32_t)num_rows;

  for (size_t pi = 0; pi < tris->get_num_primitives(); ++pi) {
    CPT(GeomPrimitive) prim = tris->get_primitive(pi);
    if (prim->get_primitive_type() != GeomPrimitive::PT_polygons) {
      continue;
    }
    prim = prim->decompose();
    int num_prims = prim->get_num_primitives();
    for (int ti = 0; ti < num_prims; ++ti) {
      int start = prim->get_primitive_start(ti);
      _indices.push_back((uint32_t)prim->get_vertex(start));
      _indices.push_back((uint32_t)prim->get_vertex(start + 1));
      _indices.push_back((uint32_t)prim->get_vertex(start + 2));
    }
  }
  range._num_triangles = (uint32_t)((_indices.size() - range._first_index) / 3);

  _ranges.push_back(range);
  ++_modified;
  return (int)_ranges.size() - 1;
}

/**
 * Removes all the triangles from the mesh.
 */
void RayTraceMesh::
clear() {
  _vertices.clear();
  _indices.clear();
  _ranges.clear();
  ++_modified;
}
