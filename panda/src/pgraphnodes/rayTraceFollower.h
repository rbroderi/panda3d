/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceFollower.h
 * @author rbroderi
 * @date 2026-11-03
 */

#ifndef RAYTRACEFOLLOWER_H
#define RAYTRACEFOLLOWER_H

#include "pandabase.h"
#include "typedReferenceCount.h"
#include "rayTraceScene.h"
#include "nodePath.h"
#include "transformState.h"
#include "pvector.h"

/**
 * Keeps a RayTraceScene's instances where nodes of the scene graph are: each
 * instance given with add_instance() follows its node, placed relative to the
 * follower's relative_to node (usually render, the space the shader traces
 * rays in).
 *
 * update() walks the nodes and moves only the instances whose nodes moved,
 * so that the scene is refitted only when something did; a node whose net
 * transform (and relative_to's) is the very TransformState it was last time
 * is passed over without computing its matrix.
 */
class EXPCL_PANDA_PGRAPHNODES RayTraceFollower : public TypedReferenceCount {
PUBLISHED:
  explicit RayTraceFollower(RayTraceScene *scene,
                            const NodePath &relative_to = NodePath());

  INLINE RayTraceScene *get_scene() const;
  INLINE const NodePath &get_relative_to() const;
  MAKE_PROPERTY(scene, get_scene);
  MAKE_PROPERTY(relative_to, get_relative_to);

  void add_instance(int n, const NodePath &node);
  void clear();

  INLINE int get_num_instances() const;
  MAKE_PROPERTY(num_instances, get_num_instances);

  int update(Thread *current_thread = Thread::get_current_thread());

private:
  struct Follow {
    int _instance;
    NodePath _node;
    CPT(TransformState) _net;
    LMatrix4f _transform;
  };

  PT(RayTraceScene) _scene;
  NodePath _relative_to;
  CPT(TransformState) _relative_net;
  pvector<Follow> _follows;

public:
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    TypedReferenceCount::init_type();
    register_type(_type_handle, "RayTraceFollower",
                  TypedReferenceCount::get_class_type());
  }
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}

private:
  static TypeHandle _type_handle;
};

#include "rayTraceFollower.I"

#endif
