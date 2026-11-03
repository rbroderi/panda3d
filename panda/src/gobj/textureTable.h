/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file textureTable.h
 * @author rbroderi
 * @date 2026-11-02
 */

#ifndef TEXTURETABLE_H
#define TEXTURETABLE_H

#include "pandabase.h"
#include "shaderBuffer.h"
#include "texture.h"
#include "samplerState.h"
#include "lightMutex.h"
#include "lightMutexHolder.h"
#include "updateSeq.h"

/**
 * A list of textures that one shader input exposes as an unsized array, so
 * that a shader can pick any of them by index ("bindless" textures):
 *
 *   #extension GL_EXT_nonuniform_qualifier : require
 *   uniform sampler2D materials[];
 *   ... texture(materials[nonuniformEXT(index)], uv) ...
 *
 * Pass it with set_shader_input(), as you would a ShaderBuffer.  A shader may
 * have one such input.  Each texture is sampled with the sampler given with
 * it, or with its default sampler.  All of its textures must be of the type
 * the shader declares (2-D for a sampler2D[]).
 *
 * Adding textures is cheap: where the hardware allows (update-after-bind),
 * only the new entries are written.  Replacing one rewrites the whole table.
 * This may be done from any thread.
 *
 * This is only supported by the Vulkan renderer, where the GSG's
 * get_supports_texture_tables() is true.
 */
class EXPCL_PANDA_GOBJ TextureTable : public ShaderBuffer {
PUBLISHED:
  explicit TextureTable(const std::string &name = std::string());

  int add_texture(Texture *texture);
  int add_texture(Texture *texture, const SamplerState &sampler);
  void set_texture(int n, Texture *texture);
  void set_texture(int n, Texture *texture, const SamplerState &sampler);
  void clear();

  int get_num_textures() const;
  PT(Texture) get_texture(int n) const;
  SamplerState get_sampler(int n) const;
  int find_texture(const Texture *texture) const;
  MAKE_SEQ(get_textures, get_num_textures, get_texture);
  MAKE_PROPERTY(num_textures, get_num_textures);

  virtual void output(std::ostream &out) const;

public:
  struct Entry {
    PT(Texture) _texture;
    SamplerState _sampler;
  };
  UpdateSeq get_entries(pvector<Entry> &into, UpdateSeq &rewritten) const;
  UpdateSeq get_modified() const;

private:
  mutable LightMutex _lock;
  pvector<Entry> _entries;

  // Any change, and a change to an entry already there (not an addition).
  UpdateSeq _modified;
  UpdateSeq _rewritten;

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
    register_type(_type_handle, "TextureTable",
                  ShaderBuffer::get_class_type());
  }

private:
  static TypeHandle _type_handle;
};

#endif
