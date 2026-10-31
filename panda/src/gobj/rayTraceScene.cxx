/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceScene.cxx
 * @author rbroderi
 * @date 2026-10-30
 */

#include "rayTraceScene.h"

TypeHandle RayTraceScene::_type_handle;

/**
 * Creates an empty scene.
 */
RayTraceScene::
RayTraceScene(const std::string &name) :
  ShaderBuffer(name, 0, GeomEnums::UH_dynamic)
{
}

/**
 * Places an instance of the given mesh in the scene, and returns its index.
 * A ray only hits instances whose mask shares a bit with the ray's cull mask.
 * custom_index (24 bits) is what a shader reads as the hit's instance custom
 * index.
 */
int RayTraceScene::
add_instance(RayTraceMesh *mesh, const LMatrix4 &transform,
             unsigned int mask, unsigned int custom_index) {
  nassertr(mesh != nullptr, -1);
  nassertr(custom_index < (1u << 24), -1);

  Instance inst;
  inst._mesh = mesh;
  inst._transform = LCAST(float, transform);
  inst._mask = mask & 0xff;
  inst._custom_index = custom_index;

  LightMutexHolder holder(_lock);
  _instances.push_back(std::move(inst));
  ++_modified;
  ++_layout_modified;
  return (int)_instances.size() - 1;
}

/**
 * Moves the nth instance.
 */
void RayTraceScene::
set_instance_transform(int n, const LMatrix4 &transform) {
  LightMutexHolder holder(_lock);
  nassertv(n >= 0 && (size_t)n < _instances.size());
  _instances[n]._transform = LCAST(float, transform);
  ++_modified;
}

/**
 * Changes the visibility mask of the nth instance.  An instance with mask 0
 * is hit by no ray.
 */
void RayTraceScene::
set_instance_mask(int n, unsigned int mask) {
  LightMutexHolder holder(_lock);
  nassertv(n >= 0 && (size_t)n < _instances.size());
  _instances[n]._mask = mask & 0xff;
  ++_modified;
  ++_layout_modified;
}

/**
 * Replaces the mesh of the nth instance.
 */
void RayTraceScene::
set_instance_mesh(int n, RayTraceMesh *mesh) {
  nassertv(mesh != nullptr);
  LightMutexHolder holder(_lock);
  nassertv(n >= 0 && (size_t)n < _instances.size());
  _instances[n]._mesh = mesh;
  ++_modified;
  ++_layout_modified;
}

/**
 * Removes all instances.
 */
void RayTraceScene::
clear_instances() {
  LightMutexHolder holder(_lock);
  _instances.clear();
  ++_modified;
  ++_layout_modified;
}

/**
 * Returns the number of instances.
 */
int RayTraceScene::
get_num_instances() const {
  LightMutexHolder holder(_lock);
  return (int)_instances.size();
}

/**
 * Returns the mesh of the nth instance.
 */
PT(RayTraceMesh) RayTraceScene::
get_instance_mesh(int n) const {
  LightMutexHolder holder(_lock);
  nassertr(n >= 0 && (size_t)n < _instances.size(), nullptr);
  return _instances[n]._mesh;
}

/**
 * Returns the transform of the nth instance.
 */
LMatrix4 RayTraceScene::
get_instance_transform(int n) const {
  LightMutexHolder holder(_lock);
  nassertr(n >= 0 && (size_t)n < _instances.size(), LMatrix4::ident_mat());
  return LCAST(PN_stdfloat, _instances[n]._transform);
}

/**
 *
 */
void RayTraceScene::
output(std::ostream &out) const {
  out << "RayTraceScene " << get_name() << ", " << get_num_instances()
      << " instances";
}

/**
 * Copies the instances, for building the GPU structure, and returns the
 * sequence number of the copy; layout is set to its layout's (which only
 * moving an instance leaves as it is).
 */
UpdateSeq RayTraceScene::
get_instances(pvector<Instance> &into, UpdateSeq &layout) const {
  LightMutexHolder holder(_lock);
  into = _instances;
  layout = _layout_modified;
  return _modified;
}

/**
 * Returns a sequence number that changes whenever the scene is changed.
 */
UpdateSeq RayTraceScene::
get_modified() const {
  LightMutexHolder holder(_lock);
  return _modified;
}
