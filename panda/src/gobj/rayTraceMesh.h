/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceMesh.h
 * @author rbroderi
 * @date 2026-10-30
 */

#ifndef RAYTRACEMESH_H
#define RAYTRACEMESH_H

#include "pandabase.h"
#include "typedReferenceCount.h"
#include "namable.h"
#include "geom.h"
#include "luse.h"
#include "updateSeq.h"
#include "pvector.h"

/**
 * A set of triangles that rays can be traced against: what Vulkan calls a
 * bottom-level acceleration structure.  The triangles are copied out of the
 * Geoms when they are added, in the mesh's own space; place the mesh in the
 * world with a RayTraceScene, which may hold any number of instances of it.
 *
 * The GPU structure is built the first time a scene using the mesh is used,
 * and rebuilt after the mesh is changed.
 *
 * This is only supported by the Vulkan renderer, on hardware that supports
 * ray queries.
 */
class EXPCL_PANDA_GOBJ RayTraceMesh : public TypedReferenceCount, public Namable {
PUBLISHED:
  explicit RayTraceMesh(const std::string &name = std::string());

  int add_geom(const Geom *geom, const LMatrix4 &transform = LMatrix4::ident_mat(),
               Thread *current_thread = Thread::get_current_thread());
  void clear();

  INLINE int get_num_geoms() const;
  INLINE int get_num_vertices() const;
  INLINE int get_num_triangles() const;

  MAKE_PROPERTY(num_geoms, get_num_geoms);
  MAKE_PROPERTY(num_vertices, get_num_vertices);
  MAKE_PROPERTY(num_triangles, get_num_triangles);

public:
  // One per add_geom() call; each becomes its own geometry in the structure,
  // so that shaders can tell them apart with the geometry index.
  struct GeomRange {
    uint32_t _first_vertex;
    uint32_t _num_vertices;
    uint32_t _first_index;
    uint32_t _num_triangles;
  };

  INLINE const pvector<LVecBase3f> &get_vertices() const;
  INLINE const pvector<uint32_t> &get_indices() const;
  INLINE const pvector<GeomRange> &get_ranges() const;
  INLINE UpdateSeq get_modified() const;

private:
  pvector<LVecBase3f> _vertices;
  pvector<uint32_t> _indices;
  pvector<GeomRange> _ranges;
  UpdateSeq _modified;

public:
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    TypedReferenceCount::init_type();
    Namable::init_type();
    register_type(_type_handle, "RayTraceMesh",
                  TypedReferenceCount::get_class_type(),
                  Namable::get_class_type());
  }
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}

private:
  static TypeHandle _type_handle;
};

#include "rayTraceMesh.I"

#endif
