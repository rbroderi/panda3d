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
#include "config_gobj.h"
#include "lightMutexHolder.h"
#include "geomPrimitive.h"
#include "geomTriangles.h"
#include "geomVertexReader.h"

TypeHandle RayTraceMesh::_type_handle;
patomic<unsigned int> RayTraceMesh::_any_modified {0};

/**
 * Returns true if the Geom's vertices are moved by animation (a transform
 * blend table or sliders).
 */
static bool
is_animated_data(const GeomVertexData *vdata) {
  return vdata->get_transform_blend_table() != nullptr ||
         vdata->get_slider_table() != nullptr;
}

/**
 * Returns true if a structure can be built straight from the Geom's own
 * buffers: plain (indexed or not) triangles, float vertex positions of at
 * least three components.
 */
static bool
can_reference(const Geom *geom, const GeomVertexData *vdata) {
  if (!ray_trace_reference_geoms) {
    return false;
  }
  // An empty one is copied: as nothing, without an empty buffer to build from.
  if (geom->get_num_primitives() == 0 || vdata->get_num_rows() == 0) {
    return false;
  }
  const GeomVertexColumn *column =
    vdata->get_format()->get_column(InternalName::get_vertex());
  if (column == nullptr ||
      column->get_numeric_type() != GeomEnums::NT_float32 ||
      column->get_num_components() < 3) {
    return false;
  }
  int num_triangles = 0;
  for (size_t pi = 0; pi < geom->get_num_primitives(); ++pi) {
    const GeomPrimitive *prim = geom->get_primitive(pi);
    if (prim->get_type() != GeomTriangles::get_class_type()) {
      return false;
    }
    num_triangles += prim->get_num_primitives();
  }
  return num_triangles > 0;
}

/**
 * Creates an empty mesh.
 */
RayTraceMesh::
RayTraceMesh(const std::string &name) : Namable(name) {
}

/**
 * Adds the triangles of the given Geom to the mesh, transformed by the given
 * matrix: by reference, posed or copied (see the class notes).  Points and
 * lines are ignored.  Returns the index of the new range, or -1 if the Geom
 * has no vertex column.
 */
int RayTraceMesh::
add_geom(const Geom *geom, const LMatrix4 &transform, Thread *current_thread) {
  nassertr(geom != nullptr, -1);

  CPT(GeomVertexData) vdata = geom->get_vertex_data(current_thread);
  if (!vdata->has_column(InternalName::get_vertex())) {
    return -1;
  }

  LightMutexHolder holder(_lock);
  GeomRange range;
  range._transform = LCAST(float, transform);
  range._identity = range._transform.almost_equal(LMatrix4f::ident_mat());

  if (!is_animated_data(vdata) && can_reference(geom, vdata)) {
    // Built from its own buffers: count it, copy nothing.
    range._geom = geom;
    range._referenced = true;
    range._num_vertices = (uint32_t)vdata->get_num_rows();
    for (size_t pi = 0; pi < geom->get_num_primitives(); ++pi) {
      range._num_triangles += (uint32_t)geom->get_primitive(pi)->get_num_primitives();
    }
    ++_num_referenced;
  }
  else {
    CPT(Geom) tris = geom->decompose();
    range._first_vertex = (uint32_t)_vertices.size();
    range._first_index = (uint32_t)_indices.size();
    range._num_vertices = (uint32_t)vdata->get_num_rows();
    _vertices.resize(_vertices.size() + range._num_vertices);

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

    range._geom = tris;
    if (is_animated_data(vdata)) {
      range._animated = true;
      ++_num_animated;
    }
    pose(range, current_thread);
  }

  _num_vertices += (int)range._num_vertices;
  _num_triangles += (int)range._num_triangles;
  _ranges.push_back(std::move(range));
  note_modified(true);
  return (int)_ranges.size() - 1;
}

/**
 * Removes all the triangles from the mesh.
 */
void RayTraceMesh::
clear() {
  LightMutexHolder holder(_lock);
  _vertices.clear();
  _indices.clear();
  _ranges.clear();
  _num_vertices = 0;
  _num_triangles = 0;
  _num_animated = 0;
  _num_referenced = 0;
  note_modified(true);
}

/**
 * Poses the mesh's animated Geoms as their animation stands now: call it
 * each frame the animation moves.  The GPU structure is refitted to the new
 * pose the next time a scene using it is used.  Returns true if the mesh has
 * animated Geoms (and so was changed).
 */
bool RayTraceMesh::
update_animation(Thread *current_thread) {
  LightMutexHolder holder(_lock);
  if (_num_animated == 0) {
    return false;
  }
  for (GeomRange &range : _ranges) {
    if (range._animated) {
      pose(range, current_thread);
    }
  }
  note_modified(false);
  return true;
}

/**
 * Copies a copied or posed range's vertex positions into the vertex list, as
 * its Geom's animation stands now (if it has any), transformed.
 */
void RayTraceMesh::
pose(GeomRange &range, Thread *current_thread) {
  CPT(GeomVertexData) vdata;
  if (range._animated) {
    vdata = range._geom->get_vertex_data(current_thread)->animate_vertices(true, current_thread);
  } else if (range._geom != nullptr) {
    vdata = range._geom->get_vertex_data(current_thread);
  } else {
    return;
  }
  GeomVertexReader reader(vdata, InternalName::get_vertex(), current_thread);
  uint32_t num_rows = std::min((uint32_t)vdata->get_num_rows(), range._num_vertices);
  LVecBase3f *out = &_vertices[range._first_vertex];
  for (uint32_t i = 0; i < num_rows; ++i) {
    out[i] = range._transform.xform_point(reader.get_data3f());
  }
}

/**
 * Notes a change: to the layout (geometry added or removed) or only to the
 * vertices' places.
 */
void RayTraceMesh::
note_modified(bool layout) {
  ++_modified;
  if (layout) {
    ++_layout_modified;
  }
  _any_modified.fetch_add(1, std::memory_order_relaxed);
}
