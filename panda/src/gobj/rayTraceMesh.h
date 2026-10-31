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
#include "patomic.h"
#include "lightMutex.h"

/**
 * A set of triangles that rays can be traced against: what Vulkan calls a
 * bottom-level acceleration structure.  Place the mesh in the world with a
 * RayTraceScene, which may hold any number of instances of it.
 *
 * A Geom added to it is kept one of three ways:
 *
 * - by reference, if it is static and made of plain triangles with float
 *   vertex positions (and ray-trace-reference-geoms is on, as it is by
 *   default): the structure is built straight from the Geom's own vertex and
 *   index buffers on the GPU, with no copy on the CPU;
 * - posed, if its vertices are animated (skinned, or morphed by sliders):
 *   its triangles are copied as animated now, and again on each
 *   update_animation(), which the structure follows by refitting itself;
 * - copied, otherwise (strips, fans, other position formats): its triangles
 *   are decomposed and copied once.
 *
 * The GPU structure is built the first time a scene using the mesh is used,
 * and rebuilt (or refitted) after the mesh is changed.  Static meshes are
 * compacted once built.
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
  bool update_animation(Thread *current_thread = Thread::get_current_thread());

  INLINE int get_num_geoms() const;
  INLINE int get_num_vertices() const;
  INLINE int get_num_triangles() const;
  INLINE bool is_animated() const;
  INLINE int get_num_referenced_geoms() const;

  MAKE_PROPERTY(num_geoms, get_num_geoms);
  MAKE_PROPERTY(num_vertices, get_num_vertices);
  MAKE_PROPERTY(num_triangles, get_num_triangles);
  MAKE_PROPERTY(animated, is_animated);
  MAKE_PROPERTY(num_referenced_geoms, get_num_referenced_geoms);

public:
  // One per add_geom() call.  A copied or posed one's triangles are in the
  // mesh's vertex and index lists; a referenced one's are its Geom's own.
  struct GeomRange {
    uint32_t _first_vertex = 0;
    uint32_t _num_vertices = 0;
    uint32_t _first_index = 0;
    uint32_t _num_triangles = 0;

    // The Geom it came from, decomposed into triangles: kept when it is
    // referenced or animated (to pose it again).
    CPT(Geom) _geom;
    bool _referenced = false;
    bool _animated = false;

    // A referenced one's transform, applied by the build (the others'
    // vertices are transformed as they are copied).
    LMatrix4f _transform = LMatrix4f::ident_mat();
    bool _identity = true;
  };

  INLINE const pvector<LVecBase3f> &get_vertices() const;
  INLINE const pvector<uint32_t> &get_indices() const;
  INLINE const pvector<GeomRange> &get_ranges() const;
  INLINE UpdateSeq get_modified() const;
  INLINE UpdateSeq get_layout_modified() const;
  INLINE static unsigned int get_any_modified();

  // Held while the mesh is changed; a renderer holds it while it reads the
  // ranges, vertices and indices (which the App thread may be changing).
  INLINE LightMutex &get_lock() const;

private:
  void note_modified(bool layout);
  void pose(GeomRange &range, Thread *current_thread);

private:
  pvector<LVecBase3f> _vertices;
  pvector<uint32_t> _indices;
  pvector<GeomRange> _ranges;
  UpdateSeq _modified;
  UpdateSeq _layout_modified;
  int _num_triangles = 0;
  int _num_vertices = 0;
  int _num_animated = 0;
  int _num_referenced = 0;
  mutable LightMutex _lock;

  // Counts changes to every mesh, so that a scene can tell cheaply whether
  // any of its meshes may have changed.
  static patomic<unsigned int> _any_modified;

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
