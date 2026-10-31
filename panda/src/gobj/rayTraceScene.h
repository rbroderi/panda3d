/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceScene.h
 * @author rbroderi
 * @date 2026-10-30
 */

#ifndef RAYTRACESCENE_H
#define RAYTRACESCENE_H

#include "pandabase.h"
#include "shaderBuffer.h"
#include "rayTraceMesh.h"
#include "lightMutex.h"
#include "lightMutexHolder.h"

/**
 * A set of placed RayTraceMesh instances that a shader can trace rays
 * against: what Vulkan calls a top-level acceleration structure.  Pass it to
 * a shader input declared as an accelerationStructureEXT (GLSL with
 * GL_EXT_ray_query) with set_shader_input(), as you would a ShaderBuffer.
 *
 * Instances are placed in whatever space the shader traces rays in, usually
 * the world (render).  Changing them is cheap on the CPU; the GPU structure
 * is rebuilt, the next time a shader uses it, after any change.  This may be
 * done from any thread.
 *
 * This is only supported by the Vulkan renderer, on hardware that supports
 * ray queries.
 */
class EXPCL_PANDA_GOBJ RayTraceScene : public ShaderBuffer {
PUBLISHED:
  explicit RayTraceScene(const std::string &name = std::string());

  int add_instance(RayTraceMesh *mesh,
                   const LMatrix4 &transform = LMatrix4::ident_mat(),
                   unsigned int mask = 0xff, unsigned int custom_index = 0);
  void set_instance_transform(int n, const LMatrix4 &transform);
  void set_instance_mask(int n, unsigned int mask);
  void set_instance_mesh(int n, RayTraceMesh *mesh);
  void clear_instances();

  int get_num_instances() const;
  PT(RayTraceMesh) get_instance_mesh(int n) const;
  LMatrix4 get_instance_transform(int n) const;
  MAKE_PROPERTY(num_instances, get_num_instances);

  virtual void output(std::ostream &out) const;

public:
  struct Instance {
    PT(RayTraceMesh) _mesh;
    LMatrix4f _transform;
    uint32_t _mask;
    uint32_t _custom_index;
  };
  UpdateSeq get_instances(pvector<Instance> &into) const;
  UpdateSeq get_modified() const;

private:
  mutable LightMutex _lock;
  pvector<Instance> _instances;
  UpdateSeq _modified;

public:
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    ShaderBuffer::init_type();
    register_type(_type_handle, "RayTraceScene",
                  ShaderBuffer::get_class_type());
  }

private:
  static TypeHandle _type_handle;
};

#endif
